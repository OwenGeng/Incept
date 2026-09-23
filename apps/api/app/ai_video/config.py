"""应用配置，从环境变量加载。"""

import json
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ai_video.core.database_url import build_cloud_sql_database_url


# This module runs inside the unified Incept API process. Read the same
# service-level environment file rather than maintaining a second backend one.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "Linglong Lab AI Video API"
    debug: bool = False

    # API
    api_v1_prefix: str = "/api/v1"

    # The mounted module receives requests only through Linglong's authenticated
    # Next proxy and shares Incept's internal service credential.
    internal_api_key: str = ""

    # Provider credentials are intentionally server-only.  Creatify's API uses
    # two named headers: API ID and API key.  Environment values take precedence
    # over legacy database fields so deployment secrets never need to be exposed
    # in the model-management UI or task payload.
    creatify_api_id: str = ""
    creatify_api_key: str = ""
    creatify_base_url: str = "https://api.creatify.ai/api"
    creatify_poll_initial_delay_seconds: int = 15
    creatify_poll_max_delay_seconds: int = 120
    openai_api_key: str = ""

    # Linglong Lab uses ADC for Vertex AI. Do not supply model defaults here: model
    # IDs and locations remain user-owned configuration in the Provider/Model
    # records and the existing Incept deployment configuration.
    vertex_ai_enabled: bool = False
    gcp_project_id: str = ""
    gcp_location: str = "global"

    # Database
    database_url: str = "sqlite+aiosqlite:///./linglong_ai_video.db"
    # In Cloud Run this value is mounted from the same Secret Manager contract
    # as Incept API. It takes precedence over local DATABASE_URL.
    database_config_json: str = ""
    instance_unix_socket: str = ""
    database_pool_size: int = 5
    database_max_overflow: int = 5

    # Redis / Celery Broker
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    celery_broker_url: str | None = None

    # Task execution. Local development keeps Celery for developer ergonomics;
    # the Cloud Run deployment uses Cloud Tasks and has no persistent worker.
    task_executor_backend: str = "celery"
    cloud_tasks_project_id: str = ""
    cloud_tasks_location: str = ""
    cloud_tasks_queue: str = ""
    # Root URL of the unified Incept API service. Cloud Tasks appends the
    # mounted /ai-video path itself; it is not a standalone AI Video URL.
    task_runner_url: str = ""
    task_runner_service_account_email: str = ""
    task_runner_dispatch_deadline_seconds: int = 900

    @property
    def resolved_cloud_tasks_project_id(self) -> str:
        """Use the deployment project unless a dedicated Tasks project was configured."""
        return self.cloud_tasks_project_id.strip() or self.gcp_project_id.strip()

    # CORS：环境变量中建议使用逗号分隔（更贴近 docker-compose 用法）
    # 也兼容 JSON 数组：'["http://a","http://b"]'
    cors_origins: str = "http://localhost:7788,http://127.0.0.1:7788,http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        s = (self.cors_origins or "").strip()
        if not s:
            return []
        if s.startswith("["):
            loaded = json.loads(s)
            if isinstance(loaded, list):
                return [str(x).strip() for x in loaded if str(x).strip()]
            return []
        return [x.strip() for x in s.split(",") if x.strip()]

    # S3 / 对象存储（用于素材文件）
    s3_endpoint_url: str | None = None
    s3_region_name: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket_name: str | None = None
    # 可选：统一前缀，方便按环境/项目隔离，如 "ai-video/dev"
    s3_base_path: str = ""
    # 可选：对外访问基址（CDN 或自定义域名），为空则使用 S3 自带 URL 或预签名 URL
    s3_public_base_url: str | None = None

    # Google Cloud Storage is the production asset store. The legacy S3 fields
    # remain available for local RustFS/AWS development only.
    gcs_bucket_name: str = ""
    gcs_base_path: str = "ai-video"
    gcs_public_base_url: str = ""
    # A disk fallback keeps the merged API usable for local upload tests when
    # no Cloud Storage bucket is configured. Production always prefers GCS.
    local_storage_dir: str = str(BACKEND_ROOT / "static" / "ai-video-files")

    @property
    def resolved_database_url(self) -> str:
        """Return Cloud SQL asyncpg URL when its Secret Manager config is present."""
        if self.database_config_json.strip():
            return build_cloud_sql_database_url(
                self.database_config_json,
                instance_unix_socket=self.instance_unix_socket,
            )
        return self.database_url

    def model_post_init(self, __context: object) -> None:
        # The AI Video module shares the owning Incept API's internal key; an
        # optional module-specific key remains backward compatible for local use.
        if not self.internal_api_key:
            self.internal_api_key = os.getenv("INCEPT_INTERNAL_API_KEY", "")
        if not self.gcs_bucket_name:
            # Reuse the existing Incept asset bucket instead of introducing a
            # second storage setting for the same Cloud Run service.
            self.gcs_bucket_name = os.getenv("INCEPT_ASSET_BUCKET", "")
        if not self.celery_broker_url or not str(self.celery_broker_url).strip():
            password_part = f":{self.redis_password}@" if self.redis_password else ""
            self.celery_broker_url = f"redis://{password_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = Settings()
