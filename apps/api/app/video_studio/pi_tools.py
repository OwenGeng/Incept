"""Authenticated business tools for Pi; no model calls or conversation loop.

Canvas parameter contracts derive from Toonflow's canvas plugin (MIT); see
apps/video-vue/apps/agentRuntime/TOONFLOW-LICENSE. Only implemented hosted
operations are advertised. Multi-tool changes commit atomically at turn end.
"""
import json
import os
import uuid
from pathlib import Path

from . import store
from .models import Position, VideoEdge, VideoNode

CANVAS_TOOLS = json.loads(Path(__file__).with_name('pi_canvas_tools.json').read_text())
CANVAS_TOOLS.append({'name': 'validateStoryboard', 'description': 'Check structured shot timing only. Feedback does not reject drafts or approve advertising/media rights.',
    'parameters': {'type': 'object', 'properties': {'duration': {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 180},
        'shots': {'type': 'array', 'minItems': 1, 'maxItems': 100, 'items': {'type': 'object', 'properties': {
            'start': {'type': 'number', 'minimum': 0}, 'end': {'type': 'number', 'minimum': 0}}, 'required': ['start', 'end'], 'additionalProperties': False}}},
        'required': ['duration', 'shots'], 'additionalProperties': False}})
NODE_TYPES = {'text', 'image', 'video', 'audio', 'imageGeneration', 'videoGeneration', 'director3d'}


def validate_storyboard(args):
    import math
    shots, duration = args['shots'], args['duration']
    if not shots or len(shots) > 100 or not isinstance(duration, (int, float)) or isinstance(duration, bool) or not 0 < duration <= 180:
        raise ValueError('Invalid storyboard timing input')
    cursor, errors = 0, []
    for shot in shots:
        start, end = shot['start'], shot['end']
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) for value in (start, end)):
            raise ValueError('Shot times must be finite numbers')
        if end <= start or abs(start - cursor) > .1:
            errors.append('Shot timeline must be continuous from 0 seconds with positive durations.')
        cursor = end
    if abs(cursor - duration) > .1:
        errors.append('Shot timing does not match the provided target duration.')
    return {'valid': not errors, 'errors': errors, 'scope': 'Timing only; not final media QA or advertising approval.'}


def node_functions(node):
    if node.type == 'text':
        if node.data.get('textPath'):
            # Mounted Vue text nodes own a versioned external document. Do not
            # pretend replacing inline data edits that live editor safely.
            return []
        return [{'name': 'node:setText', 'parameters': {'text': 'string', 'expectedText': 'optional string'}}]
    if node.type in {'imageGeneration', 'videoGeneration', 'audio'}:
        return [{'name': 'node:setPrompt', 'parameters': {'prompt': 'string'}}]
    return []


