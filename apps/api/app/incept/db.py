"""
Lightweight SQLite persistence layer.

All generation jobs and assets are written here so history survives server
restarts. The in-memory dicts in store.py are still the source of truth for
the running process — this module only handles load-on-boot and write-through.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.incept.models import Asset, CreativeThread, GenerationJob, ThemeCreatePreset, ThemeCreateStyleReport, VideoGenerationPlan, VideoProduction, VideoProductionEvent
from app.incept.postgres import PostgresConnection, postgres_enabled

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "incept.db"
_GCS_DB_OBJECT = "data/incept.db"
_GCS_DB_SNAPSHOT_PREFIX = "data/backups"
_LOCAL_DB_SNAPSHOT_DIR = _DB_PATH.parent / "backups"
_GCS_SNAPSHOT_INTERVAL = timedelta(hours=1)
_backup_timer: threading.Timer | None = None
_backup_lock = threading.Lock()
# A Cloud Run instance has an ephemeral filesystem.  If its startup restore
# fails, it must never upload the newly-created empty SQLite file back to GCS.
# Otherwise a transient IAM/network failure can overwrite the shared history.
_cloud_restore_unavailable = False

# Video Production persistence changes are recorded independently from the
# historical bootstrap DDL below.  The migrations are additive and idempotent:
# a restored SQLite database from before this feature can be opened safely,
# while a fresh SQLite or Cloud SQL database gets an inspectable version row.
VIDEO_PRODUCTION_SCHEMA_MIGRATIONS: tuple[tuple[str, str], ...] = (
    (
        "2026092201_video_production_events",
        """
        CREATE TABLE IF NOT EXISTS video_production_events (
            event_id       TEXT PRIMARY KEY,
            production_id  TEXT NOT NULL,
            workspace_id   TEXT NOT NULL DEFAULT '',
            event_type     TEXT NOT NULL,
            summary        TEXT NOT NULL DEFAULT '',
            state_revision INTEGER NOT NULL,
            actor_user_id  TEXT NOT NULL DEFAULT 'system',
            metadata_json  TEXT NOT NULL DEFAULT '{}',
            created_at     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_video_production_events_production
            ON video_production_events(production_id, created_at DESC);
        """,
    ),
)


def _get_db_bucket() -> str | None:
    bucket = os.environ.get("INCEPT_ASSET_BUCKET", "").strip()
    return bucket if bucket and bucket != "INCEPT_ASSET_BUCKET" else None


def _is_cloud_run() -> bool:
    """Whether this process is running in a Cloud Run service instance."""
    return bool(os.environ.get("K_SERVICE"))


def _get_gcs_client():
    """Use the same explicit project resolution as Studio asset storage."""
    from google.cloud import storage

    from app.incept.config import get_settings

    settings = get_settings()
    return storage.Client(project=settings.gcp_project_id or None)


def _validate_sqlite_candidate(path: Path) -> int:
    """Validate a restored SQLite DB and return a small persisted-data score."""
    with sqlite3.connect(str(path)) as candidate:
        integrity = candidate.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise ValueError(f"SQLite integrity check failed: {integrity!r}")
        tables = {
            row[0]
            for row in candidate.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        if not {"assets", "threads", "jobs"}.issubset(tables):
            raise ValueError("SQLite candidate is missing required Incept tables")
        score = 0
        for table in ("assets", "threads", "video_productions", "jobs"):
            if table in tables:
                score += int(candidate.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        return score


def _download_candidate(blob) -> tuple[Path, int]:
    """Download one GCS DB object to a validated temporary SQLite file."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="incept-restore-", suffix=".db", dir=_DB_PATH.parent, delete=False) as handle:
        candidate_path = Path(handle.name)
    try:
        blob.download_to_filename(str(candidate_path))
        return candidate_path, _validate_sqlite_candidate(candidate_path)
    except Exception:
        candidate_path.unlink(missing_ok=True)
        raise


def _gcs_snapshot_blobs(bucket) -> list:
    """Newest-first immutable SQLite backups, used only as recovery fallback."""
    snapshots = [
        blob
        for blob in bucket.list_blobs(prefix=f"{_GCS_DB_SNAPSHOT_PREFIX}/incept-")
        if blob.name.endswith(".db")
    ]
    return sorted(snapshots, key=lambda blob: blob.time_created or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def restore_db_from_gcs() -> None:
    """Restore the shared DB only for a fresh local runtime.

    A hot-reloaded local API already has its newest SQLite state on disk. The
    previous unconditional download could replace that state with an older GCS
    snapshot and make recent Production history disappear. GCS remains the
    bootstrap source for an empty/ephemeral runtime; it must not overwrite an
    existing local database during a restart.
    """
    if postgres_enabled():
        return
    # Local development intentionally keeps the local state on a hot reload.
    # On Cloud Run, however, a non-empty DB can be baked into the image or left
    # by a prior request inside an ephemeral instance; GCS is authoritative.
    if not _is_cloud_run() and _DB_PATH.exists() and _DB_PATH.stat().st_size > 0:
        logger.info("Keeping existing local Incept database; skipping GCS startup restore: %s", _DB_PATH)
        return
    bucket_name = _get_db_bucket()
    if not bucket_name:
        return
    try:
        client = _get_gcs_client()
        bucket = client.bucket(bucket_name)
        canonical = bucket.blob(_GCS_DB_OBJECT)
        candidates: list[tuple[object, str]] = []
        if canonical.exists():
            candidates.append((canonical, "canonical"))
        candidates.extend((blob, "immutable snapshot") for blob in _gcs_snapshot_blobs(bucket))
        if not candidates:
            logger.info("No DB backup found in GCS — starting fresh: gs://%s/%s", bucket_name, _GCS_DB_OBJECT)
            return

        restored: tuple[Path, int, str] | None = None
        for blob, source in candidates:
            try:
                candidate_path, score = _download_candidate(blob)
                # A valid but empty canonical DB is not trusted when an
                # immutable snapshot with real project metadata exists.
                if restored is None or score > restored[1]:
                    if restored is not None:
                        restored[0].unlink(missing_ok=True)
                    restored = (candidate_path, score, source)
                else:
                    candidate_path.unlink(missing_ok=True)
                if source == "canonical" and score > 0:
                    break
            except Exception:
                logger.warning("Skipping invalid %s Incept DB candidate: gs://%s/%s", source, bucket_name, blob.name, exc_info=True)

        if restored is None:
            raise RuntimeError("No valid Incept database candidate could be restored from GCS")
        candidate_path, score, source = restored
        try:
            os.replace(candidate_path, _DB_PATH)
        finally:
            candidate_path.unlink(missing_ok=True)
        size_kb = _DB_PATH.stat().st_size // 1024
        logger.info("Restored Incept DB from GCS %s (%d KB, metadata score=%d)", source, size_kb, score)
    except Exception:
        global _cloud_restore_unavailable
        if _is_cloud_run():
            _cloud_restore_unavailable = True
        logger.warning("Could not restore DB from GCS — starting with local/empty DB", exc_info=True)


def _backup_local_db_daily() -> Path | None:
    """Create one immutable, SQLite-consistent local snapshot per UTC day.

    The production database must remain recoverable even when a developer
    restarts the API without GCS access.  SQLite's backup API provides a
    consistent copy while the application is writing; a temporary file plus
    atomic replace ensures an interrupted backup never appears valid.
    """
    if not _DB_PATH.exists() or _DB_PATH.stat().st_size == 0:
        return None
    snapshot_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_path = _LOCAL_DB_SNAPSHOT_DIR / f"incept-{snapshot_day}.db"
    if snapshot_path.exists() and snapshot_path.stat().st_size > 0:
        return snapshot_path
    _LOCAL_DB_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f"incept-{snapshot_day}-",
        suffix=".db.tmp",
        dir=_LOCAL_DB_SNAPSHOT_DIR,
        delete=False,
    ) as handle:
        candidate_path = Path(handle.name)
    try:
        with sqlite3.connect(str(_DB_PATH)) as source, sqlite3.connect(str(candidate_path)) as destination:
            source.backup(destination)
            destination.execute("PRAGMA integrity_check").fetchone()
        # Do not overwrite an existing daily recovery point created by another
        # process. The first valid snapshot of the day is deliberately frozen.
        if not snapshot_path.exists():
            os.replace(candidate_path, snapshot_path)
            logger.info("Created immutable local Incept DB snapshot: %s", snapshot_path)
        return snapshot_path
    except Exception:
        logger.warning("Could not create local Incept database snapshot", exc_info=True)
        return None
    finally:
        candidate_path.unlink(missing_ok=True)


def _latest_gcs_snapshot_at(bucket) -> datetime | None:
    """Return the newest immutable application snapshot, if it can be listed."""
    latest: datetime | None = None
    for blob in bucket.list_blobs(prefix=f"{_GCS_DB_SNAPSHOT_PREFIX}/incept-"):
        if not blob.name.endswith(".db") or blob.time_created is None:
            continue
        created_at = blob.time_created.astimezone(timezone.utc)
        if latest is None or created_at > latest:
            latest = created_at
    return latest


def _do_backup_now() -> None:
    if postgres_enabled():
        return
    _backup_local_db_daily()
    bucket_name = _get_db_bucket()
    if not bucket_name or not _DB_PATH.exists():
        return
    if _is_cloud_run() and _cloud_restore_unavailable:
        logger.error("Refusing to upload Incept DB: Cloud Run startup restore failed, so this instance may only contain an empty database")
        return
    try:
        client = _get_gcs_client()
        bucket = client.bucket(bucket_name)
        bucket.blob(_GCS_DB_OBJECT).upload_from_filename(str(_DB_PATH))
        # Keep an application-level immutable recovery point even when Bucket
        # Object Versioning has not been enabled. Canonical state is updated on
        # writes; immutable GCS recovery points are intentionally limited to
        # one per hour so normal generation activity does not create an
        # unbounded number of duplicate database files.
        now = datetime.now(timezone.utc)
        latest_snapshot_at = _latest_gcs_snapshot_at(bucket)
        if latest_snapshot_at is None or now - latest_snapshot_at >= _GCS_SNAPSHOT_INTERVAL:
            snapshot_name = (
                f"{_GCS_DB_SNAPSHOT_PREFIX}/incept-"
                f"{now.strftime('%Y%m%dT%H%M%S.%fZ')}.db"
            )
            bucket.blob(snapshot_name).upload_from_filename(str(_DB_PATH))
            logger.info("Backed up Incept database to %s and %s", _GCS_DB_OBJECT, snapshot_name)
        else:
            logger.info(
                "Backed up Incept database to %s; immutable GCS snapshot not due until one hour after %s",
                _GCS_DB_OBJECT,
                latest_snapshot_at.isoformat(),
            )
        logger.debug("DB backed up to GCS: gs://%s/%s", bucket_name, _GCS_DB_OBJECT)
    except Exception:
        logger.warning("Could not back up DB to GCS", exc_info=True)


def _schedule_db_backup() -> None:
    """Debounced GCS backup — uploads 10 s after the last write."""
    if postgres_enabled():
        return
    global _backup_timer
    with _backup_lock:
        if _backup_timer is not None:
            _backup_timer.cancel()
        _backup_timer = threading.Timer(10.0, _do_backup_now)
        _backup_timer.daemon = True
        _backup_timer.start()


def _connect() -> sqlite3.Connection | PostgresConnection:
    if postgres_enabled():
        return PostgresConnection()
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def _apply_video_production_schema_migrations(con: sqlite3.Connection | PostgresConnection) -> None:
    """Apply known additive Video Production migrations exactly once.

    This does not attempt destructive down-migrations. Recovery of an
    accidental deployment rollback remains the already-supported immutable
    SQLite/GCS backup path or a Cloud SQL point-in-time restore, both of which
    retain the prior schema and data together.
    """

    con.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )"""
    )
    applied = {
        row["migration_id"]
        for row in con.execute("SELECT migration_id FROM schema_migrations").fetchall()
    }
    for migration_id, statement in VIDEO_PRODUCTION_SCHEMA_MIGRATIONS:
        if migration_id in applied:
            continue
        con.executescript(statement)
        con.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            (migration_id, datetime.now(timezone.utc).isoformat()),
        )


def video_production_schema_migration_status() -> dict[str, object]:
    """Return the expected and applied additive migration ids for health checks."""

    expected = [migration_id for migration_id, _statement in VIDEO_PRODUCTION_SCHEMA_MIGRATIONS]
    with _connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )"""
        )
        applied = [
            str(row["migration_id"])
            for row in con.execute("SELECT migration_id FROM schema_migrations ORDER BY migration_id").fetchall()
        ]
    missing = [migration_id for migration_id in expected if migration_id not in applied]
    return {"expected": expected, "applied": applied, "missing": missing, "ready": not missing}


