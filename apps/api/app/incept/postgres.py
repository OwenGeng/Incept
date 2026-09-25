"""PostgreSQL connection support for the Cloud SQL migration.

The production secret is mounted by Cloud Run as DATABASE_CONFIG_JSON. It is
JSON rather than a URL so passwords never need to be expanded into deploy
commands or checked into local configuration files.
"""

from __future__ import annotations

import json
import os
import re
from contextlib import AbstractContextManager
from functools import lru_cache
from typing import Any

from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def postgres_enabled() -> bool:
    return bool(os.getenv("DATABASE_CONFIG_JSON", "").strip() or os.getenv("DATABASE_URL", "").strip())


def _connection_string() -> str:
    direct_url = os.getenv("DATABASE_URL", "").strip()
    if direct_url:
        return direct_url

    raw = os.getenv("DATABASE_CONFIG_JSON", "").strip()
    if not raw:
        raise RuntimeError("DATABASE_CONFIG_JSON or DATABASE_URL is required for PostgreSQL")
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("DATABASE_CONFIG_JSON must be valid JSON") from exc

    required = ("database", "user", "password")
    missing = [key for key in required if not str(config.get(key, "")).strip()]
    if missing:
        raise RuntimeError(f"DATABASE_CONFIG_JSON is missing: {', '.join(missing)}")

    # When Cloud Run attaches a Cloud SQL instance, the Unix socket is the
    # preferred path. The secret's connection_name is stable and avoids
    # depending on a public IP address.
    connection_name = str(config.get("connection_name", "")).strip()
    socket_dir = os.getenv("INSTANCE_UNIX_SOCKET", "").strip()
    if not socket_dir and os.getenv("K_SERVICE") and connection_name:
        socket_dir = f"/cloudsql/{connection_name}"
    # A local shell may inherit Cloud Run-oriented variables from a deploy
    # session. Use the Unix socket only after Cloud Run has actually mounted
    # it; otherwise fall back to the SSL public-host connection in the secret.
    if socket_dir and not os.path.isdir(socket_dir):
        socket_dir = ""
    host = socket_dir or str(config.get("host", "")).strip()
    if not host:
        raise RuntimeError("DATABASE_CONFIG_JSON must include connection_name or host")

    values = {
        "host": host,
        "port": str(config.get("port", "5432")),
        "dbname": str(config["database"]),
        "user": str(config["user"]),
        "password": str(config["password"]),
        "sslmode": "disable" if host.startswith("/") else "require",
    }
    # Let psycopg/libpq build the connection string. Hand-assembling it can
    # mis-quote a hostname or password, which in turn produces opaque socket
    # errors before a database connection is attempted.
    return make_conninfo(**values)


@lru_cache
def connection_pool() -> ConnectionPool:
    pool_size = max(1, int(os.getenv("DATABASE_POOL_SIZE", "5")))
    max_size = max(pool_size, int(os.getenv("DATABASE_MAX_POOL_SIZE", str(pool_size))))
    return ConnectionPool(
        conninfo=_connection_string(),
        min_size=1,
        max_size=max_size,
        kwargs={"row_factory": dict_row, "connect_timeout": 10},
        timeout=10,
        open=True,
    )


_PRIMARY_KEYS = {
    "jobs": "job_id",
    "threads": "thread_id",
    "assets": "id",
    "theme_create_reports": "report_id",
    "theme_create_presets": "preset_id",
    "video_plans": "plan_id",
    "video_productions": "production_id",
    "video_production_events": "event_id",
    "video_studio_metadata": "record_id",
    "schema_migrations": "migration_id",
}


def _translate_sql(sql: str) -> str:
    """Translate the small SQLite SQL dialect surface used by Incept.

    This is deliberately limited to the existing persistence statements. New
    SQL should use PostgreSQL syntax directly instead of extending this shim.
    """
    normalized = sql.strip()
    if normalized.upper() == "BEGIN IMMEDIATE":
        return "BEGIN"

    replace_match = re.match(r"(\s*)INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\((.*?)\)\s*VALUES", normalized, re.IGNORECASE | re.DOTALL)
    if replace_match:
        table = replace_match.group(2)
        primary_key = _PRIMARY_KEYS.get(table)
        if not primary_key:
            raise RuntimeError(f"No PostgreSQL upsert key registered for {table}")
        columns = [column.strip() for column in replace_match.group(3).split(",")]
        assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in columns if column != primary_key)
        rewritten = re.sub(r"INSERT\s+OR\s+REPLACE", "INSERT", normalized, count=1, flags=re.IGNORECASE)
        return f"{rewritten} ON CONFLICT ({primary_key}) DO UPDATE SET {assignments}".replace("?", "%s")

    ignore_match = re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO\s+(\w+)", normalized, re.IGNORECASE)
    if ignore_match:
        table = ignore_match.group(1)
        primary_key = _PRIMARY_KEYS.get(table, "id")
        rewritten = re.sub(r"INSERT\s+OR\s+IGNORE", "INSERT", normalized, count=1, flags=re.IGNORECASE)
        return f"{rewritten} ON CONFLICT ({primary_key}) DO NOTHING".replace("?", "%s")

    # Incept's current SQL has no PostgreSQL JSON operators, so qmark-style
    # placeholders can be converted without ambiguity during this transition.
    return normalized.replace("?", "%s")


class PostgresConnection(AbstractContextManager["PostgresConnection"]):
    """Small sqlite3-compatible adapter for the existing repository modules."""

    def __init__(self) -> None:
        self._lease: Any | None = None
        self._connection: Any | None = None

    def __enter__(self) -> "PostgresConnection":
        self._lease = connection_pool().connection()
        self._connection = self._lease.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool | None:
        if self._connection is not None:
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()
        if self._lease is not None:
            return self._lease.__exit__(exc_type, exc_value, traceback)
        return None

    def execute(self, sql: str, params: tuple | list | None = None):
        if self._connection is None:
            raise RuntimeError("PostgreSQL connection was not entered")
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(_translate_sql(sql), params)
        return cursor

    def executemany(self, sql: str, params_seq):
        if self._connection is None:
            raise RuntimeError("PostgreSQL connection was not entered")
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.executemany(_translate_sql(sql), params_seq)
        return cursor

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self) -> None:
        if self._connection is not None:
            self._connection.commit()


def check_postgres_ready() -> bool:
    if not postgres_enabled():
        return False
    try:
        with PostgresConnection() as connection:
            return connection.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
    except Exception:
        return False
