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

    # ── Intersight dataset bootstrap ───────────────────────────────────────────

    def _write_project(self) -> str:
        return (
            settings.bq_write_project
            or settings.gcp_project_deploy
            or settings.google_cloud_project
        )

    def ensure_intersight_tables(self) -> None:
        """Create the intersight dataset and required tables if they don't exist."""
        if self._tables_ready:
            return
        project = self._write_project()
        if not project:
            logger.warning("No write project configured — skipping intersight table setup.")
            return

        # Ensure dataset exists
        dataset_ref = bigquery.DatasetReference(project, "intersight")
        try:
            self.client.get_dataset(dataset_ref)
        except Exception:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "US"
            try:
                self.client.create_dataset(dataset, exists_ok=True)
            except Exception as exc:
                logger.warning("Could not create intersight dataset: %s", exc)

        # Ensure tables exist via DDL
        ddl_statements = [
            f"""
            CREATE TABLE IF NOT EXISTS `{project}.intersight.supply_smb_snapshot`
            (
              week_start_date DATE NOT NULL,
              created_at      TIMESTAMP NOT NULL,
              total_companies INT64,
              total_apps      INT64,
              p1_count        INT64,
              p2_count        INT64,
              p3_count        INT64,
              p4_count        INT64,
              team_routing_json     STRING,
              genre_mix_json        STRING,
              monetization_mix_json STRING,
              top_companies_json    STRING
            )
            PARTITION BY week_start_date
            """,
            f"""
            CREATE TABLE IF NOT EXISTS `{project}.intersight.lead_tracking`
            (
              lead_id        STRING NOT NULL,
              company_name   STRING,
              list_source    STRING,
              team_routing   STRING,
              sent_to_team   STRING,
              notes          STRING,
              activated_by   STRING,
              status         STRING,
              activated_date DATE,
              last_updated   TIMESTAMP,
              converted_date DATE,
              total_spend_90d FLOAT64
            )
            PARTITION BY activated_date
            """,
        ]
        for ddl in ddl_statements:
            try:
                self.client.query(ddl).result()
            except Exception as exc:
                logger.warning("DDL failed (table may already exist): %s", exc)

        self._tables_ready = True

    # ── Snapshot: write ────────────────────────────────────────────────────────

    def write_snapshot(self, week_start_date: str, snapshot: dict[str, Any]) -> None:
        """Insert a weekly snapshot row into supply_smb_snapshot."""
        project = self._write_project()
        sql = f"""
        INSERT INTO `{project}.intersight.supply_smb_snapshot`
          (week_start_date, created_at, total_companies, total_apps,
           p1_count, p2_count, p3_count, p4_count,
           team_routing_json, genre_mix_json, monetization_mix_json, top_companies_json)
        VALUES (
          @week_start_date, CURRENT_TIMESTAMP(),
          @total_companies, @total_apps,
          @p1_count, @p2_count, @p3_count, @p4_count,
          @team_routing_json, @genre_mix_json, @monetization_mix_json, @top_companies_json
        )
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("week_start_date", "DATE", week_start_date),
                bigquery.ScalarQueryParameter("total_companies", "INT64", snapshot["total_companies"]),
                bigquery.ScalarQueryParameter("total_apps", "INT64", snapshot["total_apps"]),
                bigquery.ScalarQueryParameter("p1_count", "INT64", snapshot["p1_count"]),
                bigquery.ScalarQueryParameter("p2_count", "INT64", snapshot["p2_count"]),
                bigquery.ScalarQueryParameter("p3_count", "INT64", snapshot["p3_count"]),
                bigquery.ScalarQueryParameter("p4_count", "INT64", snapshot["p4_count"]),
                bigquery.ScalarQueryParameter("team_routing_json", "STRING", json.dumps(snapshot["team_routing"])),
                bigquery.ScalarQueryParameter("genre_mix_json", "STRING", json.dumps(snapshot["genre_mix"])),
                bigquery.ScalarQueryParameter("monetization_mix_json", "STRING", json.dumps(snapshot["monetization_mix"])),
                bigquery.ScalarQueryParameter("top_companies_json", "STRING", json.dumps(snapshot["top_companies"])),
            ]
        )
        self.client.query(sql, job_config=job_config).result()

    # ── Snapshot: read ─────────────────────────────────────────────────────────

    def read_previous_snapshot(self, before_date: str) -> dict[str, Any] | None:
        """Read the most recent snapshot strictly before before_date."""
        project = self._write_project()
        sql = f"""
        SELECT *
        FROM `{project}.intersight.supply_smb_snapshot`
        WHERE week_start_date < @before_date
        ORDER BY week_start_date DESC
        LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("before_date", "DATE", before_date),
            ]
        )
        rows = self.query(sql, job_config=job_config)
        if not rows:
            return None
        row = rows[0]
        # Deserialize JSON fields
        for field in ("team_routing_json", "genre_mix_json", "monetization_mix_json", "top_companies_json"):
            try:
                row[field] = json.loads(row[field] or "{}")
            except Exception:
                row[field] = {}
        return row

    # ── Lead Tracking: write ───────────────────────────────────────────────────

    def insert_lead(self, lead: dict[str, Any]) -> None:
        """Insert a new lead into lead_tracking."""
        project = self._write_project()
        sql = f"""
        INSERT INTO `{project}.intersight.lead_tracking`
          (lead_id, company_name, list_source, team_routing, sent_to_team,
           notes, activated_by, status, activated_date, last_updated)
        VALUES (
          @lead_id, @company_name, @list_source, @team_routing, @sent_to_team,
          @notes, @activated_by, @status, CURRENT_DATE(), CURRENT_TIMESTAMP()
        )
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("lead_id", "STRING", lead["lead_id"]),
                bigquery.ScalarQueryParameter("company_name", "STRING", lead["company_name"]),
                bigquery.ScalarQueryParameter("list_source", "STRING", lead["list_source"]),
                bigquery.ScalarQueryParameter("team_routing", "STRING", lead["team_routing"]),
                bigquery.ScalarQueryParameter("sent_to_team", "STRING", lead["sent_to_team"]),
                bigquery.ScalarQueryParameter("notes", "STRING", lead.get("notes", "")),
                bigquery.ScalarQueryParameter("activated_by", "STRING", lead["activated_by"]),
                bigquery.ScalarQueryParameter("status", "STRING", lead.get("status", "sent")),
            ]
        )
        self.client.query(sql, job_config=job_config).result()

    def append_lead_status(self, lead_id: str, new_status: str, notes: str = "") -> None:
        """Append a status update row (append model — newest row wins when reading)."""
        project = self._write_project()
        # Copy all fields from the latest row, override status + notes + last_updated
        sql = f"""
        INSERT INTO `{project}.intersight.lead_tracking`
          (lead_id, company_name, list_source, team_routing, sent_to_team,
           notes, activated_by, status, activated_date, last_updated)
        SELECT
          lead_id, company_name, list_source, team_routing, sent_to_team,
          IF(@notes != '', @notes, notes),
          activated_by,
          @new_status,
          activated_date,
          CURRENT_TIMESTAMP()
        FROM (
          SELECT * FROM `{project}.intersight.lead_tracking`
          WHERE lead_id = @lead_id
          ORDER BY last_updated DESC
          LIMIT 1
        )
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("lead_id", "STRING", lead_id),
                bigquery.ScalarQueryParameter("new_status", "STRING", new_status),
                bigquery.ScalarQueryParameter("notes", "STRING", notes),
            ]
        )
        self.client.query(sql, job_config=job_config).result()

    # ── Lead Tracking: read ────────────────────────────────────────────────────

    def list_leads(self, email_filter: str | None = None) -> list[dict[str, Any]]:
        """Return latest status per lead, ordered by last_updated DESC."""
        project = self._write_project()
        email_clause = f"AND activated_by = '{email_filter}'" if email_filter else ""
        sql = f"""
        WITH ranked AS (
          SELECT *,
            ROW_NUMBER() OVER (PARTITION BY lead_id ORDER BY last_updated DESC) AS rn
          FROM `{project}.intersight.lead_tracking`
          WHERE TRUE {email_clause}
        )
        SELECT * EXCEPT(rn) FROM ranked WHERE rn = 1
        ORDER BY last_updated DESC
        """
        return self.query(sql)

    # ── Attribution check ──────────────────────────────────────────────────────

    def run_attribution_check(self, email_filter: str | None = None) -> list[dict[str, Any]]:
        """
        Join active leads against fact_dsp_core to identify converts.
        Matches on company_name (case-insensitive). Attribution window: 90 days.
        """
        project = self._write_project()
        email_clause = f"AND activated_by = '{email_filter}'" if email_filter else ""
        sql = f"""
        WITH latest_leads AS (
          SELECT *,
            ROW_NUMBER() OVER (PARTITION BY lead_id ORDER BY last_updated DESC) AS rn
          FROM `{project}.intersight.lead_tracking`
          WHERE TRUE {email_clause}
        ),
        active_leads AS (
          SELECT * EXCEPT(rn)
          FROM latest_leads
          WHERE rn = 1
        ),
        dsp_spend AS (
          SELECT
            LOWER(TRIM(product.company_name)) AS company_key,
            MIN(date_utc)                      AS first_spend_date,
            SUM(gross_spend_usd)               AS total_spend_90d
          FROM `ads-bpd-guard-china.athena.fact_dsp_core`
          WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
            AND gross_spend_usd > 0
            AND product.company_name IS NOT NULL
            AND TRIM(product.company_name) != ''
          GROUP BY 1
        )
        SELECT
          l.*,
          d.first_spend_date,
          d.total_spend_90d,
          (d.company_key IS NOT NULL
            AND d.first_spend_date >= l.activated_date) AS is_attributed
        FROM active_leads l
        LEFT JOIN dsp_spend d
          ON LOWER(TRIM(l.company_name)) = d.company_key
        ORDER BY l.last_updated DESC
        """
        return self.query(sql)
