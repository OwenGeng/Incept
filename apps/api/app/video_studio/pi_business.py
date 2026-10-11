"""Authenticated Pi tools over existing business APIs; no model or agent loop.

All paths are relative to the authenticated project's assets. Private state is
stored separately through the metadata repository and is never a workspace file.
Paid generation requires an interactive approval bound to the exact request.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import time
import uuid
from contextlib import nullcontext
from pathlib import Path

from . import store
from .models import CanvasCreate, CanvasUpdate, CatalogImport, ExportRequest, MediaJobCreate, SkillDefinition
from .workspace_documents import DocumentConflict, MAX_TEXT_BYTES, document_lock, text_snapshot, write_document

MAX_RESOURCE_CHARS = 100_000
_RESOURCES = {'memory', 'rules', 'team'}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=str).encode()).hexdigest()


def _object(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


def _string(**kwargs):
    return {'type': 'string', **kwargs}


def _schema(model):
    """Inline Pydantic references for the SDK's tool schema compiler."""
    schema = model.model_json_schema()
    definitions = schema.pop('$defs', {})
    def expand(value):
        if isinstance(value, dict):
            if '$ref' in value:
                return expand(copy.deepcopy(definitions[value['$ref'].split('/')[-1]]))
            result = {key: expand(item) for key, item in value.items()}
            if result.get('type') == 'object':
                result['additionalProperties'] = False
            return result
        return [expand(item) for item in value] if isinstance(value, list) else value
    return expand(schema)


def _validate(value, schema):
    """Reject unknown keys and malformed tool arguments before dispatch."""
    if 'anyOf' in schema:
        for option in schema['anyOf']:
            try:
                _validate(value, option)
                return
            except (ValueError, TypeError):
                pass
        raise ValueError('Tool argument does not match a supported type')
    kind = schema.get('type')
    if kind == 'object':
        if not isinstance(value, dict):
            raise ValueError('Tool arguments must be an object')
        if set(value) - set(schema.get('properties', {})):
            raise ValueError('Unknown tool argument')
        if set(schema.get('required', [])) - set(value):
            raise ValueError('Required tool argument is missing')
        for key, item in value.items():
            _validate(item, schema['properties'][key])
    elif kind == 'array':
        if not isinstance(value, list) or len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', 10_000):
            raise ValueError('Invalid tool argument list')
        for item in value:
            _validate(item, schema.get('items', {}))
    elif kind == 'string':
        if not isinstance(value, str) or len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', MAX_TEXT_BYTES):
            raise ValueError('Invalid text tool argument')
        if schema.get('pattern') and not re.search(schema['pattern'], value):
            raise ValueError('Invalid tool argument format')
    elif kind == 'boolean' and not isinstance(value, bool):
        raise ValueError('Tool argument must be a boolean')
    elif kind in {'number', 'integer'}:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or (kind == 'integer' and not isinstance(value, int)):
            raise ValueError('Tool argument must be a finite number')
        if value < schema.get('minimum', -math.inf) or value > schema.get('maximum', math.inf) or value <= schema.get('exclusiveMinimum', -math.inf):
            raise ValueError('Tool argument is out of range')
    elif kind == 'null' and value is not None:
        raise ValueError('Tool argument must be null')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('Unsupported tool action or option')


