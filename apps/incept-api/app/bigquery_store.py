import logging
from functools import lru_cache

from app.config import get_settings
from app.models import Asset, GenerationJob, UsageEvent


logger = logging.getLogger(__name__)


class BigQueryStore:
    def __init__(self) -> None:
        settings = get_settings()
        from google.cloud import bigquery

        self._client = bigquery.Client(project=settings.gcp_project_id)
        self._project_id = self._client.project
        self._dataset = settings.bigquery_dataset
        self._table_prefix = settings.bigquery_table_prefix

    def _table(self, table_id: str) -> str:
        return f"{self._project_id}.{self._dataset}.{self._table_prefix}{table_id}"

    def _insert(self, table_id: str, rows: list[dict]) -> None:
        if not rows:
            return
        errors = self._client.insert_rows_json(self._table(table_id), rows)
        if errors:
            raise RuntimeError(f"BigQuery insert failed for {table_id}: {errors}")

    def insert_job(self, job: GenerationJob) -> None:
        self._insert(
            "jobs",
            [
                {
                    "job_id": job.job_id,
                    "task_id": None,
                    "workspace_id": job.workspace_id,
                    "tool_id": job.tool_id,
                    "status": job.status.value,
                    "progress": job.progress,
                    "error_message": None,
                    "created_at": job.created_at.isoformat(),
                    "updated_at": job.updated_at.isoformat(),
                }
            ],
        )
        self._insert(
            "generation_results",
            [
                {
                    "generation_result_id": f"gr_{job.job_id}",
                    "job_id": job.job_id,
                    "workspace_id": job.workspace_id,
                    "provider": job.tool_id.split("-", 1)[0],
                    "model": job.tool_id,
                    "variant_count": None,
                    "output_asset_ids": job.output_asset_ids,
                    "created_at": job.created_at.isoformat(),
                }
            ],
        )

    def insert_assets(self, assets: list[Asset]) -> None:
        self._insert(
            "assets",
            [
                {
                    "incept_asset_id": asset.id,
                    "workspace_id": asset.workspace_id,
                    "job_id": asset.job_id,
                    "asset_type": asset.type,
                    "gcs_uri": asset.gcs_uri,
                    "provider": asset.provider,
                    "model": asset.model,
                    "prompt_hash": asset.prompt_hash,
                    "metadata_json": {
                        "title": asset.title,
                        "preview_url": asset.preview_url,
                        "width": asset.width,
                        "height": asset.height,
                        "theme": asset.theme,
                    },
                    "created_by": asset.created_by,
                    "created_at": asset.created_at.isoformat(),
                }
                for asset in assets
            ],
        )

    def insert_usage_event(self, event: UsageEvent) -> None:
        self._insert(
            "usage_events",
            [
                {
                    "usage_event_id": event.id,
                    "job_id": event.job_id,
                    "workspace_id": event.workspace_id,
                    "user_id": event.user_id,
                    "user_email": event.user_email,
                    "provider": event.provider,
                    "model": event.model,
                    "operation": event.operation,
                    "prompt_hash": event.prompt_hash,
                    "variants": event.variants,
                    "output_size_count": event.output_size_count,
                    "output_format": event.output_format,
                    "estimated_provider_generations": event.estimated_provider_generations,
                    "output_asset_count": event.output_asset_count,
                    "estimated_cost_usd": event.estimated_cost_usd,
                    "actual_cost_usd": event.actual_cost_usd,
                    "input_tokens": event.input_tokens,
                    "output_tokens": event.output_tokens,
                    "created_at": event.created_at.isoformat(),
                }
            ],
        )


@lru_cache
def get_bigquery_store() -> BigQueryStore | None:
    settings = get_settings()
    if not settings.bigquery_enabled:
        return None
    return BigQueryStore()


def persist_generation(job: GenerationJob, assets: list[Asset], usage_event: UsageEvent) -> None:
    store = get_bigquery_store()
    if not store:
        return
    try:
        store.insert_job(job)
        store.insert_assets(assets)
        store.insert_usage_event(usage_event)
    except Exception:
        logger.exception("Failed to persist generation job to BigQuery")