class CanvasTools:
    def __init__(self, canvas, enabled_types):
        self.canvas = canvas.model_copy(deep=True)
        self.enabled_types = enabled_types
        self.changed = False

    def snapshot(self):
        return {**self.canvas.model_dump(mode='json'), 'availableNodeTypes': [
            {'type': kind + 'Node', 'inputs': self.ports(kind)[0], 'outputs': self.ports(kind)[1]}
            for kind in sorted(self.enabled_types)], 'nodeTools': {
            node.id: node_functions(node) for node in self.canvas.nodes}}

    @staticmethod
    def ports(kind):
        # Persisted port IDs must match the actual Vue node registrations.
        inputs = ['in'] if kind in {'imageGeneration', 'videoGeneration'} else []
        output = {'text': 'text', 'image': 'image', 'imageGeneration': 'image',
                  'video': 'video', 'videoGeneration': 'video', 'audio': 'audio'}.get(kind)
        return inputs, [output] if output else []

    def execute(self, name, args):
        if name == 'getCanvas':
            return self.snapshot()
        if name == 'validateStoryboard':
            return validate_storyboard(args)
        candidate = self.canvas.model_copy(deep=True)
        nodes = {node.id: node for node in candidate.nodes}
        if name == 'addNode':
            kind = args['type'].removesuffix('Node').removeprefix('remote-')
            if kind not in self.enabled_types:
                raise ValueError('Node type is disabled or unavailable')
            node = VideoNode(id=f'{kind}-{uuid.uuid4().hex}', type=kind, position=Position(**args['position']),
                data={'kind': kind, 'label': args.get('label') or kind, 'status': 'idle'})
            candidate.nodes.append(node)
            result = {'node': node.model_dump(mode='json'), 'nodeTools': node_functions(node)}
        elif name == 'nodeTools':
            node = nodes[args['nodeId']]
            params = args['args']
            if args['name'] == 'node:setText' and node.type == 'text':
                if node.data.get('textPath'):
                    raise ValueError('This text node uses an external document; create a new revision node or edit the document in the UI.')
                if set(params) - {'text', 'expectedText'} or 'text' not in params:
                    raise ValueError('setText requires text and optional expectedText')
                if not isinstance(params['text'], str):
                    raise ValueError('setText requires a string; draft content is not coerced or rewritten')
                text = str(node.data.get('textSnapshot', ''))
                if 'expectedText' in params and params['expectedText'] != text:
                    raise ValueError('Text changed; read the current canvas before retrying')
                node.data['textSnapshot'] = params['text']
                result = {'text': params['text']}
            elif args['name'] == 'node:setPrompt' and node.type in {'imageGeneration', 'videoGeneration', 'audio'}:
                if set(params) != {'prompt'}:
                    raise ValueError('setPrompt requires only prompt')
                node.data.update(prompt=params['prompt'], promptModel=[
                    [{'type': 'Write', 'text': text}] for text in params['prompt'].split('\n')])
                result = {'prompt': params['prompt']}
            else:
                raise ValueError('This node function is unavailable; use mediaJobs with action=submit and exact-request approval for paid generation')
        elif name == 'deleteNodes':
            for node_id in args['nodeIds']:
                if node_id not in nodes:
                    raise ValueError('Unknown node ID')
            candidate.nodes = [node for node in candidate.nodes if node.id not in args['nodeIds']]
            candidate.edges = [edge for edge in candidate.edges if edge.source not in args['nodeIds'] and edge.target not in args['nodeIds']]
            result = {'deletedNodeIds': args['nodeIds']}
        elif name in {'moveNodes', 'renameNodes'}:
            for item in args['moves' if name == 'moveNodes' else 'renames']:
                node = nodes[item['nodeId']]
                if name == 'moveNodes':
                    node.position = Position(**item['position'])
                else:
                    node.data['label'] = item['label']
            result = {'updated': True}
        elif name == 'deleteEdges':
            if set(args['edgeIds']) - {edge.id for edge in candidate.edges}:
                raise ValueError('Unknown edge ID')
            candidate.edges = [edge for edge in candidate.edges if edge.id not in args['edgeIds']]
            result = {'deletedEdgeIds': args['edgeIds']}
        elif name == 'connectNodes':
            for connection in args['connections']:
                source, target = nodes[connection['source']], nodes[connection['target']]
                output, input_port = connection['sourceHandle'], connection['targetHandle']
                if source.id == target.id or output not in self.ports(source.type)[1] or input_port not in self.ports(target.type)[0]:
                    raise ValueError('Unknown or incompatible port')
                if input_port != 'in' or (target.type == 'imageGeneration' and output not in {'image', 'text'}):
                    raise ValueError('Incompatible port types')
                if any(edge.target == target.id and edge.target_handle == input_port for edge in candidate.edges):
                    raise ValueError('Input port already connected')
                candidate.edges.append(VideoEdge(id=f'edge-{uuid.uuid4().hex}', source=source.id, target=target.id,
                    source_handle=output, target_handle=input_port))
            result = {'connected': len(args['connections'])}
        else:
            raise ValueError('Unknown canvas operation')
        # Revalidate bounds after the entire batch, before changing staged state.
        self.canvas = type(candidate).model_validate(candidate.model_dump())
        self.changed = True
        return {**result, 'status': 'staged_pending_commit'}


def skill_tool(skills):
    return {'name': 'skillOperator', 'description': 'List/read enabled production skills and references. Reading instructions does not grant permission to research, import assets or generate media. No skill writes.',
        'parameters': {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': ['list', 'read']},
            'name': {'type': 'string'}, 'scope': {'type': 'string', 'enum': ['workspace']}, 'path': {'type': 'string'}},
            'required': ['action'], 'additionalProperties': False}}


def read_skill(args, skills):
    if args['action'] == 'list':
        return {'skills': [{'name': 'workflow', 'scope': 'workspace', 'description': 'Toonflow production workflow; continue approved stages.'},
            *[{'name': s.id, 'description': s.description, 'scope': 'workspace', 'disableModelInvocation': not (s.builtin and s.id in {'canvas', 'storyboard', 'continuity', 'ctv-creative-strategy'})} for s in skills]]}
    name = args.get('name')
    relative = args.get('path') or 'SKILL.md'
    if name == 'workflow':
        root = Path(os.getenv('INCEPT_PROJECT_ROOT') or Path(__file__).resolve().parents[4]) / 'apps/video-vue/apps/agentRuntime/skills/workflow'
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_size > 200_000:
            raise ValueError('Unknown skill reference')
        return {'name': name, 'path': relative, 'content': path.read_text()}
    skill = next((s for s in skills if s.id == name), None)
    if not skill or relative != 'SKILL.md':
        raise ValueError('Skill or reference is unavailable')
    content = skill.instructions
    if skill.builtin and skill.id == 'ctv-creative-strategy':
        # Campaign requirements belong to the matching skill, not every session.
        from .creative_specs import moloco_ctv_instructions
        content += '\n\n' + moloco_ctv_instructions()
    return {'name': name, 'path': relative, 'content': content}
