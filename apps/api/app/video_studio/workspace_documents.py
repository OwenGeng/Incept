"""Text snapshots and serialized workspace writes shared by editor and Agent."""

from __future__ import annotations

import hashlib
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

from app.incept.postgres import connection_pool, postgres_enabled

TextEncoding = Literal['utf-8', 'utf-8-bom', 'utf-16le', 'utf-16be']
MAX_TEXT_BYTES = 5 * 1024 * 1024
_locks = [threading.RLock() for _ in range(64)]


class DocumentConflict(ValueError):
    pass


@contextmanager
def document_lock(path: Path) -> Iterator[None]:
    digest = hashlib.sha256(str(path.resolve()).encode()).digest()
    with _locks[digest[0] % len(_locks)]:
        if postgres_enabled():
            # Transaction-scoped lock also serializes cooperating Cloud Run
            # instances. No table or infrastructure migration is necessary.
            with connection_pool().connection() as connection:
                connection.execute('SELECT pg_advisory_xact_lock(%s)', (int.from_bytes(digest[:8], signed=True),))
                yield
        else:
            yield


def text_snapshot(path: Path, max_bytes: int = MAX_TEXT_BYTES) -> dict[str, str]:
    if path.stat().st_size > min(max_bytes, MAX_TEXT_BYTES):
        raise OverflowError('文本文件过大，请缩小文件后再编辑')
    raw = path.read_bytes()
    if len(raw) > min(max_bytes, MAX_TEXT_BYTES):
        raise OverflowError('文本文件过大，请缩小文件后再编辑')
    encoding: TextEncoding = 'utf-8'
    content = raw
    codec = 'utf-8'
    for prefix, name, decoder in [(b'\xef\xbb\xbf', 'utf-8-bom', 'utf-8'), (b'\xff\xfe', 'utf-16le', 'utf-16-le'), (b'\xfe\xff', 'utf-16be', 'utf-16-be')]:
        if raw.startswith(prefix):
            encoding, codec, content = name, decoder, raw[len(prefix):]
            break
    try:
        text = content.decode(codec)
    except UnicodeDecodeError as error:
        raise ValueError('文件不是支持的 UTF-8 / UTF-16 文本') from error
    if '\x00' in text:
        raise ValueError('二进制文件不能作为文本编辑')
    return {'text': text, 'revision': hashlib.sha256(raw).hexdigest(), 'encoding': encoding}


def write_document(path: Path, payload: bytes, *, exclusive: bool = False, expected_revision: str | None = None, encoding: TextEncoding | None = None) -> str:
    if expected_revision or encoding:
        if len(payload) > MAX_TEXT_BYTES:
            raise OverflowError('文本文件不能超过 5 MB')
        try:
            text = payload.decode('utf-8')
        except UnicodeDecodeError as error:
            raise ValueError('保存文本必须使用 UTF-8 传输') from error
        if '\x00' in text:
            raise ValueError('二进制文件不能作为文本编辑')
    if encoding:
        try:
            text = payload.decode('utf-8')
        except UnicodeDecodeError as error:
            raise ValueError('保存文本必须使用 UTF-8 传输') from error
        codecs = {'utf-8': ('utf-8', b''), 'utf-8-bom': ('utf-8', b'\xef\xbb\xbf'), 'utf-16le': ('utf-16-le', b'\xff\xfe'), 'utf-16be': ('utf-16-be', b'\xfe\xff')}
        codec, prefix = codecs[encoding]
        payload = prefix + text.encode(codec)
        if len(payload) > MAX_TEXT_BYTES:
            raise OverflowError('编码后的文本文件不能超过 5 MB')
    with document_lock(path):
        if expected_revision:
            if not path.is_file() or path.stat().st_size > MAX_TEXT_BYTES:
                raise DocumentConflict('文件已被删除、移动或变更；当前修改未覆盖，请另存副本或重新载入')
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected_revision:
                raise DocumentConflict('文件已被其他编辑器或 Agent 修改；当前修改未覆盖，请下载副本或重新载入')
        if exclusive and path.exists():
            raise FileExistsError(path.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f'{path.suffix}.{uuid.uuid4().hex}.tmp')
        try:
            temporary.write_bytes(payload)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return hashlib.sha256(payload).hexdigest()
