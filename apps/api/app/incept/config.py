import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env from the service root (services/api/.env)
load_dotenv(Path(__file__).parent.parent.parent / ".env")


class Settings(BaseModel):
    environment: str = Field(default="development")
    auth_mode: str = Field(default="dev")
    allowed_email_domain: str = Field(default="moloco.com")
    iap_jwt_audience: str | None = Field(default=None)
    admin_emails: set[str] = Field(default_factory=set)
    manager_emails: set[str] = Field(default_factory=set)

    gcp_project_id: str | None = Field(default=None)
    gcp_location: str = Field(default="global")
    incept_asset_bucket: str = Field(default="INCEPT_ASSET_BUCKET")
    bigquery_enabled: bool = Field(default=False)
    bigquery_dataset: str = Field(default="incept")
    bigquery_table_prefix: str = Field(default="ll_")

    openai_api_key: str | None = Field(default=None)

    default_image_provider: str = Field(default="gemini")
    openai_image_model: str = Field(default="gpt-image-2")
    vertex_ai_enabled: bool = Field(default=False)
    # Imagen models (generate_images / edit_image API) — deprecated 2026-06-30
    vertex_imagen_model: str = Field(default="imagen-4.0-generate-001")
    vertex_imagen_edit_model: str = Field(default="imagen-4.0-generate-001")
    # Gemini image generation (generate_content API — replaces Imagen long-term)
    vertex_gemini_image_model: str = Field(default="gemini-3.1-flash-image")
    vertex_gemini_enabled: bool = Field(default=True)
    vertex_gemini_model: str = Field(default="gemini-3.1-flash-lite")
    gcp_vision_enabled: bool = Field(default=False)
    max_image_variants: int = Field(default=2)
    max_output_sizes: int = Field(default=32)

    cors_origins: list[str] = Field(default_factory=lambda: [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ])


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings(
        environment=os.getenv("INCEPT_ENV", "development"),
        auth_mode=os.getenv("AUTH_MODE", "dev").lower(),
        allowed_email_domain=os.getenv("ALLOWED_EMAIL_DOMAIN", "moloco.com").lower(),
        iap_jwt_audience=os.getenv("IAP_JWT_AUDIENCE"),
        admin_emails={item.lower() for item in _split_csv(os.getenv("INCEPT_ADMIN_EMAILS"))},
        manager_emails={item.lower() for item in _split_csv(os.getenv("INCEPT_MANAGER_EMAILS"))},
        gcp_project_id=os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT"),
        gcp_location=os.getenv("GCP_LOCATION", "global"),
        incept_asset_bucket=os.getenv("INCEPT_ASSET_BUCKET", "INCEPT_ASSET_BUCKET"),
        bigquery_enabled=os.getenv("BIGQUERY_ENABLED", "false").lower() == "true",
        bigquery_dataset=os.getenv("BIGQUERY_DATASET", "incept"),
        bigquery_table_prefix=os.getenv("BIGQUERY_TABLE_PREFIX", "ll_"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        default_image_provider=os.getenv("DEFAULT_IMAGE_PROVIDER", "gemini"),
        openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
        vertex_ai_enabled=os.getenv("VERTEX_AI_ENABLED", "false").lower() == "true",
        vertex_imagen_model=os.getenv("VERTEX_IMAGEN_MODEL", "imagen-4.0-generate-001"),
        vertex_imagen_edit_model=os.getenv("VERTEX_IMAGEN_EDIT_MODEL", "imagen-4.0-generate-001"),
        vertex_gemini_image_model=os.getenv("VERTEX_GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"),
        vertex_gemini_enabled=os.getenv("VERTEX_GEMINI_ENABLED", "true").lower() == "true",
        vertex_gemini_model=os.getenv("VERTEX_GEMINI_MODEL", "gemini-3.1-flash-lite"),
        gcp_vision_enabled=os.getenv("GCP_VISION_ENABLED", "false").lower() == "true",
        max_image_variants=int(os.getenv("MAX_IMAGE_VARIANTS", "2")),
        max_output_sizes=int(os.getenv("MAX_OUTPUT_SIZES", "32")),
        cors_origins=_split_csv(os.getenv("CORS_ORIGINS")) or [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
    )
