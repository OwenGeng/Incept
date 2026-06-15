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

    def _write_dataset(self) -> str:
        return settings.bq_dataset_supply_smb_write or "intersight"

    def ensure_intersight_tables(self) -> None:
        """Create the intersight dataset and required tables if they don't exist."""
        if self._tables_ready:
            return
        project = self._write_project()
        dataset_name = self._write_dataset()
        if not project:
            logger.warning("No write project configured — skipping intersight table setup.")
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
                logger.warning("Could not create intersight dataset: %s", exc)

        # Ensure tables exist via DDL
        ddl_statements = [
            f"""
            CREATE TABLE IF NOT EXISTS `{project}.{dataset_name}.supply_smb_snapshot`
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
            CREATE TABLE IF NOT EXISTS `{project}.{dataset_name}.lead_tracking`
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

    # ── Bundle lookup (agent tool) ─────────────────────────────────────────────

    def lookup_bundles(self, bundle_ids: list[str]) -> list[dict[str, Any]]:
        """Return raw Moloco signals for a list of app bundle IDs / App Store IDs."""
        if not bundle_ids:
            return []
        sql = """
WITH
input_ids AS (
  SELECT bundle_id FROM UNNEST(@bundle_ids) AS bundle_id
),
sdk_supply AS (
  SELECT
    req.app_bundle                        AS bundle_id,
    TRUE                                  AS has_sdk_supply,
    MAX(req.app_name)                     AS app_name,
    SUM(impressions)                      AS sdk_impressions_90d
  FROM `ads-bpd-guard-china.gtm.fact_supply_with_tracking_publisher`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND req.app_bundle IN UNNEST(@bundle_ids)
  GROUP BY req.app_bundle
),
sdl AS (
  SELECT
    app_bundle,
    MAX(is_moloco_sdk_app)          AS is_moloco_sdk_app,
    MAX(is_moloco_advertiser_app)   AS is_moloco_advertiser_app,
    MAX(sdk_media_cost_usd)         AS sdk_media_cost_usd,
    MAX(eligibility_status)         AS eligibility_status
  FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
  WHERE app_bundle IN UNNEST(@bundle_ids)
  GROUP BY app_bundle
),
ua AS (
  SELECT
    product.app_market_bundle       AS bundle_id,
    SUM(gross_spend_usd)            AS ua_spend_90d
  FROM `ads-bpd-guard-china.athena.fact_dsp_core`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND product.app_market_bundle IN UNNEST(@bundle_ids)
    AND gross_spend_usd > 0
  GROUP BY product.app_market_bundle
),
meta AS (
  SELECT
    app_market_bundle,
    MAX(sensortower.company.name)       AS company_name,
    MAX(sensortower.company.hq_country) AS hq_country_st,
    MAX(os)                             AS os
  FROM `ads-bpd-guard-china.athena.dim1_app_v3`
  WHERE app_market_bundle IN UNNEST(@bundle_ids)
  GROUP BY app_market_bundle
),
gtm_hq AS (
  SELECT company_name, final_hq_country
  FROM `ads-bpd-guard-sandbox.yingzi_uploads.hq_country_triage`
  WHERE final_hq_country IS NOT NULL
)
SELECT
  i.bundle_id,
  COALESCE(s.app_name, 'Unknown')              AS app_name,
  COALESCE(s.has_sdk_supply, FALSE)            AS has_sdk_supply,
  COALESCE(s.sdk_impressions_90d, 0)           AS sdk_impressions_90d,
  COALESCE(d.is_moloco_sdk_app, FALSE)         AS is_moloco_sdk_app,
  COALESCE(d.is_moloco_advertiser_app, FALSE)  AS is_moloco_advertiser_app,
  COALESCE(d.sdk_media_cost_usd, 0)            AS sdk_media_cost_usd,
  d.eligibility_status,
  COALESCE(u.ua_spend_90d, 0)                  AS ua_spend_90d,
  m.company_name,
  COALESCE(g.final_hq_country, m.hq_country_st) AS final_hq_country,
  m.os
FROM input_ids i
LEFT JOIN sdk_supply s ON i.bundle_id = s.bundle_id
LEFT JOIN sdl       d ON i.bundle_id = d.app_bundle
LEFT JOIN ua        u ON i.bundle_id = u.bundle_id
LEFT JOIN meta      m ON i.bundle_id = m.app_market_bundle
LEFT JOIN gtm_hq    g ON m.company_name = g.company_name
"""
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("bundle_ids", "STRING", bundle_ids)
            ]
        )
        return self.query(sql, job_config=job_config)

    # ── Feedback ───────────────────────────────────────────────────────────────

    def write_feedback(self, feedback: dict[str, Any]) -> None:
        """Insert a user feedback row into intersight.feedback."""
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

    # ── Snapshot: write ────────────────────────────────────────────────────────

    def write_snapshot(self, week_start_date: str, snapshot: dict[str, Any]) -> None:
        """Insert a weekly snapshot row into supply_smb_snapshot."""
        project = self._write_project()
        dataset_name = self._write_dataset()
        sql = f"""
        INSERT INTO `{project}.{dataset_name}.supply_smb_snapshot`
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
        rows = self.read_historical_snapshots(n_weeks=1, before_date=before_date)
        return rows[0] if rows else None

    def read_historical_snapshots(
        self, n_weeks: int = 8, before_date: str | None = None
    ) -> list[dict[str, Any]]:
        """Read the last n_weeks snapshots, optionally before a given date. Oldest first."""
        project = self._write_project()
        dataset_name = self._write_dataset()
        if not project:
            return []
        where = "WHERE week_start_date < @before_date" if before_date else ""
        params = []
        if before_date:
            params.append(bigquery.ScalarQueryParameter("before_date", "DATE", before_date))
        params.append(bigquery.ScalarQueryParameter("n_weeks", "INT64", n_weeks))
        sql = f"""
        SELECT *
        FROM `{project}.{dataset_name}.supply_smb_snapshot`
        {where}
        ORDER BY week_start_date DESC
        LIMIT @n_weeks
        """
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        try:
            rows = self.query(sql, job_config=job_config)
        except Exception as exc:
            logger.warning("read_historical_snapshots failed: %s", exc)
            return []
        json_fields = ("team_routing_json", "genre_mix_json", "monetization_mix_json", "top_companies_json")
        for row in rows:
            for field in json_fields:
                try:
                    row[field] = json.loads(row[field] or "{}")
                except Exception:
                    row[field] = {}
        rows.reverse()  # return oldest → newest
        return rows

    def snapshot_exists_for_week(self, week_start_date: str) -> bool:
        """Return True if a snapshot for this exact week already exists."""
        project = self._write_project()
        dataset_name = self._write_dataset()
        if not project:
            return False
        sql = f"""
        SELECT COUNT(*) AS cnt
        FROM `{project}.{dataset_name}.supply_smb_snapshot`
        WHERE week_start_date = @week_start_date
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("week_start_date", "DATE", week_start_date),
            ]
        )
        try:
            rows = self.query(sql, job_config=job_config)
            return bool(rows and rows[0].get("cnt", 0) > 0)
        except Exception:
            return False

    # ── Lead Tracking: write ───────────────────────────────────────────────────

    def insert_lead(self, lead: dict[str, Any]) -> None:
        """Insert a new lead into lead_tracking."""
        project = self._write_project()
        dataset_name = self._write_dataset()
        sql = f"""
        INSERT INTO `{project}.{dataset_name}.lead_tracking`
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
        INSERT INTO `{project}.{self._write_dataset()}.lead_tracking`
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
          SELECT * FROM `{project}.{self._write_dataset()}.lead_tracking`
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
          FROM `{project}.{self._write_dataset()}.lead_tracking`
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
          FROM `{project}.{self._write_dataset()}.lead_tracking`
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
