from functools import cached_property

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    intersight_env: str = Field(default="development", alias="INTERSIGHT_ENV")
    api_mode: str = Field(default="mock", alias="INTERSIGHT_API_MODE")
    api_host: str = Field(default="0.0.0.0", alias="INTERSIGHT_API_HOST")
    api_port: int = Field(default=8000, alias="INTERSIGHT_API_PORT")
    internal_api_key: str = Field(default="", alias="INTERSIGHT_INTERNAL_API_KEY")
    cors_allow_origins: str = Field(default="http://localhost:3000", alias="CORS_ALLOW_ORIGINS")

    gcp_project_deploy: str = Field(default="", alias="GCP_PROJECT_DEPLOY")
    gcp_project_data: str = Field(default="", alias="GCP_PROJECT_DATA")
    bq_write_project: str = Field(default="", alias="BQ_WRITE_PROJECT")
    bq_read_project: str = Field(default="", alias="BQ_READ_PROJECT")
    bq_dataset_supply_smb_write: str = Field(default="supply_smb", alias="BQ_DATASET_SUPPLY_SMB_WRITE")
    bq_dataset_config: str = Field(default="config", alias="BQ_DATASET_CONFIG")

    google_cloud_project: str = Field(default="", alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(default="global", alias="GOOGLE_CLOUD_LOCATION")
    google_genai_use_enterprise: bool = Field(default=True, alias="GOOGLE_GENAI_USE_ENTERPRISE")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    @cached_property
    def cors_allow_origins_list(self) -> list[str]:
        return [item.strip() for item in self.cors_allow_origins.split(",") if item.strip()]


settings = Settings()
