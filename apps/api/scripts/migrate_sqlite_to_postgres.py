"""One-time, idempotent SQLite-to-Cloud-SQL importer for Incept.

Run this from a Cloud Run Job with DATABASE_CONFIG_JSON mounted from Secret
Manager and the Cloud SQL instance attached. Use --dry-run first, then --apply
and finally --verify. The apply step refuses to write if any Incept table
already contains records; it never deletes destination records.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path

from app.incept.db import _connect, init_db
from app.incept.postgres import postgres_enabled

TABLES = (
    "jobs", "threads", "assets", "theme_create_reports", "theme_create_presets",
    "usage_events", "video_plans", "video_productions", "workflows",
    "workflow_revisions", "workflow_runs", "workflow_run_nodes", "workflow_events",
    "workflow_outputs", "workflow_node_cache",
)
PRIMARY_KEYS = {
    "jobs": ("job_id",), "threads": ("thread_id",), "assets": ("id",),
    "theme_create_reports": ("report_id",), "theme_create_presets": ("preset_id",),
    "usage_events": ("id",), "video_plans": ("plan_id",),
    "video_productions": ("production_id",), "workflows": ("workflow_id",),
    "workflow_revisions": ("workflow_id", "revision"), "workflow_runs": ("run_id",),
    "workflow_run_nodes": ("run_id", "node_id"), "workflow_events": ("event_id",),
    "workflow_outputs": ("output_id",), "workflow_node_cache": ("cache_key",),
}


def _source_path(source: str) -> Path:
    if not source.startswith("gs://"):
        return Path(source)
    from google.cloud import storage

    bucket_name, object_name = source[5:].split("/", 1)
    handle = tempfile.NamedTemporaryFile(prefix="incept-sqlite-", suffix=".db", delete=False)
    handle.close()
    destination = Path(handle.name)
    storage.Client().bucket(bucket_name).blob(object_name).download_to_filename(destination)
    return destination


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()]


def _checksum(rows, primary_keys: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: tuple(str(item[key]) for key in primary_keys)):
        digest.update("|".join("" if row[key] is None else str(row[key]) for key in primary_keys).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _upsert_sql(table: str, columns: list[str]) -> str:
    keys = PRIMARY_KEYS[table]
    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in columns if column not in keys)
    return (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)}) "
        f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET {assignments}"
    )


def migrate(source: Path, *, apply: bool, verify: bool) -> int:
    if not postgres_enabled():
        raise RuntimeError("Refusing to run: DATABASE_CONFIG_JSON or DATABASE_URL is not configured")
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as sqlite_db:
        sqlite_db.row_factory = sqlite3.Row
        integrity = sqlite_db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
        source_counts = {
            table: sqlite_db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in TABLES
        }
        for table, count in source_counts.items():
            print(f"{table}: source={count}")
        if not apply and not verify:
            print("Dry run complete: source integrity and row counts verified; destination was not changed.")
            return 0

        if apply:
            init_db()
        with _connect() as target:
            destination_counts = {
                table: target.execute(f"SELECT count(*) AS count FROM {table}").fetchone()["count"]
                for table in TABLES
            }
            if apply:
                occupied = {table: count for table, count in destination_counts.items() if count}
                if occupied:
                    formatted = ", ".join(f"{table}={count}" for table, count in sorted(occupied.items()))
                    raise RuntimeError(
                        "Refusing to import into non-empty Incept tables. "
                        f"Create a separate empty database or investigate first: {formatted}"
                    )
            for table in TABLES:
                columns = _columns(sqlite_db, table)
                source_rows = sqlite_db.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
                print(f"{table}: destination={destination_counts[table]}")
                if apply and source_rows:
                    target.executemany(_upsert_sql(table, columns), [tuple(row[column] for column in columns) for row in source_rows])
                if verify:
                    target_count = target.execute(f"SELECT count(*) AS count FROM {table}").fetchone()["count"]
                    if target_count != len(source_rows):
                        raise RuntimeError(f"{table}: expected {len(source_rows)} rows, found {target_count}")
                    # Primary-key checksums detect missing or duplicate records without logging business data.
                    target_rows = target.execute(f"SELECT {', '.join(PRIMARY_KEYS[table])} FROM {table}").fetchall()
                    source_key_rows = sqlite_db.execute(f"SELECT {', '.join(PRIMARY_KEYS[table])} FROM {table}").fetchall()
                    target_digest = _checksum(target_rows, PRIMARY_KEYS[table])
                    source_digest = _checksum(source_key_rows, PRIMARY_KEYS[table])
                    if target_digest != source_digest:
                        raise RuntimeError(f"{table}: primary-key checksum mismatch")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="SQLite file path or gs://bucket/object")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if sum((args.apply, args.verify, args.dry_run)) != 1:
        parser.error("Choose exactly one of --dry-run, --apply, or --verify")
    source = _source_path(args.source)
    try:
        return migrate(source, apply=args.apply, verify=args.verify)
    finally:
        if args.source.startswith("gs://"):
            source.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
