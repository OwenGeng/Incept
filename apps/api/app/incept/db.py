"""
Lightweight SQLite persistence layer.

All generation jobs and assets are written here so history survives server
restarts. The in-memory dicts in store.py are still the source of truth for
the running process — this module only handles load-on-boot and write-through.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.incept.models import Asset, CreativeThread, GenerationJob, ThemeCreatePreset, ThemeCreateStyleReport

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "incept.db"


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
        """)
        _ensure_column(con, "assets", "asset_role", "TEXT DEFAULT 'generated'")
        _ensure_column(con, "assets", "analysis_json", "TEXT")
        _ensure_column(con, "assets", "thread_id", "TEXT")
        _ensure_column(con, "assets", "parent_asset_id", "TEXT")
        _ensure_column(con, "assets", "root_asset_id", "TEXT")
        _ensure_column(con, "jobs", "thread_id", "TEXT")
        _ensure_column(con, "jobs", "source_asset_id", "TEXT")
        con.executescript("""
            CREATE INDEX IF NOT EXISTS idx_assets_job_id    ON assets(job_id);
            CREATE INDEX IF NOT EXISTS idx_assets_workspace ON assets(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_assets_thread    ON assets(thread_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_workspace   ON jobs(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_thread      ON jobs(thread_id);
            CREATE INDEX IF NOT EXISTS idx_threads_workspace ON threads(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_theme_reports_workspace ON theme_create_reports(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_theme_presets_mode ON theme_create_presets(theme_create_mode);
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


def upsert_thread(thread: CreativeThread) -> None:
    with _connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO threads
               (thread_id, workspace_id, title, generation_mode, created_by,
                origin_asset_id, cover_asset_id, latest_asset_id, latest_job_id,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
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
                thread.created_at.isoformat(),
                thread.updated_at.isoformat(),
            ),
        )


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


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_asset(asset_id: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM assets WHERE id = ?", (asset_id,))


def delete_job(job_id: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))


def delete_thread(thread_id: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))


# ── Read (called once at startup to warm the in-memory store) ─────────────────

def load_jobs() -> list[dict]:
    with _connect() as con:
        return [
            dict(r)
            for r in con.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC"
            ).fetchall()
        ]


def load_threads() -> list[dict]:
    with _connect() as con:
        return [
            dict(r)
            for r in con.execute(
                "SELECT * FROM threads ORDER BY updated_at DESC"
            ).fetchall()
        ]


def load_assets() -> list[dict]:
    with _connect() as con:
        return [
            dict(r)
            for r in con.execute(
                "SELECT * FROM assets ORDER BY created_at DESC"
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
