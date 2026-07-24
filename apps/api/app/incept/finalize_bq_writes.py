"""
Finalization script: reads existing cold_prospect_app rows and runs the
remaining BQ steps that failed in the previous pipeline run:
  - bq_append_snapshot  (WRITE_APPEND to prospect_snapshot)
  - bq_write_company    (CREATE OR REPLACE cold_prospect_company)
  - bq_ensure_conversion_view

Run after fixing the SchemaUpdateOption in save_cold_prospect_table.py.
"""
import logging
from google.cloud import bigquery
from app.incept.save_cold_prospect_table import (
    DEST_APP, SCHEMA,
    bq_append_snapshot, bq_write_company, bq_ensure_conversion_view,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    bq = bigquery.Client(project="ads-bpd-guard-sandbox")

    log.info("Reading rows from %s …", DEST_APP)
    field_names = [f.name for f in SCHEMA]
    select_cols = ", ".join(field_names)
    from datetime import date as _date
    rows_raw = list(bq.query(f"SELECT {select_cols} FROM `{DEST_APP}`").result())
    def _serialize(v):
        if isinstance(v, _date):
            return v.isoformat()
        return v
    rows = [{k: _serialize(v) for k, v in dict(r).items()} for r in rows_raw]
    log.info("Loaded %d rows", len(rows))

    log.info("Appending to snapshot …")
    bq_append_snapshot(bq, rows)

    log.info("Writing company table …")
    bq_write_company(bq)

    log.info("Refreshing conversion view …")
    bq_ensure_conversion_view(bq)

    log.info("All BQ finalization steps complete.")


if __name__ == "__main__":
    main()
