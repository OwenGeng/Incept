from functools import cached_property

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    incept_env: str = Field(default="development", alias="INCEPT_ENV")
    api_mode: str = Field(default="mock", alias="INCEPT_API_MODE")
    api_host: str = Field(default="0.0.0.0", alias="INCEPT_API_HOST")
    api_port: int = Field(default=8000, alias="INCEPT_API_PORT")
    internal_api_key: str = Field(default="", alias="INCEPT_INTERNAL_API_KEY")
    cors_allow_origins: str = Field(default="http://localhost:3000", alias="CORS_ALLOW_ORIGINS")

    enable_gaming_playable: bool | None = Field(default=None, alias="INCEPT_ENABLE_GAMING_PLAYABLE")

    gcp_project_deploy: str = Field(default="", alias="GCP_PROJECT_DEPLOY")
    gcp_project_data: str = Field(default="", alias="GCP_PROJECT_DATA")
    bq_write_project: str = Field(default="", alias="BQ_WRITE_PROJECT")
    bq_read_project: str = Field(default="", alias="BQ_READ_PROJECT")
    # Legacy production datasets retain their original name to preserve data.
    bq_dataset_app_write: str = Field(default="Incept", alias="BQ_DATASET_APP_WRITE")
    bq_dataset_config: str = Field(default="Incept", alias="BQ_DATASET_CONFIG")

    google_cloud_project: str = Field(default="", alias="GOOGLE_CLOUD_PROJECT")

    @cached_property
    def cors_allow_origins_list(self) -> list[str]:
        return [item.strip() for item in self.cors_allow_origins.split(",") if item.strip()]

    @property
    def gaming_playable_enabled(self) -> bool:
        if self.enable_gaming_playable is not None:
            return self.enable_gaming_playable
        return self.incept_env.strip().lower() != "production"


settings = Settings()
