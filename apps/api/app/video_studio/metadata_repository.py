from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from app.incept.db import _connect
from app.incept.postgres import postgres_enabled


_schema_lock = threading.Lock()
_schema_ready = False


def enabled() -> bool:
    override = os.getenv("VIDEO_STUDIO_METADATA_DATABASE", "").strip().lower()
    if override in {"0", "false", "no"}:
        return False
    return postgres_enabled() or override in {"1", "true", "yes"}


def _ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        with _connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS video_studio_metadata (
                    record_id TEXT PRIMARY KEY,
                    path_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_video_studio_metadata_path "
                "ON video_studio_metadata(path_key)"
            )
        _schema_ready = True


def _record_id(path_key: str) -> str:
    return hashlib.sha256(path_key.encode("utf-8")).hexdigest()


def read(path_key: str) -> Any | None:
    if not enabled():
        return None
    _ensure_schema()
    with _connect() as connection:
        row = connection.execute(
            "SELECT payload_json FROM video_studio_metadata WHERE path_key = ?",
            (path_key,),
        ).fetchone()
    if not row:
        return None
    return json.loads(row["payload_json"])


def write(path_key: str, payload: Any) -> None:
    if not enabled():
        return
    _ensure_schema()
    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO video_studio_metadata
                (record_id, path_key, payload_json, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                _record_id(path_key),
                path_key,
                json.dumps(payload, ensure_ascii=False, default=str),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def delete(path_key: str) -> None:
    if not enabled():
        return
    _ensure_schema()
    with _connect() as connection:
        connection.execute(
            "DELETE FROM video_studio_metadata WHERE path_key = ?",
            (path_key,),
        )


def delete_prefix(path_prefix: str) -> None:
    if not enabled():
        return
    _ensure_schema()
    escaped = path_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with _connect() as connection:
        connection.execute(
            "DELETE FROM video_studio_metadata WHERE path_key = ? OR path_key LIKE ? ESCAPE '\\'",
            (path_prefix, f"{escaped}/%"),
        )
