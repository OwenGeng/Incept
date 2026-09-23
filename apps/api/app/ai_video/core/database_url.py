"""Build SQLAlchemy URLs for the Cloud SQL PostgreSQL contract used by Incept."""

from __future__ import annotations

import json
import os
from typing import Any

from sqlalchemy.engine import URL


def build_cloud_sql_database_url(database_config_json: str, *, instance_unix_socket: str = "") -> str:
    """Build an asyncpg URL from the Secret Manager JSON used by Incept services.

    The secret has ``database``, ``user``, ``password``, and either a
    ``connection_name`` for Cloud Run's mounted socket or a TLS ``host`` for
    local access. Keeping this parsing here prevents credentials from being
    expanded into a checked-in deployment command.
    """
    try:
        config: dict[str, Any] = json.loads(database_config_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("DATABASE_CONFIG_JSON must be valid JSON") from exc

    required = ("database", "user", "password")
    missing = [key for key in required if not str(config.get(key, "")).strip()]
    if missing:
        raise RuntimeError(f"DATABASE_CONFIG_JSON is missing: {', '.join(missing)}")

    connection_name = str(config.get("connection_name", "")).strip()
    socket_dir = instance_unix_socket.strip() or os.getenv("INSTANCE_UNIX_SOCKET", "").strip()
    if not socket_dir and connection_name:
        # Cloud Run services set K_SERVICE, while Cloud Run Jobs use a
        # different runtime contract. In either case, rely on the actual
        # mounted socket rather than guessing from the execution environment.
        mounted_socket_dir = f"/cloudsql/{connection_name}"
        if os.path.isdir(mounted_socket_dir):
            socket_dir = mounted_socket_dir
    # A local shell can inherit K_SERVICE-adjacent settings. Only use a mounted
    # socket; otherwise defer to the TLS host stored in the deployment secret.
    if socket_dir and not os.path.isdir(socket_dir):
        socket_dir = ""

    host = socket_dir or str(config.get("host", "")).strip()
    if not host:
        raise RuntimeError("DATABASE_CONFIG_JSON must include connection_name or host")

    query: dict[str, str] = {}
    url_host: str | None = host
    if host.startswith("/"):
        url_host = None
        query["host"] = host
    else:
        query["ssl"] = str(config.get("ssl", "require"))

    return str(
        URL.create(
            "postgresql+asyncpg",
            username=str(config["user"]),
            password=str(config["password"]),
            host=url_host,
            port=int(config.get("port", 5432)),
            database=str(config["database"]),
            query=query,
        )
    )
