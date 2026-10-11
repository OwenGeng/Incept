"""Bounded copies with independent canvas identities and node-owned assets."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .store import safe_asset_path
from .workspace_documents import document_lock, write_document

MAX_COPY_FILES = 1000
MAX_COPY_BYTES = 100 * 1024 * 1024


def _read_bounded(path: Path, limit: int) -> bytes:
    with path.open('rb') as source:
        payload = source.read(limit + 1)
    if len(payload) > limit:
        raise ValueError('复制内容不能超过 100 MB')
    return payload


def _publish_locked(target: Path, payload: bytes) -> None:
    # Caller owns target's lock; do not open another PostgreSQL transaction.
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f'{target.suffix}.{uuid.uuid4().hex}.tmp')
    try:
        temporary.write_bytes(payload)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _copy_files(root: Path, source: Path, target: Path, budget: list[int]) -> None:
    if source.is_symlink():
        raise ValueError('不能复制符号链接')
    items = source.rglob('*') if source.is_dir() else iter([source])
    copies: list[tuple[Path, Path]] = []
    for index, item in enumerate(items):
        if index >= MAX_COPY_FILES:
            raise ValueError('复制项目过多，请拆分后重试')
        if item.is_symlink():
            raise ValueError('不能复制符号链接')
        if item.is_dir():
            continue
        if not item.is_file():
            raise ValueError('只能复制普通文件或文件夹')
        destination = target / item.relative_to(source) if source.is_dir() else target
        safe_asset_path(root, str(item.relative_to(root)))
        safe_asset_path(root, str(destination.relative_to(root)))
        budget[0] += 1
        budget[1] += item.stat().st_size
        if budget[0] > MAX_COPY_FILES or budget[1] > MAX_COPY_BYTES:
            raise ValueError('复制内容不能超过 1000 个文件或 100 MB')
        copies.append((item, destination))
    if target.exists():
        raise FileExistsError(target.name)
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=False)
    for item, destination in copies:
        payload = _read_bounded(item, MAX_COPY_BYTES)
        write_document(destination, payload, exclusive=True)


def _remap(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str):
        if value in ids:
            return ids[value]
        normalized = value.replace('\\', '/')
        for previous, current in ids.items():
            prefix = f'assets/{previous}/'
            if normalized.startswith(prefix):
                return f'assets/{current}/{normalized[len(prefix):]}'
        return value
    if isinstance(value, list):
        return [_remap(item, ids) for item in value]
    if isinstance(value, dict):
        return {key: _remap(item, ids) for key, item in value.items()}
    return value


def copy_workspace_file(root: Path, source_path: str, target_path: str) -> None:
    if any(part.is_symlink() for part in [root / source_path, *(root / source_path).parents] if part != root and root in part.parents):
        raise ValueError('不能复制符号链接')
    source = safe_asset_path(root, source_path)
    target = safe_asset_path(root, target_path)
    if source == target or source in target.parents:
        raise ValueError('不能复制到原位置或源目录内部')
    if not source.exists():
        raise FileNotFoundError(source_path)
    # Copying never replaces an existing destination, including empty folders.
    with document_lock(target):
        if target.exists():
            raise FileExistsError(target_path)
        budget = [0, 0]
        canvas: Any = None
        if source.is_file() and source.suffix.lower() == '.json' and source.stat().st_size <= 5 * 1024 * 1024:
            try:
                canvas = json.loads(_read_bounded(source, 5 * 1024 * 1024))
            except (ValueError, UnicodeDecodeError):
                pass
        if not isinstance(canvas, dict) or canvas.get('linglonglabVideoCanvas') is not True:
            # The outer lock already owns target; avoid recursively acquiring a
            # PostgreSQL transaction lock from write_document on the same file.
            if source.is_file():
                if source.stat().st_size > MAX_COPY_BYTES:
                    raise ValueError('复制文件不能超过 100 MB')
                _publish_locked(target, _read_bounded(source, MAX_COPY_BYTES))
            else:
                _copy_files(root, source, target, budget)
            return
        nodes = canvas.get('nodes')
        edges = canvas.get('edges')
        if not isinstance(nodes, list) or not isinstance(edges, list) or len(nodes) > MAX_COPY_FILES:
            raise ValueError('画布结构无效或节点过多')
        ids: dict[str, str] = {}
        for node in nodes:
            if not isinstance(node, dict) or not isinstance(node.get('id'), str) or node['id'] in ids:
                raise ValueError('画布节点 ID 无效或重复')
            owned = safe_asset_path(root, f"assets/{node['id']}")
            if owned.parent != root / 'assets':
                raise ValueError('画布节点 ID 不能作为文件夹名称')
            ids[node['id']] = uuid.uuid4().hex
        for previous, current in ids.items():
            owned = safe_asset_path(root, f'assets/{previous}')
            if owned.is_dir():
                _copy_files(root, owned, safe_asset_path(root, f'assets/{current}'), budget)
        cloned = _remap(canvas, ids)
        for edge in cloned['edges']:
            if not isinstance(edge, dict):
                raise ValueError('画布连线无效')
            edge['id'] = uuid.uuid4().hex
        payload = (json.dumps(cloned, ensure_ascii=False, indent=2) + '\n').encode()
        _publish_locked(target, payload)