class BusinessTools:
    def __init__(self, email, project_id, conversation_id, control, canvas_tools, ask=None,
                 invoke_async=None, enabled_extensions=None, extension_configs=None, permissions=None, readonly=False):
        store.get_project(email, project_id)  # Ownership is checked even for private user state.
        self.email, self.project_id, self.conversation_id = email, project_id, conversation_id
        self.control, self.canvas_tools = control, canvas_tools
        self.ask, self.invoke_async = ask, invoke_async
        self.enabled_extensions, self.extension_configs = enabled_extensions, extension_configs or {}
        self.permissions, self.readonly = permissions, readonly
        self.canvas_id = store.get_project(email, project_id).active_canvas_id
        self.canvas_baseline = store.get_project_canvas(email, project_id, self.canvas_id).model_copy(deep=True)
        self.canvas_file_locked = False

    def _check(self):
        if self.control:
            self.control.check()
        store.get_project(self.email, self.project_id)

    def _mutation(self):
        return self.control.mutation() if self.control else nullcontext()

    def _allowed(self, name, args):
        if self.enabled_extensions is not None:
            gate = {'workspaceDocuments': 'tool-workspace', 'canvasManager': 'tool-canvas'}.get(name)
            if gate and gate not in self.enabled_extensions:
                raise ValueError('Business tool is disabled')
            if name == 'mediaJobs' and args['action'] == 'submit' and 'tool-media-generation' not in self.enabled_extensions:
                raise ValueError('Media generation is disabled')
            if name in {'mediaJobs', 'exportJobs'} and args['action'] == 'attach' and 'tool-canvas' not in self.enabled_extensions:
                raise ValueError('Canvas attachment is disabled')
        reads = {'list', 'read', 'search', 'status', 'probe'}
        if name in {'workspaceDocuments', 'canvasManager', 'mediaJobs', 'exportJobs', 'mediaProcess'} and args['action'] not in reads:
            domain = 'workspace' if name == 'workspaceDocuments' else 'canvas' if name == 'canvasManager' else 'media'
            if not self._can(domain):
                raise ValueError('This turn does not authorize workspace or media changes')
        if name in {'mediaJobs', 'exportJobs'} and args['action'] == 'cancel' and self.permissions is not None and not self.permissions.get('destructive'):
            raise ValueError('This turn does not authorize cancellation')

    def _can(self, domain):
        if self.permissions is not None:
            return bool(self.permissions.get(domain, self.permissions.get('canvas', False)))
        return not self.readonly

    def definitions(self, readonly=None):
        if readonly is not None:
            self.readonly = readonly
        workspace_write, canvas_write, media_write = [self._can(domain) for domain in ('workspace', 'canvas', 'media')]
        generation_enabled = self.enabled_extensions is None or 'tool-media-generation' in self.enabled_extensions
        attachment_enabled = self.enabled_extensions is None or 'tool-canvas' in self.enabled_extensions
        cancellation_enabled = self.permissions is None or bool(self.permissions.get('destructive'))
        media_request_schema = _schema(MediaJobCreate)
        # Input revisions are authenticated by the host before approval, never
        # accepted as hashes supplied by a model.
        media_request_schema['properties'].pop('input_revisions', None)
        resource = _object({'action': _string(enum=['read', 'write', 'forget', 'configure']),
            'scope': _string(enum=['user', 'project']), 'content': _string(maxLength=MAX_RESOURCE_CHARS),
            'expected_revision': _string(), 'enabled': {'type': 'boolean'}}, ['action'])
        specs = [
            ('memoryOperator', 'Read, explicitly remember, forget or disable user/project memory. Use exact revisions; current instructions always take priority.', resource),
            ('projectRules', 'Read or edit versioned project instructions. These are user-owned rules, not model-generated plans.', resource),
            ('skillManager', 'List, read, create, update, enable or delete user-owned skills shared across this user\'s projects, with catalog revision checks.', _object({
                'action': _string(enum=['list', 'read', 'write', 'delete']), 'id': _string(), 'expected_revision': _string(),
                'skill': _schema(SkillDefinition)}, ['action'])),
            ('workspaceDocuments', 'Bounded project asset listing, text search and revision-safe UTF-8 document writes. Paths are project-relative; private state is inaccessible.', _object({
                'action': _string(enum=['list', 'read', 'search'] if not workspace_write else ['list', 'read', 'search', 'create', 'write']),
                'path': _string(maxLength=1024), 'query': _string(maxLength=200), 'text': _string(maxLength=MAX_TEXT_BYTES),
                'expected_revision': _string(), 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 200}}, ['action'])),
            ('canvasManager', 'List/read canvases or create/switch/rename them. Switching is blocked if this turn has uncommitted canvas edits.', _object({
                'action': _string(enum=['list', 'read'] if not canvas_write else ['list', 'read', 'create', 'switch', 'rename']),
                'canvas_id': _string(), 'name': _string(minLength=1, maxLength=120)}, ['action'])),
            ('mediaJobs', 'Submit a configured provider/model request only after interactive exact-request paid approval; inspect, cancel or attach completed jobs. A stable idempotency_key is required.', _object({
                'action': _string(enum=['list', 'status'] + ((['cancel'] if cancellation_enabled else []) + (['attach'] if attachment_enabled else []) + (['submit'] if generation_enabled else []) if media_write else [])),
                'request': media_request_schema, 'job_id': _string(pattern='^[a-f0-9]{32}$'),
                'node_id': _string(), 'position': _object({'x': {'type': 'number'}, 'y': {'type': 'number'}}, ['x', 'y'])}, ['action'])),
            ('exportJobs', 'Submit, inspect, cancel or attach local exports from project assets using existing export jobs. A stable idempotency_key is required.', _object({
                'action': _string(enum=['list', 'status'] + (['submit'] + (['cancel'] if cancellation_enabled else []) + (['attach'] if attachment_enabled else []) if media_write else [])),
                'request': _schema(ExportRequest), 'job_id': _string(pattern='^[a-f0-9]{32}$'),
                'node_id': _string(), 'position': _object({'x': {'type': 'number'}, 'y': {'type': 'number'}}, ['x', 'y'])}, ['action'])),
            ('mediaProcess', 'Probe project media, or create a bounded local trim, resized video, audio extraction or still frame. Uses fixed media operations; no shell or custom commands.', _object({
                'action': _string(enum=['probe'] if not media_write else ['probe', 'trim', 'resize', 'extract_audio', 'extract_frame']),
                'path': _string(minLength=1, maxLength=1024), 'start': {'type': 'number', 'minimum': 0, 'maximum': 3600},
                'duration': {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 600},
                'width': {'type': 'integer', 'minimum': 32, 'maximum': 3840},
                'height': {'type': 'integer', 'minimum': 32, 'maximum': 2160}}, ['action', 'path'])),
            ('remoteTeam', 'List configured external team agents; send a user-approved exact task through A2A 0.3 JSON-RPC, or inspect/cancel its receipt. External transmission always requires interactive approval. No arbitrary URLs or credentials.', _object({
                'action': _string(enum=['list', 'send', 'status', 'cancel']), 'target_id': _string(maxLength=80),
                'text': _string(minLength=1, maxLength=12_000), 'idempotency_key': _string(minLength=8, maxLength=128),
                'receipt_id': _string(pattern='^[a-f0-9]{64}$')}, ['action'])),
        ]
        return [{'name': name, 'description': description, 'parameters': schema} for name, description, schema in specs
                if self.enabled_extensions is None or not {'workspaceDocuments': 'tool-workspace', 'canvasManager': 'tool-canvas'}.get(name)
                or {'workspaceDocuments': 'tool-workspace', 'canvasManager': 'tool-canvas'}[name] in self.enabled_extensions]

    def execute(self, name, args, tool_call_id=None):
        self._check()
        definition = next((item for item in self.definitions() if item['name'] == name), None)
        if not definition:
            raise ValueError('Unknown or disabled business tool')
        if not isinstance(args, dict) or not isinstance(args.get('action'), str):
            raise ValueError('Business tools require an action string')
        self._allowed(name, args)
        _validate(args, definition['parameters'])
        if name in {'memoryOperator', 'projectRules'}:
            return self._resource('memory' if name == 'memoryOperator' else 'rules', args)
        if name == 'skillManager':
            return self._skills(args)
        if name == 'workspaceDocuments':
            return self._workspace(args)
        if name == 'canvasManager':
            return self._canvas(args)
        if name in {'mediaJobs', 'exportJobs'}:
            return self._jobs(name == 'mediaJobs', args, tool_call_id)
        if name == 'remoteTeam':
            return self._remote(args, tool_call_id)
        return self._process(args)

    def _resource_path(self, resource, scope):
        if resource not in _RESOURCES or scope not in {'user', 'project'} or (resource != 'memory' and scope != 'project'):
            raise ValueError('Unsupported resource scope')
        root = store._user_root(self.email) if scope == 'user' else store._project_root(self.email, self.project_id)
        return root / 'pi-private' / f'{resource}.json'

    def resource_read(self, resource, scope='project'):
        self._check()
        if resource == 'skills':
            if scope != 'project':
                raise ValueError('Skills resource supports project scope only')
            # Project scope is the authenticated resource API entry point;
            # the existing user catalog is shared across that user's projects.
            catalog = store.get_catalog(self.email)
            return {'resource': resource, 'scope': scope, 'content': json.dumps([item.model_dump(mode='json') for item in catalog.skills], ensure_ascii=False, indent=2),
                    'enabled': True, 'revision': _digest(catalog.model_dump(mode='json'))}
        state = store._read_json(self._resource_path(resource, scope), {'content': '', 'enabled': True, 'history': []})
        return {'resource': resource, 'scope': scope, 'content': state['content'], 'enabled': state['enabled'],
                'revision': state.get('revision') or _digest({'content': state['content'], 'enabled': state['enabled']})}

    def resource_write(self, resource, content, expected_revision, enabled=True, scope='project'):
        self._check()
        if not isinstance(content, str) or len(content) > MAX_RESOURCE_CHARS or not isinstance(enabled, bool):
            raise ValueError('Invalid resource content')
        if resource == 'skills':
            if scope != 'project':
                raise ValueError('Skills resource supports project scope only')
            if not enabled:
                raise ValueError('Enable or disable individual skills in the catalog')
            raw = json.loads(content)
            if not isinstance(raw, list) or len(raw) > 100:
                raise ValueError('Skills content must be a JSON array of at most 100 skills')
            for item in raw:
                _validate(item, _schema(SkillDefinition))
            skills = [SkillDefinition.model_validate(item) for item in raw]
            if len({item.id for item in skills}) != len(skills):
                raise ValueError('Skill identifiers must be unique')
            path = store._user_root(self.email) / 'catalog.json'
            with self._mutation(), document_lock(path):
                if not expected_revision or self.resource_read(resource)['revision'] != expected_revision:
                    raise DocumentConflict('Skill catalog changed; reload before editing')
                custom = store._custom_catalog(self.email)
                store.save_catalog(self.email, CatalogImport(skills=skills, extensions=custom.extensions))
            return self.resource_read(resource)
        if resource == 'team':
            self._validate_team(content)
        path = self._resource_path(resource, scope)
        with self._mutation(), document_lock(path):
            current = self.resource_read(resource, scope)
            if not expected_revision or expected_revision != current['revision']:
                raise DocumentConflict('Resource changed; read its current revision before writing')
            previous = store._read_json(path, {'history': []})
            # Forgetting memory removes its content from revision history as well.
            history = [] if resource == 'memory' and not content else [*previous.get('history', []), current][-20:]
            store._write_json(path, {'content': content, 'enabled': enabled, 'history': history, 'revision': uuid.uuid4().hex})
        return self.resource_read(resource, scope)

    @staticmethod
    def _validate_team(content):
        if not content.strip():
            return
        value = json.loads(content)
        if not isinstance(value, dict) or set(value) - {'agents', 'remote_agents'}:
            raise ValueError('Team configuration supports agents and remote_agents only')
        agents, remote = value.get('agents', []), value.get('remote_agents', [])
        if not isinstance(agents, list) or not isinstance(remote, list) or len(agents) + len(remote) > 20:
            raise ValueError('A team supports up to 20 agents')
        for item in agents:
            if not isinstance(item, dict) or set(item) - {'id', 'name', 'instructions'} or not isinstance(item.get('name'), str):
                raise ValueError('Invalid team agent')
            if not 0 < len(item['name']) <= 120:
                raise ValueError('Team names require 1 to 120 characters')
            if not isinstance(item.get('id'), str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', item['id']) or not isinstance(item.get('instructions', ''), str):
                raise ValueError('Team agents require unique safe IDs and text instructions')
            if len(json.dumps(item)) > 30_000:
                raise ValueError('Team instructions are too large')
        if remote:
            from .research_tools import _assert_public_url, _normalized_http_url
            for item in remote:
                if not isinstance(item, dict) or set(item) - {'id', 'name', 'url'} or not isinstance(item.get('name'), str):
                    raise ValueError('Invalid remote agent')
                if not 0 < len(item['name']) <= 120 or not isinstance(item.get('url'), str) or len(item['url']) > 2048:
                    raise ValueError('Remote name or URL is invalid')
                if not isinstance(item.get('id'), str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', item['id']):
                    raise ValueError('Remote agents require safe IDs')
                url = _normalized_http_url(item.get('url', ''))
                if not url.startswith('https://'):
                    raise ValueError('Remote agents require HTTPS')
                _assert_public_url(url)
        ids = [item['id'] for item in agents + remote]
        if len(set(ids)) != len(ids):
            raise ValueError('Team agent IDs must be unique')

    def _resource(self, resource, args):
        scope = args.get('scope', 'project')
        current = self.resource_read(resource, scope)
        if args['action'] == 'read':
            return current
        if args['action'] == 'write' and 'content' not in args:
            raise ValueError('Resource write requires content')
        if args['action'] == 'configure' and 'enabled' not in args:
            raise ValueError('Configure requires an explicit enabled value')
        content = '' if args['action'] == 'forget' else args.get('content', current['content'])
        enabled = args.get('enabled', current['enabled'])
        return self.resource_write(resource, content, args.get('expected_revision'), enabled, scope)

    def context(self):
        chunks = []
        for resource, scope in [('memory', 'user'), ('memory', 'project'), ('rules', 'project')]:
            value = self.resource_read(resource, scope)
            if value['enabled'] and value['content'].strip():
                chunks.append(f'User-owned {scope} {resource} (current instructions take priority):\n{value["content"]}')
        return '\n\n'.join(chunks)

    def _skills(self, args):
        path = store._user_root(self.email) / 'catalog.json'
        with document_lock(path):
            catalog = store.get_catalog(self.email)
            revision = _digest(catalog.model_dump(mode='json'))
            if args['action'] == 'list':
                return {'revision': revision, 'skills': [item.model_dump(mode='json') for item in catalog.skills]}
            if args['action'] == 'read':
                item = next((item for item in catalog.skills if item.id == args.get('id')), None)
                if not item:
                    raise ValueError('Unknown skill')
                return {'revision': revision, 'skill': item.model_dump(mode='json')}
            if not args.get('expected_revision') or args['expected_revision'] != revision:
                raise DocumentConflict('Skill catalog changed; read its current revision before editing')
            custom = store._custom_catalog(self.email)
            if args['action'] == 'write':
                if 'skill' not in args:
                    raise ValueError('Skill write requires skill')
                item = SkillDefinition.model_validate(args['skill'])
                if args.get('id') and args['id'] != item.id:
                    raise ValueError('Skill identifier does not match')
                custom.skills = [entry for entry in custom.skills if entry.id != item.id] + [item]
            else:
                item = next((item for item in catalog.skills if item.id == args.get('id')), None)
                if not item:
                    raise ValueError('Unknown skill')
                if item.builtin:
                    raise ValueError('Builtin skills can be disabled with write, not deleted')
                custom.skills = [entry for entry in custom.skills if entry.id != item.id]
            with self._mutation():
                store.save_catalog(self.email, CatalogImport.model_validate(custom.model_dump()))
            result = store.get_catalog(self.email)
            return {'revision': _digest(result.model_dump(mode='json')), 'skills': [item.model_dump(mode='json') for item in result.skills]}

    def _asset(self, path, allow_root=False):
        if not isinstance(path, str) or path.startswith(('/', '\\')) or '..' in Path(path.replace('\\', '/')).parts or ':' in path or '\x00' in path:
            raise ValueError('Only project-relative asset paths are supported')
        root = store.assets_root(self.email, self.project_id)
        target = store.safe_asset_path(root, path, allow_root=allow_root)
        return root, target

    def _workspace(self, args):
        root, target = self._asset(args.get('path', ''), allow_root=args['action'] in {'list', 'search'})
        action, limit = args['action'], args.get('limit', 100)
        if action == 'read':
            return {'path': target.relative_to(root).as_posix(), **text_snapshot(target, 200_000)}
        if action in {'create', 'write'}:
            if 'text' not in args or (action == 'write' and not args.get('expected_revision')):
                raise ValueError('Document writes require text and current revision')
            payload = args['text'].encode('utf-8')
            if len(payload) > MAX_TEXT_BYTES or '\x00' in args['text']:
                raise ValueError('Text is too large or contains binary data')
            with self._mutation():
                revision = write_document(target, payload, exclusive=action == 'create', expected_revision=args.get('expected_revision'), encoding='utf-8')
            return {'path': target.relative_to(root).as_posix(), 'revision': revision, 'status': 'saved'}
        if not target.is_dir():
            raise ValueError('Workspace listing/search requires a directory')
        if action == 'list':
            entries, truncated = [], False
            for entry in sorted(target.iterdir(), key=lambda item: item.name.lower()):
                if entry.is_symlink() or not entry.resolve().is_relative_to(root):
                    continue
                if len(entries) == limit:
                    truncated = True
                    break
                entries.append({'path': entry.relative_to(root).as_posix(), 'kind': 'directory' if entry.is_dir() else 'file', 'size': entry.stat().st_size if entry.is_file() else 0})
            return {'entries': entries, 'truncated': truncated}
        query = args.get('query')
        if not query:
            raise ValueError('Search requires a nonempty literal query')
        matches, visited, scanned = [], 0, 0
        # Bound file count, decoded bytes and results; never recurse through symlinks.
        for directory, dirs, files in os.walk(target, followlinks=False):
            dirs[:] = sorted(name for name in dirs if not (Path(directory) / name).is_symlink())
            for name in sorted(files):
                path = Path(directory) / name
                visited += 1
                if visited > 500 or scanned > 5_000_000 or len(matches) >= limit:
                    return {'matches': matches, 'truncated': True}
                if path.is_symlink() or not path.resolve().is_relative_to(root) or path.stat().st_size > 200_000:
                    continue
                scanned += path.stat().st_size
                try:
                    snapshot = text_snapshot(path, 200_000)
                except (ValueError, OverflowError):
                    continue
                for number, line in enumerate(snapshot['text'].splitlines(), 1):
                    if query.casefold() in line.casefold():
                        matches.append({'path': path.relative_to(root).as_posix(), 'line': number, 'text': line[:1000], 'revision': snapshot['revision']})
                        if len(matches) >= limit:
                            return {'matches': matches, 'truncated': True}
        return {'matches': matches, 'truncated': False}

    def _canvas(self, args):
        action = args['action']
        if action == 'list':
            project = store.get_project(self.email, self.project_id)
            return {'active_canvas_id': project.active_canvas_id, 'canvases': [item.model_dump(mode='json') for item in project.canvases]}
        if action == 'read':
            canvas_id = args.get('canvas_id', self.canvas_id)
            value = self.canvas_tools.canvas if canvas_id == self.canvas_id else store.get_project_canvas(self.email, self.project_id, canvas_id)
            return {'canvas_id': canvas_id, 'canvas': value.model_dump(mode='json')}
        if action in {'create', 'switch'}:
            if self.canvas_file_locked:
                raise ValueError('This turn targets a workspace canvas file; finish it before switching the project canvas')
            if self.canvas_tools.changed:
                raise DocumentConflict('Commit staged canvas changes in this turn before switching canvases')
        # Serialize against API/editor commits across Cloud Run instances.
        with self._mutation(), document_lock(store._project_root(self.email, self.project_id) / 'project.json'):
            if action == 'rename':
                if not args.get('name') or not args.get('canvas_id'):
                    raise ValueError('Rename requires canvas_id and name')
                values = store.update_canvas(self.email, self.project_id, args['canvas_id'], CanvasUpdate(name=args['name']))
                return {'status': 'saved', 'canvases': [item.model_dump(mode='json') for item in values]}
            if action == 'create':
                if not args.get('name'):
                    raise ValueError('Create requires name')
                project = store.create_canvas(self.email, self.project_id, CanvasCreate(name=args['name']))
            else:
                if not args.get('canvas_id'):
                    raise ValueError('Switch requires canvas_id')
                project = store.activate_canvas(self.email, self.project_id, args['canvas_id'])
            # Turn host must commit to this updated ID and baseline.
            self.canvas_id = project.active_canvas_id
            self.canvas_baseline = project.canvas.model_copy(deep=True)
            self.canvas_tools.canvas = project.canvas.model_copy(deep=True)
            self.canvas_tools.changed = False
            return {'status': 'saved', 'active_canvas_id': project.active_canvas_id, 'canvas': project.canvas.model_dump(mode='json')}

    def _async(self, function):
        if not self.invoke_async:
            raise RuntimeError('The API event loop is required for background jobs')
        async def invoke():
            return function()
        return self.invoke_async(invoke())

    @staticmethod
    def _approved(answer, label='批准并提交'):
        if not isinstance(answer, dict) or answer.get('skipped'):
            return False
        values = answer.get('values', {})
        reply = answer.get('answer')
        choice = values.get('choice') if isinstance(values, dict) else None
        return answer.get('approved') is True or (isinstance(reply, str) and reply in {'approve', label}) or (isinstance(choice, str) and choice in {'approve', label})

    def _remote(self, args, tool_call_id):
        """A2A 0.3 JSON-RPC: https://a2a-protocol.org/v0.3.0/specification/."""
        state = self.resource_read('team')
        team = json.loads(state['content']) if state['content'].strip() else {}
        targets = team.get('remote_agents', []) if state['enabled'] else []
        if args['action'] == 'list':
            return {'agents': targets, 'protocol': 'A2A 0.3 JSON-RPC'}
        if args['action'] != 'send':
            if not args.get('receipt_id'):
                raise ValueError('Remote task operation requires receipt_id')
            path = store._project_root(self.email, self.project_id) / 'pi-private' / 'remote-receipts' / f'{args["receipt_id"]}.json'
            receipt = store._read_json(path, None)
            if not receipt or receipt.get('conversation_id') != self.conversation_id:
                raise ValueError('Remote task receipt is unavailable in this conversation')
            target = next((item for item in targets if item['id'] == receipt['target']['id']), None)
            if not target or target['url'] != receipt['target']['url']:
                raise ValueError('Remote target is disabled or its configured address changed')
            if not receipt.get('task_id'):
                return {'receipt_id': args['receipt_id'], 'status': receipt['status'], 'result': receipt.get('result')}
            if args['action'] == 'cancel':
                # Cancellation sends a message externally too; ask before doing so.
                if not self.ask or not self._approved(self.ask(tool_call_id or f'remote-cancel-{args["receipt_id"][:20]}', {
                    'title': '取消外部代理任务', 'question': f'向已配置外部代理 {target["name"]} 请求取消任务 {receipt["task_id"]}？',
                    'options': ['批准并发送', '取消'], 'outboundRequest': {'target': target, 'task_id': receipt['task_id'], 'method': 'tasks/cancel'},
                }), '批准并发送'):
                    return {'status': 'approval_denied', 'receipt_id': args['receipt_id']}
            method = 'tasks/cancel' if args['action'] == 'cancel' else 'tasks/get'
            result = self._remote_rpc(target['url'], method, {'id': receipt['task_id']})
            return {'receipt_id': args['receipt_id'], 'result': result}
        if not args.get('target_id') or not args.get('text') or not args.get('idempotency_key'):
            raise ValueError('Remote send requires configured target_id, text and stable idempotency_key')
        target = next((item for item in targets if item['id'] == args['target_id']), None)
        if not target:
            raise ValueError('Remote target is not configured or enabled')
        exact = {'target': target, 'text': args['text']}
        request_hash = _digest(exact)
        key = _digest({'conversation': self.conversation_id, 'target': target['id'], 'key': args['idempotency_key']})
        path = store._project_root(self.email, self.project_id) / 'pi-private' / 'remote-receipts' / f'{key}.json'
        with self._mutation(), document_lock(path):
            receipt = store._read_json(path, None)
            if receipt and receipt['request_hash'] != request_hash:
                raise DocumentConflict('Remote idempotency key is bound to a different target or task')
            if receipt and receipt['status'] in {'sent', 'uncertain', 'sending', 'denied'}:
                return {'receipt_id': key, 'status': receipt['status'], 'result': receipt.get('result'), 'reused': True}
            if receipt and receipt['status'] == 'asking' and receipt.get('run_id') == getattr(self.control, 'run_id', None):
                return {'receipt_id': key, 'status': 'approval_pending'}
            approved = bool(receipt and receipt['status'] == 'approved')
            if not approved:
                receipt = {'conversation_id': self.conversation_id, 'request_hash': request_hash, 'target': target,
                           'text': args['text'], 'status': 'asking', 'run_id': getattr(self.control, 'run_id', None)}
                store._write_json(path, receipt)
        if not approved:
            try:
                answer = self.ask(tool_call_id or f'remote-{key[:24]}', {
                    'title': '批准外部代理协作', 'question': '以下任务正文将发送给已配置的外部代理。批准发送吗？\n' + json.dumps(exact, ensure_ascii=False, indent=2),
                    'options': ['批准并发送', '取消'], 'outboundRequest': {'requestHash': request_hash, 'request': exact},
                }) if self.ask else {'skipped': True}
            except Exception:
                with document_lock(path):
                    receipt['status'] = 'interrupted'
                    store._write_json(path, receipt)
                raise
            with self._mutation(), document_lock(path):
                receipt.update(status='approved' if self._approved(answer, '批准并发送') else 'denied', answer=answer)
                store._write_json(path, receipt)
            if receipt['status'] == 'denied':
                return {'receipt_id': key, 'status': 'approval_denied'}
        with self._mutation(), document_lock(path):
            receipt = store._read_json(path, {})
            if receipt['status'] != 'approved':
                return {'receipt_id': key, 'status': receipt['status'], 'result': receipt.get('result'), 'reused': True}
            receipt['status'] = 'sending'
            store._write_json(path, receipt)
        # Persist "sending" before network IO: uncertain sends are never replayed.
        try:
            result = self._remote_rpc(target['url'], 'message/send', {
                'message': {'kind': 'message', 'role': 'user', 'messageId': key, 'parts': [{'kind': 'text', 'text': args['text']}]},
                'configuration': {'blocking': False, 'acceptedOutputModes': ['text/plain'], 'historyLength': 2},
            })
        except Exception:
            with document_lock(path):
                receipt['status'] = 'uncertain'
                store._write_json(path, receipt)
            raise
        with document_lock(path):
            receipt.update(status='sent', result=result)
            if result.get('kind') == 'task' and isinstance(result.get('id'), str):
                receipt['task_id'] = result['id']
            store._write_json(path, receipt)
        return {'receipt_id': key, 'status': 'sent', 'result': result, 'reused': False}

    def _remote_rpc(self, url, method, params):
        import httpx
        from .website_assets import PublicMediaTransport
        self._check()
        request_id = uuid.uuid4().hex
        payload = {'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params}
        with httpx.Client(transport=PublicMediaTransport(limits=httpx.Limits(max_keepalive_connections=0)),
                          trust_env=False, follow_redirects=False, timeout=20) as client:
            with client.stream('POST', url, json=payload, headers={'Accept': 'application/json', 'User-Agent': 'LinglongLab-A2A/1.0'}) as response:
                if response.status_code != 200:
                    raise ValueError(f'External agent returned HTTP {response.status_code}; its configured address was not changed')
                if response.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
                    raise ValueError('External agent must return JSON-RPC JSON')
                data, deadline = bytearray(), time.monotonic() + 30
                for chunk in response.iter_bytes():
                    self._check()
                    if len(data) + len(chunk) > 200_000 or time.monotonic() > deadline:
                        raise ValueError('External agent response exceeds the response budget')
                    data.extend(chunk)
        result = json.loads(data)
        if not isinstance(result, dict) or set(result) - {'jsonrpc', 'id', 'result', 'error'} or result.get('jsonrpc') != '2.0' or result.get('id') != request_id:
            raise ValueError('External agent returned an invalid JSON-RPC response')
        if 'error' in result or not isinstance(result.get('result'), dict) or result['result'].get('kind') not in {'message', 'task'}:
            raise ValueError('External agent rejected the request or returned an unsupported A2A result')
        value = result['result']
        if value['kind'] == 'task':
            if not isinstance(value.get('id'), str) or not 0 < len(value['id']) <= 256 or not isinstance(value.get('status'), dict) or value['status'].get('state') not in {
                'submitted', 'working', 'input-required', 'auth-required', 'completed', 'canceled', 'failed', 'rejected', 'unknown'}:
                raise ValueError('External agent returned an invalid A2A task')
        elif not isinstance(value.get('messageId'), str) or not value['messageId'] or value.get('role') != 'agent' or not isinstance(value.get('parts'), list) or not value['parts']:
            raise ValueError('External agent returned an invalid A2A message')
        return value

    def _submit(self, media, args, tool_call_id):
        from . import jobs, media_jobs
        model = MediaJobCreate if media else ExportRequest
        request = model.model_validate(args['request'])
        if not request.idempotency_key:
            raise ValueError('Submit requires a stable request idempotency_key')
        if media:
            # Validate deployment-owned values without changing or inventing IDs.
            from app.routers.video_runtime import validate_media_model
            validate_media_model(request.media_type, request.provider_id, request.model_id)
        for relative in ([request.first_frame_path, request.last_frame_path, request.output_directory] if media else [clip.asset_path for clip in request.clips] + [request.soundtrack_path]):
            if relative:
                self._asset(relative, allow_root=media and relative == request.output_directory)
        if media:
            revisions = {}
            for relative in (request.first_frame_path, request.last_frame_path):
                if not relative or relative in revisions:
                    continue
                _, asset = self._asset(relative)
                if not asset.is_file():
                    raise FileNotFoundError(relative)
                if not store.asset_mime_type(asset).startswith('image/'):
                    raise ValueError('Approved reference frames must be image assets')
                digest = hashlib.sha256()
                with asset.open('rb') as source:
                    while chunk := source.read(1024 * 1024):
                        self._check()
                        digest.update(chunk)
                revisions[relative] = digest.hexdigest()
            request = request.model_copy(update={'input_revisions': revisions})
        exact = request.model_dump(mode='json')
        request_hash = _digest(exact)
        key = _digest({'conversation': self.conversation_id, 'kind': 'media' if media else 'export', 'key': request.idempotency_key})
        path = store._project_root(self.email, self.project_id) / 'pi-private' / 'receipts' / f'{key}.json'
        with self._mutation(), document_lock(path):
            receipt = store._read_json(path, None)
            if receipt and receipt['request_hash'] != request_hash:
                raise DocumentConflict('Idempotency key is already bound to a different exact request')
            if receipt and receipt.get('job_id'):
                result = store.get_media_job(self.email, self.project_id, receipt['job_id']) if media else store.get_export_job(self.email, self.project_id, receipt['job_id'])
                return {'job': result.model_dump(mode='json'), 'approval_receipt': key, 'reused': True}
            if receipt and receipt['status'] == 'denied':
                return {'status': 'approval_denied', 'approval_receipt': key}
            if receipt and receipt['status'] == 'asking' and receipt.get('run_id') == getattr(self.control, 'run_id', None):
                return {'status': 'approval_pending', 'approval_receipt': key}
            approved = bool(receipt and receipt['status'] == 'approved')
            if not approved:
                store._write_json(path, {'request_hash': request_hash, 'request': exact, 'status': 'asking' if media else 'approved',
                                        'run_id': getattr(self.control, 'run_id', None)})
        if media and not approved:
            if not self.ask:
                answer = {'skipped': True}
            else:
                try:
                    answer = self.ask(tool_call_id or f'approve-{key[:24]}', {
                        'title': '批准媒体生成', 'question': '这项生成可能产生供应商费用，费用尚未知。批准下面的完整请求并提交吗？\n' + json.dumps(exact, ensure_ascii=False, indent=2),
                        'options': ['批准并提交', '取消'],
                        'paidRequest': {'requestHash': request_hash, 'request': exact},
                    })
                except Exception:
                    # Mark only private approval state, never submit after a
                    # cancelled/interrupted question. A later run can ask again.
                    with document_lock(path):
                        interrupted = store._read_json(path, {})
                        interrupted['status'] = 'interrupted'
                        store._write_json(path, interrupted)
                    raise
            with self._mutation(), document_lock(path):
                receipt = store._read_json(path, {})
                receipt.update(status='approved' if self._approved(answer) else 'denied', answer=answer)
                store._write_json(path, receipt)
            if not self._approved(answer):
                return {'status': 'approval_denied', 'approval_receipt': key}
        self._check()
        with self._mutation(), document_lock(path):
            receipt = store._read_json(path, {})
            if receipt.get('job_id'):
                result = store.get_media_job(self.email, self.project_id, receipt['job_id']) if media else store.get_export_job(self.email, self.project_id, receipt['job_id'])
                return {'job': result.model_dump(mode='json'), 'approval_receipt': key, 'reused': True}
            # Existing job APIs provide another durable idempotency barrier if a
            # process exits after job persistence but before receipt persistence.
            request = request.model_copy(update={'idempotency_key': f'pi-{key}'})
            create = media_jobs.create_media_job if media else jobs.create_export_job
            result = self._async(lambda: create(self.email, self.project_id, request))
            receipt.update(status='submitted', job_id=result.id)
            store._write_json(path, receipt)
            return {'job': result.model_dump(mode='json'), 'approval_receipt': key, 'reused': False}

    def _jobs(self, media, args, tool_call_id):
        from . import jobs, media_jobs
        action = args['action']
        if action == 'submit':
            if 'request' not in args:
                raise ValueError('Submit requires request')
            return self._submit(media, args, tool_call_id)
        if action == 'list':
            result = store.list_media_jobs(self.email, self.project_id) if media else store.list_export_jobs(self.email, self.project_id)
            return {'jobs': [item.model_dump(mode='json') for item in result][-100:]}
        if not args.get('job_id'):
            raise ValueError('Job action requires job_id')
        if action == 'status':
            ensure = media_jobs.ensure_media_job_running if media else jobs.ensure_export_job_running
            result = self._async(lambda: ensure(self.email, self.project_id, args['job_id']))
        elif action == 'cancel':
            cancel = media_jobs.cancel_media_job if media else jobs.cancel_export_job
            with self._mutation():
                result = self._async(lambda: cancel(self.email, self.project_id, args['job_id']))
        else:
            result = store.get_media_job(self.email, self.project_id, args['job_id']) if media else store.get_export_job(self.email, self.project_id, args['job_id'])
            if result.status != 'completed':
                raise ValueError('Only completed media can be attached')
            relative = result.result_asset_path if media else result.result.asset_path if result.result else None
            mime = result.result_mime_type if media else result.result.mime_type if result.result else None
            if not relative or not mime:
                raise ValueError('Completed job has no media result')
            return self._attach(relative, mime, args)
        return {'job': result.model_dump(mode='json')}

    def _attach(self, relative, mime, args):
        _, asset = self._asset(relative)
        if not asset.is_file():
            raise FileNotFoundError(relative)
        kind = mime.split('/')[0]
        if kind not in {'image', 'video', 'audio'}:
            raise ValueError('Result node type is unsupported')
        node_id = args.get('node_id')
        with self._mutation():
            candidate = self.canvas_tools.canvas.model_copy(deep=True)
            node = next((item for item in candidate.nodes if item.id == node_id), None) if node_id else None
            if node_id and (node is None or node.type not in {kind, kind + 'Generation'} or node.type not in self.canvas_tools.enabled_types):
                raise ValueError('Attach target is missing or incompatible')
            if node is None:
                if kind not in self.canvas_tools.enabled_types:
                    raise ValueError('Result node type is disabled')
                from .models import Position, VideoNode
                node = VideoNode(id=f'{kind}-{uuid.uuid4().hex}', type=kind, position=Position(**args.get('position', {})), data={'label': asset.name, 'kind': kind})
                candidate.nodes.append(node)
            # Vue node media values are workspace paths, resolved through the
            # authenticated workspace file service rather than public URLs.
            node.data.update(outputs={kind: {'dataType': kind.upper(), 'value': {'url': relative, 'mimeType': mime}}}, status='succeeded')
            self.canvas_tools.canvas = type(candidate).model_validate(candidate.model_dump())
            self.canvas_tools.changed = True
        return {'status': 'staged_pending_commit', 'node_id': node.id, 'asset_path': relative}

    def _process(self, args):
        from . import render
        root, source = self._asset(args['path'])
        if not source.is_file():
            raise FileNotFoundError(args['path'])
        if args['action'] == 'probe':
            value = render.probe_asset(self.email, self.project_id, args['path'])
            # ffprobe's format filename contains a server filesystem path.
            value.get('format', {}).pop('filename', None)
            return {'path': args['path'], 'metadata': value}
        mime = store.asset_mime_type(source)
        if not mime.startswith(('video/', 'audio/')):
            raise ValueError('Media processing requires a video or audio asset')
        if args['action'] in {'resize', 'extract_frame'} and not mime.startswith('video/'):
            raise ValueError('This operation requires video')
        if args['action'] == 'resize' and (not args.get('width') or not args.get('height') or args['width'] % 2 or args['height'] % 2):
            raise ValueError('Resize requires even width and height')
        if args['action'] == 'trim' and not args.get('duration'):
            raise ValueError('Trim requires a bounded duration')
        suffix = '.png' if args['action'] == 'extract_frame' else '.wav' if args['action'] == 'extract_audio' or mime.startswith('audio/') else '.mp4'
        destination = root / 'processed' / f'{args["action"]}-{uuid.uuid4().hex}{suffix}'
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = [os.getenv('FFMPEG_PATH', 'ffmpeg'), '-v', 'error', '-nostdin', '-y', '-protocol_whitelist', 'file,pipe', '-ss', str(args.get('start', 0)), '-i', str(source)]
        if args.get('duration'):
            command += ['-t', str(args['duration'])]
        if args['action'] == 'extract_frame':
            command += ['-frames:v', '1']
        elif args['action'] == 'extract_audio' or mime.startswith('audio/'):
            command += ['-vn', '-c:a', 'pcm_s16le']
        else:
            if args['action'] == 'resize':
                command += ['-vf', f'scale={args["width"]}:{args["height"]}']
            command += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart']
        command.append(str(destination))
        try:
            self._check()
            self._run_media_process(command, root, timeout=120)
            self._check()
            if not destination.is_file() or not destination.stat().st_size:
                raise RuntimeError('Media processing returned no output')
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return {'status': 'completed', 'asset_path': destination.relative_to(root).as_posix(), 'mime_type': store.asset_mime_type(destination), 'size': destination.stat().st_size}

    def _run_media_process(self, command, root, *, timeout):
        """Run only the fixed FFmpeg command, stopping promptly on cancellation."""
        with tempfile.TemporaryFile() as errors:
            try:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors)
            except FileNotFoundError as error:
                raise RuntimeError('Required media executable is unavailable') from error
            deadline = time.monotonic() + timeout
            try:
                while process.poll() is None:
                    self._check()
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Media processing exceeded its time limit')
                    try:
                        process.wait(timeout=.2)
                    except subprocess.TimeoutExpired:
                        pass
            except BaseException:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                raise
            if process.returncode:
                errors.seek(0, 2)
                errors.seek(max(0, errors.tell() - 2000))
                detail = errors.read().decode('utf-8', errors='replace').replace(str(root), '<project-assets>')
                raise RuntimeError(detail or 'Media processing failed')
