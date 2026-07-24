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
from pathlib import Path

from app.incept.models import Asset, CreativeThread, GenerationJob, ThemeCreatePreset, ThemeCreateStyleReport, VideoGenerationPlan, VideoProduction

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "incept.db"
_GCS_DB_OBJECT = "data/incept.db"
_backup_timer: threading.Timer | None = None
_backup_lock = threading.Lock()


def _get_db_bucket() -> str | None:
    bucket = os.environ.get("INCEPT_ASSET_BUCKET", "").strip()
    return bucket if bucket and bucket != "INCEPT_ASSET_BUCKET" else None


def _get_gcs_client():
    """Use the same explicit project resolution as Studio asset storage."""
    from google.cloud import storage

    from app.incept.config import get_settings

    settings = get_settings()
    return storage.Client(project=settings.gcp_project_id or None)


def restore_db_from_gcs() -> None:
    """Download incept.db from GCS at startup. No-op if bucket not configured or file not found."""
    bucket_name = _get_db_bucket()
    if not bucket_name:
        return
    try:
        client = _get_gcs_client()
        blob = client.bucket(bucket_name).blob(_GCS_DB_OBJECT)
        if not blob.exists():
            logger.info("No DB backup found in GCS — starting fresh: gs://%s/%s", bucket_name, _GCS_DB_OBJECT)
            return
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(_DB_PATH))
        size_kb = _DB_PATH.stat().st_size // 1024
        logger.info("Restored DB from GCS: gs://%s/%s (%d KB)", bucket_name, _GCS_DB_OBJECT, size_kb)
    except Exception:
        logger.warning("Could not restore DB from GCS — starting with local/empty DB", exc_info=True)


def _do_backup_now() -> None:
    bucket_name = _get_db_bucket()
    if not bucket_name or not _DB_PATH.exists():
        return
    try:
        client = _get_gcs_client()
        client.bucket(bucket_name).blob(_GCS_DB_OBJECT).upload_from_filename(str(_DB_PATH))
        logger.debug("DB backed up to GCS: gs://%s/%s", bucket_name, _GCS_DB_OBJECT)
    except Exception:
        logger.warning("Could not back up DB to GCS", exc_info=True)


def _schedule_db_backup() -> None:
    """Debounced GCS backup — uploads 10 s after the last write."""
    global _backup_timer
    with _backup_lock:
        if _backup_timer is not None:
            _backup_timer.cancel()
        _backup_timer = threading.Timer(10.0, _do_backup_now)
        _backup_timer.daemon = True
        _backup_timer.start()


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


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
        """)


def _ensure_column(con: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
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