def init_db() -> None:
    """Create tables if they don't exist. Call once at startup."""
    with _connect() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id           TEXT PRIMARY KEY,
                workspace_id     TEXT NOT NULL DEFAULT '',
                status           TEXT NOT NULL DEFAULT 'completed',
                progress         INTEGER DEFAULT 100,
                lineage_key      TEXT DEFAULT '',
                message          TEXT DEFAULT '',
                tool_id          TEXT DEFAULT '',
                title            TEXT DEFAULT '',
                output_asset_ids TEXT DEFAULT '[]',
                thread_id        TEXT,
                source_asset_id  TEXT,
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS threads (
                thread_id        TEXT PRIMARY KEY,
                workspace_id     TEXT NOT NULL DEFAULT '',
                title            TEXT DEFAULT '',
                generation_mode  TEXT DEFAULT 'free_create',
                created_by       TEXT DEFAULT '',
                origin_asset_id  TEXT,
                cover_asset_id   TEXT,
                latest_asset_id  TEXT,
                latest_job_id    TEXT,
                messages_json    TEXT NOT NULL DEFAULT '[]',
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS assets (
                id           TEXT PRIMARY KEY,
                title        TEXT DEFAULT '',
                type         TEXT DEFAULT 'image',
                gcs_uri      TEXT DEFAULT '',
                preview_url  TEXT DEFAULT '',
                provider     TEXT DEFAULT '',
                model        TEXT DEFAULT '',
                workspace_id TEXT DEFAULT '',
                job_id       TEXT DEFAULT '',
                prompt_hash  TEXT DEFAULT '',
                created_by   TEXT DEFAULT '',
                created_at   TEXT NOT NULL,
                width        INTEGER,
                height       INTEGER,
                theme        TEXT,
                asset_role   TEXT DEFAULT 'generated',
                analysis_json TEXT,
                thread_id    TEXT,
                parent_asset_id TEXT,
                root_asset_id   TEXT
            );

            CREATE TABLE IF NOT EXISTS theme_create_reports (
                report_id        TEXT PRIMARY KEY,
                workspace_id     TEXT NOT NULL DEFAULT '',
                title            TEXT DEFAULT '',
                summary          TEXT DEFAULT '',
                theme_create_mode TEXT DEFAULT 'style_modify',
                prompt_template  TEXT DEFAULT '',
                source_asset_id  TEXT,
                reference_asset_ids TEXT DEFAULT '[]',
                source_job_id    TEXT,
                recommended_preset_name TEXT,
                visual_dna_json  TEXT DEFAULT '[]',
                composition_rules_json TEXT DEFAULT '[]',
                do_not_copy_json TEXT DEFAULT '[]',
                tags_json        TEXT DEFAULT '[]',
                taxonomy_json    TEXT DEFAULT '{}',
                created_by       TEXT DEFAULT '',
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS theme_create_presets (
                preset_id        TEXT PRIMARY KEY,
                name             TEXT DEFAULT '',
                description      TEXT DEFAULT '',
                theme_create_mode TEXT DEFAULT 'style_modify',
                visibility       TEXT DEFAULT 'team',
                prompt_template  TEXT DEFAULT '',
                style_name       TEXT,
                style_details    TEXT,
                workspace_id     TEXT,
                tags_json        TEXT DEFAULT '[]',
                taxonomy_json    TEXT DEFAULT '{}',
                source_report_id TEXT,
                source_job_id    TEXT,
                source_asset_id  TEXT,
                created_by       TEXT DEFAULT '',
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL,
                usage_count      INTEGER DEFAULT 0,
                is_official      INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS usage_events (
                id                              TEXT PRIMARY KEY,
                job_id                          TEXT DEFAULT '',
                workspace_id                    TEXT DEFAULT '',
                user_id                         TEXT DEFAULT '',
                user_email                      TEXT DEFAULT '',
                provider                        TEXT DEFAULT '',
                model                           TEXT DEFAULT '',
                operation                       TEXT DEFAULT '',
                prompt_hash                     TEXT DEFAULT '',
                variants                        INTEGER DEFAULT 0,
                output_size_count               INTEGER DEFAULT 0,
                output_format                   TEXT DEFAULT '',
                estimated_provider_generations  INTEGER DEFAULT 0,
                output_asset_count              INTEGER DEFAULT 0,
                estimated_cost_usd              REAL DEFAULT 0,
                actual_cost_usd                 REAL,
                input_tokens                    INTEGER,
                output_tokens                   INTEGER,
                created_at                      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS video_plans (
                plan_id       TEXT PRIMARY KEY,
                workspace_id  TEXT NOT NULL DEFAULT '',
                thread_id     TEXT NOT NULL DEFAULT '',
                created_by    TEXT NOT NULL DEFAULT '',
                payload_json  TEXT NOT NULL DEFAULT '{}',
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS video_productions (
                production_id TEXT PRIMARY KEY,
                workspace_id  TEXT NOT NULL DEFAULT '',
                created_by    TEXT NOT NULL DEFAULT '',
                payload_json  TEXT NOT NULL DEFAULT '{}',
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS playable_projects (
                project_id         TEXT PRIMARY KEY,
                workspace_id       TEXT NOT NULL,
                owner_user_id      TEXT NOT NULL,
                title              TEXT NOT NULL,
                schema_json        TEXT NOT NULL,
                source_template_id TEXT,
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS playable_copilot_sessions (
                session_id     TEXT PRIMARY KEY,
                workspace_id   TEXT NOT NULL,
                owner_user_id  TEXT NOT NULL,
                title          TEXT NOT NULL,
                messages_json  TEXT NOT NULL DEFAULT '[]',
                proposal_json  TEXT NOT NULL DEFAULT '{}',
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS playable_templates (
                template_id        TEXT PRIMARY KEY,
                workspace_id      TEXT NOT NULL,
                owner_user_id     TEXT NOT NULL,
                owner_name        TEXT NOT NULL DEFAULT '',
                title             TEXT NOT NULL,
                description       TEXT NOT NULL DEFAULT '',
                visibility        TEXT NOT NULL DEFAULT 'private',
                category          TEXT NOT NULL DEFAULT 'merge',
                version           INTEGER NOT NULL DEFAULT 1,
                schema_json       TEXT NOT NULL,
                asset_policy      TEXT NOT NULL DEFAULT 'slots_only',
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS playable_template_favorites (
                template_id TEXT NOT NULL,
                user_id     TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                PRIMARY KEY (template_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS playable_template_forks (
                fork_id     TEXT PRIMARY KEY,
                template_id TEXT NOT NULL,
                project_id  TEXT NOT NULL,
                owner_user_id TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
        """)
        _ensure_column(con, "assets", "asset_role", "TEXT DEFAULT 'generated'")
        _ensure_column(con, "assets", "analysis_json", "TEXT")
        _ensure_column(con, "assets", "thread_id", "TEXT")
        _ensure_column(con, "assets", "parent_asset_id", "TEXT")
        _ensure_column(con, "assets", "root_asset_id", "TEXT")
        _ensure_column(con, "jobs", "thread_id", "TEXT")
        _ensure_column(con, "jobs", "source_asset_id", "TEXT")
        _ensure_column(con, "threads", "messages_json", "TEXT NOT NULL DEFAULT '[]'")
        con.executescript("""
            CREATE INDEX IF NOT EXISTS idx_assets_job_id    ON assets(job_id);
            CREATE INDEX IF NOT EXISTS idx_assets_workspace ON assets(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_assets_thread    ON assets(thread_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_workspace   ON jobs(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_thread      ON jobs(thread_id);
            CREATE INDEX IF NOT EXISTS idx_threads_workspace ON threads(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_theme_reports_workspace ON theme_create_reports(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_theme_presets_mode ON theme_create_presets(theme_create_mode);
            CREATE INDEX IF NOT EXISTS idx_video_plans_thread ON video_plans(thread_id);
            CREATE INDEX IF NOT EXISTS idx_video_productions_workspace ON video_productions(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_video_productions_creator ON video_productions(created_by);
            CREATE INDEX IF NOT EXISTS idx_playable_projects_owner ON playable_projects(workspace_id, owner_user_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_playable_copilot_sessions_owner ON playable_copilot_sessions(workspace_id, owner_user_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_playable_templates_visibility ON playable_templates(workspace_id, visibility, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_playable_template_forks_template ON playable_template_forks(template_id);

            CREATE TABLE IF NOT EXISTS workflows (
                workflow_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                title TEXT NOT NULL,
                template TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                revision INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workflows_workspace ON workflows(workspace_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS workflow_revisions (
                workflow_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (workflow_id, revision)
            );

            CREATE TABLE IF NOT EXISTS workflow_runs (
                run_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                status TEXT NOT NULL,
                requested_output_node_ids TEXT NOT NULL DEFAULT '[]',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow ON workflow_runs(workflow_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS workflow_run_nodes (
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                node_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                result_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (run_id, node_id)
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_run_nodes_status ON workflow_run_nodes(status, updated_at ASC);

            CREATE TABLE IF NOT EXISTS workflow_events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                node_id TEXT,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                progress INTEGER,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_events_run ON workflow_events(run_id, created_at ASC);

            CREATE TABLE IF NOT EXISTS workflow_outputs (
                output_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                output_type TEXT NOT NULL,
                value_id TEXT NOT NULL,
                created_by TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_outputs_workflow ON workflow_outputs(workflow_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_workflow_outputs_run ON workflow_outputs(run_id, node_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_outputs_run_node_value
                ON workflow_outputs(run_id, node_id, value_id);

            CREATE TABLE IF NOT EXISTS workflow_node_cache (
                cache_key TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                node_type TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_node_cache_workspace ON workflow_node_cache(workspace_id, node_type, updated_at DESC);
        """)
        _ensure_column(con, "workflow_runs", "priority", "INTEGER NOT NULL DEFAULT 0")
        con.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_queue ON workflow_runs(status, priority DESC, created_at ASC)")
        _apply_video_production_schema_migrations(con)
    if not postgres_enabled():
        _backup_local_db_daily()


def _ensure_column(con: sqlite3.Connection | PostgresConnection, table: str, column: str, ddl: str) -> None:
    if postgres_enabled():
        con.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
        return
    columns = {
        row["name"]
        for row in con.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


# ── Write ──────────────────────────────────────────────────────────────────────

def upsert_job(job: GenerationJob) -> None:
    with _connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO jobs
               (job_id, workspace_id, status, progress, lineage_key, message,
                tool_id, title, output_asset_ids, thread_id, source_asset_id,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job.job_id,
                job.workspace_id,
                job.status.value,
                job.progress,
                job.lineage_key,
                job.message,
                job.tool_id,
                job.title,
                json.dumps(job.output_asset_ids),
                job.thread_id,
                job.source_asset_id,
                job.created_at.isoformat(),
                job.updated_at.isoformat(),
            ),
        )
    _schedule_db_backup()


def upsert_thread(thread: CreativeThread) -> None:
    with _connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO threads
               (thread_id, workspace_id, title, generation_mode, created_by,
                origin_asset_id, cover_asset_id, latest_asset_id, latest_job_id,
                messages_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                thread.thread_id,
                thread.workspace_id,
                thread.title,
                thread.generation_mode.value,
                thread.created_by,
                thread.origin_asset_id,
                thread.cover_asset_id,
                thread.latest_asset_id,
                thread.latest_job_id,
                json.dumps([message.model_dump(mode="json") for message in thread.messages]),
                thread.created_at.isoformat(),
                thread.updated_at.isoformat(),
            ),
        )
    _schedule_db_backup()


def upsert_asset(asset: Asset) -> None:
    with _connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO assets
               (id, title, type, gcs_uri, preview_url, provider, model,
                workspace_id, job_id, prompt_hash, created_by, created_at,
                width, height, theme, asset_role, analysis_json, thread_id,
                parent_asset_id, root_asset_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                asset.id,
                asset.title,
                asset.type,
                asset.gcs_uri,
                asset.preview_url,
                asset.provider,
                asset.model,
                asset.workspace_id,
                asset.job_id,
                asset.prompt_hash,
                asset.created_by,
                asset.created_at.isoformat(),
                asset.width,
                asset.height,
                asset.theme,
                asset.asset_role.value,
                json.dumps(asset.analysis) if asset.analysis is not None else None,
                asset.thread_id,
                asset.parent_asset_id,
                asset.root_asset_id,
            ),
        )
    _schedule_db_backup()


def upsert_theme_create_report(report: ThemeCreateStyleReport) -> None:
    with _connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO theme_create_reports
               (report_id, workspace_id, title, summary, theme_create_mode,
                prompt_template, source_asset_id, reference_asset_ids, source_job_id,
                recommended_preset_name, visual_dna_json, composition_rules_json,
                do_not_copy_json, tags_json, taxonomy_json, created_by, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                report.report_id,
                report.workspace_id,
                report.title,
                report.summary,
                report.theme_create_mode.value,
                report.prompt_template,
                report.source_asset_id,
                json.dumps(report.reference_asset_ids),
                report.source_job_id,
                report.recommended_preset_name,
                json.dumps(report.visual_dna),
                json.dumps(report.composition_rules),
                json.dumps(report.do_not_copy),
                json.dumps(report.tags),
                json.dumps(report.taxonomy),
                report.created_by,
                report.created_at.isoformat(),
                report.updated_at.isoformat(),
            ),
        )
    _schedule_db_backup()


def upsert_theme_create_preset(preset: ThemeCreatePreset) -> None:
    with _connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO theme_create_presets
               (preset_id, name, description, theme_create_mode, visibility,
                prompt_template, style_name, style_details, workspace_id,
                tags_json, taxonomy_json, source_report_id, source_job_id, source_asset_id,
                created_by, created_at, updated_at, usage_count, is_official)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                preset.preset_id,
                preset.name,
                preset.description,
                preset.theme_create_mode.value,
                preset.visibility.value,
                preset.prompt_template,
                preset.style_name,
                preset.style_details,
                preset.workspace_id,
                json.dumps(preset.tags),
                json.dumps(preset.taxonomy),
                preset.source_report_id,
                preset.source_job_id,
                preset.source_asset_id,
                preset.created_by,
                preset.created_at.isoformat(),
                preset.updated_at.isoformat(),
                preset.usage_count,
                1 if preset.is_official else 0,
            ),
        )
    _schedule_db_backup()


def upsert_video_plan(plan: VideoGenerationPlan) -> None:
    with _connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO video_plans
               (plan_id, workspace_id, thread_id, created_by, payload_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                plan.plan_id,
                plan.workspace_id,
                plan.thread_id,
                plan.created_by,
                json.dumps(plan.model_dump(mode="json")),
                plan.created_at.isoformat(),
                plan.updated_at.isoformat(),
            ),
        )
    _schedule_db_backup()


def upsert_video_production(production: VideoProduction) -> None:
    with _connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO video_productions
               (production_id, workspace_id, created_by, payload_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (
                production.production_id,
                production.workspace_id,
                production.created_by,
                json.dumps(production.model_dump(mode="json")),
                production.created_at.isoformat(),
                production.updated_at.isoformat(),
            ),
        )
    _schedule_db_backup()


def upsert_video_production_event(event: VideoProductionEvent) -> None:
    with _connect() as con:
        con.execute(
            """INSERT OR IGNORE INTO video_production_events
               (event_id, production_id, workspace_id, event_type, summary,
                state_revision, actor_user_id, metadata_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                event.event_id,
                event.production_id,
                event.workspace_id,
                event.event_type,
                event.summary,
                event.state_revision,
                event.actor_user_id,
                json.dumps(event.metadata),
                event.created_at.isoformat(),
            ),
        )
    _schedule_db_backup()


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_asset(asset_id: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
    _schedule_db_backup()


def delete_job(job_id: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
    _schedule_db_backup()


def delete_thread(thread_id: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
        con.execute("DELETE FROM video_plans WHERE thread_id = ?", (thread_id,))
    _schedule_db_backup()


def delete_video_production(production_id: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM video_productions WHERE production_id = ?", (production_id,))
        con.execute("DELETE FROM video_production_events WHERE production_id = ?", (production_id,))
    _schedule_db_backup()


def upsert_usage_event(event) -> None:
    with _connect() as con:
        con.execute(
            """INSERT OR IGNORE INTO usage_events
               (id, job_id, workspace_id, user_id, user_email, provider, model,
                operation, prompt_hash, variants, output_size_count, output_format,
                estimated_provider_generations, output_asset_count,
                estimated_cost_usd, actual_cost_usd, input_tokens, output_tokens,
                created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event.id, event.job_id, event.workspace_id,
                event.user_id, event.user_email, event.provider, event.model,
                event.operation, event.prompt_hash, event.variants,
                event.output_size_count, event.output_format,
                event.estimated_provider_generations, event.output_asset_count,
                event.estimated_cost_usd, event.actual_cost_usd,
                event.input_tokens, event.output_tokens,
                event.created_at.isoformat(),
            ),
        )
    _schedule_db_backup()


# ── Read (called once at startup to warm the in-memory store) ─────────────────

def load_jobs() -> list[dict]:
    with _connect() as con:
        return [
            dict(r)
            for r in con.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC"
            ).fetchall()
        ]


def load_job(job_id: str) -> dict | None:
    """Fetch the latest persisted state for one job.

    Long-running capture jobs may finish on a different Cloud Run instance
    than the one serving the browser's polling request.
    """
    with _connect() as con:
        row = con.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    return dict(row) if row else None


def load_threads() -> list[dict]:
    with _connect() as con:
        return [
            dict(r)
            for r in con.execute(
                "SELECT * FROM threads ORDER BY updated_at DESC"
            ).fetchall()
        ]


def load_video_plans(thread_id: str | None = None) -> list[dict]:
    with _connect() as con:
        if thread_id:
            rows = con.execute(
                "SELECT * FROM video_plans WHERE thread_id = ? ORDER BY updated_at DESC",
                (thread_id,),
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM video_plans ORDER BY updated_at DESC").fetchall()
    return [dict(row) for row in rows]


def load_video_productions(workspace_id: str | None = None) -> list[dict]:
    with _connect() as con:
        if workspace_id:
            rows = con.execute(
                "SELECT * FROM video_productions WHERE workspace_id = ? ORDER BY updated_at DESC",
                (workspace_id,),
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM video_productions ORDER BY updated_at DESC").fetchall()
    return [dict(row) for row in rows]


def load_video_production_events(production_id: str, limit: int = 80) -> list[dict]:
    safe_limit = max(1, min(int(limit), 200))
    with _connect() as con:
        rows = con.execute(
            """SELECT * FROM video_production_events
               WHERE production_id = ? ORDER BY created_at DESC LIMIT ?""",
            (production_id, safe_limit),
        ).fetchall()
    return [dict(row) for row in rows]


def load_assets() -> list[dict]:
    with _connect() as con:
        return [
            dict(r)
            for r in con.execute(
                "SELECT * FROM assets ORDER BY created_at DESC"
            ).fetchall()
        ]


def load_usage_events() -> list[dict]:
    with _connect() as con:
        return [
            dict(r)
            for r in con.execute(
                "SELECT * FROM usage_events ORDER BY created_at DESC"
            ).fetchall()
        ]


def load_theme_create_reports() -> list[dict]:
    with _connect() as con:
        return [
            dict(r)
            for r in con.execute(
                "SELECT * FROM theme_create_reports ORDER BY updated_at DESC"
            ).fetchall()
        ]


def load_theme_create_presets() -> list[dict]:
    with _connect() as con:
        return [
            dict(r)
            for r in con.execute(
                "SELECT * FROM theme_create_presets ORDER BY is_official DESC, updated_at DESC"
            ).fetchall()
        ]
