from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from google.cloud import bigquery

from app.core.config import settings

logger = logging.getLogger(__name__)


class BigQueryService:
    def __init__(self) -> None:
        project = settings.gcp_project_deploy or settings.google_cloud_project or None
        self.client = bigquery.Client(project=project)
        self._tables_ready = False

    # ── Read helpers ───────────────────────────────────────────────────────────

    def query(
        self,
        sql: str,
        job_config: bigquery.QueryJobConfig | None = None,
    ) -> list[dict[str, Any]]:
        job = self.client.query(sql, job_config=job_config)
        return [dict(row.items()) for row in job.result()]

    def query_file(self, file_path: str | Path) -> list[dict[str, Any]]:
        sql = Path(file_path).read_text(encoding="utf-8")
        return self.query(sql)

    # ── Application dataset bootstrap ───────────────────────────────────────────

    def _write_project(self) -> str:
        return (
            settings.bq_write_project
            or settings.gcp_project_deploy
            or settings.google_cloud_project
        )

    def _write_dataset(self) -> str:
        return settings.bq_dataset_app_write or "Incept"

    def ensure_app_tables(self) -> None:
        """Create the application dataset and required tables if they don't exist."""
        if self._tables_ready:
            return
        project = self._write_project()
        dataset_name = self._write_dataset()
        if not project:
            logger.warning("No write project configured — skipping application table setup.")
            return

        # Ensure dataset exists
        dataset_ref = bigquery.DatasetReference(project, dataset_name)
        try:
            self.client.get_dataset(dataset_ref)
        except Exception:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "US"
            try:
                self.client.create_dataset(dataset, exists_ok=True)
            except Exception as exc:
                logger.warning("Could not create application dataset: %s", exc)

        # Ensure tables exist via DDL
        ddl_statements = [
            f"""
            CREATE TABLE IF NOT EXISTS `{project}.{dataset_name}.feedback`
            (
              feedback_id  STRING NOT NULL,
              created_at   TIMESTAMP NOT NULL,
              user_email   STRING,
              content      STRING NOT NULL
            )
            PARTITION BY DATE(created_at)
            """,
        ]
        for ddl in ddl_statements:
            try:
                self.client.query(ddl).result()
            except Exception as exc:
                logger.warning("DDL failed (table may already exist): %s", exc)

        self._tables_ready = True

    # ── Feedback ───────────────────────────────────────────────────────────────

    def write_feedback(self, feedback: dict[str, Any]) -> None:
        """Insert a user feedback row into the application feedback table."""
        project = self._write_project()
        dataset_name = self._write_dataset()
        if not project:
            logger.warning("No write project — feedback not saved.")
            return
        sql = f"""
        INSERT INTO `{project}.{dataset_name}.feedback`
          (feedback_id, created_at, user_email, content)
        VALUES (@feedback_id, CURRENT_TIMESTAMP(), @user_email, @content)
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("feedback_id", "STRING", feedback["feedback_id"]),
                bigquery.ScalarQueryParameter("user_email", "STRING", feedback.get("user_email") or ""),
                bigquery.ScalarQueryParameter("content", "STRING", feedback["content"]),
            ]
        )
        self.client.query(sql, job_config=job_config).result()
