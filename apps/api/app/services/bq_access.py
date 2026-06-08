from __future__ import annotations

import logging
import threading
import time
from typing import Any

from google.cloud import bigquery

from app.core.config import settings

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[dict[str, Any] | None, float]] = {}
_cache_ttl = 300  # 5 min
_lock = threading.Lock()


def _invalidate(email: str | None = None) -> None:
    """Purge one or all entries from the in-memory cache."""
    with _lock:
        if email:
            _cache.pop(email, None)
        else:
            _cache.clear()


class BQAccessService:
    def __init__(self) -> None:
        project = (
            settings.bq_write_project
            or settings.gcp_project_deploy
            or settings.google_cloud_project
            or ""
        )
        self.client = bigquery.Client(project=project or None)
        # Use the same resolved project for both the client AND the table reference
        self._project = project
        self._dataset = settings.bq_dataset_config  # default: "config"
        self._table_id = f"{project}.{self._dataset}.users"
        self._table_ref = f"`{self._table_id}`"
        self._ensure_table()

    def _ensure_table(self) -> None:
        """
        Create the config dataset and users table if they don't exist.
        Called once at service init so list_users / upsert_user never hit 404.
        Schema: email STRING, role STRING, allowed_projects ARRAY<STRING>
        """
        if not self._project:
            logger.warning("[bq_access] No project configured — skipping table auto-creation.")
            return

        # 1. Ensure dataset exists
        dataset_ref = bigquery.DatasetReference(self._project, self._dataset)
        try:
            self.client.get_dataset(dataset_ref)
            logger.debug("[bq_access] Dataset %s:%s already exists.", self._project, self._dataset)
        except Exception:
            logger.info("[bq_access] Creating dataset %s:%s …", self._project, self._dataset)
            try:
                ds = bigquery.Dataset(dataset_ref)
                ds.location = "US"
                self.client.create_dataset(ds, exists_ok=True)
                logger.info("[bq_access] Dataset created.")
            except Exception as exc:
                logger.error("[bq_access] Could not create dataset: %s", exc)
                return  # give up — queries will fail but won't crash __init__

        # 2. Ensure users table exists
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self._table_id}`
        (
          email              STRING  NOT NULL,
          role               STRING  NOT NULL,
          allowed_projects   ARRAY<STRING>
        )
        """
        try:
            self.client.query(ddl).result()
            logger.info("[bq_access] users table ready at %s", self._table_id)
        except Exception as exc:
            logger.error("[bq_access] Could not create users table: %s", exc)

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_user_record(self, email: str) -> dict[str, Any] | None:
        now = time.monotonic()
        with _lock:
            if email in _cache:
                record, ts = _cache[email]
                if now - ts < _cache_ttl:
                    return record

        record = self._query_one(email)

        with _lock:
            _cache[email] = (record, now)

        return record

    def list_users(self) -> list[dict[str, Any]]:
        sql = f"SELECT email, role, allowed_projects FROM {self._table_ref} ORDER BY role, email"
        logger.info("list_users querying: %s", self._table_id)
        rows = list(self.client.query(sql).result())
        result = []
        for row in rows:
            ap = list(row["allowed_projects"]) if row["allowed_projects"] else []
            result.append({
                "email": row["email"],
                "role": row["role"],
                "routing_bucket": ap[0] if len(ap) > 0 else None,
                "agency_company": ap[1] if len(ap) > 1 else None,
            })
        return result

    def _query_one(self, email: str) -> dict[str, Any] | None:
        sql = f"SELECT role, allowed_projects FROM {self._table_ref} WHERE email = @email LIMIT 1"
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("email", "STRING", email)]
        )
        rows = list(self.client.query(sql, job_config=job_config).result())
        if not rows:
            return None
        row = rows[0]
        return {
            "role": row["role"],
            "allowed_projects": list(row["allowed_projects"]) if row["allowed_projects"] else None,
        }

    # ── Write ──────────────────────────────────────────────────────────────────

    def upsert_user(
        self,
        email: str,
        role: str,
        routing_bucket: str | None = None,
        agency_company: str | None = None,
    ) -> None:
        """Insert or replace a user row (DELETE + INSERT via MERGE)."""
        allowed = self._build_allowed_projects(routing_bucket, agency_company)
        allowed_literal = self._array_literal(allowed)

        sql = f"""
        MERGE {self._table_ref} AS T
        USING (SELECT @email AS email) AS S
        ON T.email = S.email
        WHEN MATCHED THEN
          UPDATE SET role = @role, allowed_projects = {allowed_literal}
        WHEN NOT MATCHED THEN
          INSERT (email, role, allowed_projects)
          VALUES (@email, @role, {allowed_literal})
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("email", "STRING", email),
                bigquery.ScalarQueryParameter("role", "STRING", role),
            ]
        )
        self.client.query(sql, job_config=job_config).result()
        _invalidate(email)

    def bulk_upsert_users(
        self,
        emails: list[str],
        role: str,
        routing_bucket: str | None = None,
        agency_company: str | None = None,
    ) -> int:
        """Upsert multiple users with the same role settings. Returns count written."""
        for email in emails:
            self.upsert_user(email, role, routing_bucket, agency_company)
        return len(emails)

    def delete_user(self, email: str) -> None:
        sql = f"DELETE FROM {self._table_ref} WHERE email = @email"
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("email", "STRING", email)]
        )
        self.client.query(sql, job_config=job_config).result()
        _invalidate(email)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_allowed_projects(
        routing_bucket: str | None,
        agency_company: str | None,
    ) -> list[str]:
        result: list[str] = []
        if routing_bucket:
            result.append(routing_bucket)
            if agency_company:
                result.append(agency_company)
        return result

    @staticmethod
    def _array_literal(values: list[str]) -> str:
        if not values:
            return "CAST([] AS ARRAY<STRING>)"
        escaped = ", ".join(f"'{v.replace(chr(39), chr(39)*2)}'" for v in values)
        return f"[{escaped}]"
