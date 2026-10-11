"""Bounded, atomic uploads; incoming network streams never hold document locks."""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterable
from pathlib import Path

from .workspace_documents import document_lock


def upload_limit(path: Path) -> int:
    return 450_000_000 if path.suffix.lower() in {'.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v'} else 500 * 1024 * 1024


async def read_bounded(chunks: AsyncIterable[bytes], limit: int) -> bytes:
    payload = bytearray()
    async for chunk in chunks:
        if len(payload) + len(chunk) > limit:
            raise OverflowError('文件超过允许大小；请缩小文件或拆分上传。')
        payload.extend(chunk)
    return bytes(payload)


async def write_stream(path: Path, chunks: AsyncIterable[bytes], *, exclusive: bool = False) -> None:
    limit = upload_limit(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f'{path.suffix}.{uuid.uuid4().hex}.tmp')
    try:
        total = 0
        with temporary.open('xb') as output:
            async for chunk in chunks:
                total += len(chunk)
                if total > limit:
                    raise OverflowError('视频不能超过 450 MB；其他工作区文件不能超过 500 MiB。')
                output.write(chunk)
        with document_lock(path):
            if exclusive and path.exists():
                raise FileExistsError(path.name)
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
