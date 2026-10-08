import os
import json
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
    incept_require_gcs_upload: bool = Field(default=False)
    bigquery_enabled: bool = Field(default=False)
    bigquery_dataset: str = Field(default="Incept")
    bigquery_table_prefix: str = Field(default="ll_")

    openai_api_key: str | None = Field(default=None)
    openai_text_model: str = Field(default="gpt-6.1-sol")

    default_image_provider: str = Field(default="gemini")
    openai_image_model: str = Field(default="gpt-image-2.5-flare")
    openai_tts_model: str = Field(default="gpt-4o-mini-tts-2025-12-15")
    vertex_ai_enabled: bool = Field(default=False)
    # Imagen models (generate_images / edit_image API) — deprecated 2026-06-30
    vertex_imagen_model: str = Field(default="imagen-4.0-generate-001")
    vertex_imagen_edit_model: str = Field(default="imagen-4.0-generate-001")
    # Gemini image generation (generate_content API — replaces Imagen long-term)
    vertex_gemini_image_model: str = Field(default="gemini-3.1-flash-image")
    vertex_gemini_enabled: bool = Field(default=True)
    vertex_gemini_model: str = Field(default="gemini-3.8-flash")
    vertex_playable_model: str = Field(default="gemini-3.8-flash")
    # GamingPlayable's conversational planner has an explicit, intentionally
    # small model menu. Keep these independent from legacy video-to-playable
    # generation so an environment override cannot silently change that flow.
    vertex_playable_flash_model: str = Field(default="gemini-3.8-flash")
    vertex_playable_pro_model: str = Field(default="gemini-3.1-pro-preview")
    # Research has a separate explicit model choice so its behavior cannot be
    # changed by GamingPlayable or legacy video-planning configuration.
    vertex_research_model: str = Field(default="gemini-3.8-flash")
    # Keep video planning on the richer model without changing image/remediation analysis.
    vertex_video_analysis_model: str = Field(default="gemini-3.8-flash")
    google_tts_model: str = Field(default="gemini-3.1-flash-tts-preview")
    vertex_lyria_model: str = Field(default="lyria-3-clip-preview")
    vertex_lyria_location: str = Field(default="global")
    vertex_lyria_enabled: bool = Field(default=True)
    vertex_veo_fast_model: str = Field(default="gemini-omni-1.1-flash-preview")
    vertex_veo_location: str = Field(default="global")
    vertex_veo_model: str = Field(default="")
    # Claude uses Anthropic's first-party API. Keep it hidden from the model
    # picker until a server-side key is configured.
    anthropic_api_key: str | None = Field(default=None)
    anthropic_model: str = Field(default="claude-sonnet-5-5")
    studio_user_budget_usd: float = Field(default=500.0)
    veo_fast_estimated_cost_per_second_usd: float = Field(default=0.08)
    # Gemini text pricing is deployment-owned. Keep the default at zero rather
    # than silently inventing a price; usage is still metered by tokens.
    studio_copilot_estimated_cost_per_1k_tokens_usd: float = Field(default=0.0)
    studio_copilot_requests_per_minute: int = Field(default=12)
    studio_copilot_max_message_chars: int = Field(default=12_000)
    creative_core_home: str = Field(default="")
    playable_capture_chrome_path: str = Field(default="")
    playable_capture_ffmpeg_path: str = Field(default="")
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


def _json_object(value: str | None) -> dict[str, dict[str, str]]:
    """Read deployment-owned MCP principals without logging bearer tokens."""
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    principals: dict[str, dict[str, str]] = {}
    for token, principal in parsed.items():
        if not isinstance(token, str) or not token or not isinstance(principal, dict):
            continue
        normalized = {
            str(key): str(item)
            for key, item in principal.items()
            if isinstance(key, str) and isinstance(item, (str, int, float))
        }
        if normalized:
            principals[token] = normalized
    return principals


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
        incept_require_gcs_upload=os.getenv("INCEPT_REQUIRE_GCS_UPLOAD", "false").lower() == "true",
        bigquery_enabled=os.getenv("BIGQUERY_ENABLED", "false").lower() == "true",
        bigquery_dataset=os.getenv("BIGQUERY_DATASET", "Incept"),
        bigquery_table_prefix=os.getenv("BIGQUERY_TABLE_PREFIX", "ll_"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_text_model=os.getenv("OPENAI_TEXT_MODEL", "gpt-6.1-sol"),
        default_image_provider=os.getenv("DEFAULT_IMAGE_PROVIDER", "gemini"),
        openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare"),
        openai_tts_model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts-2025-12-15"),
        vertex_ai_enabled=os.getenv("VERTEX_AI_ENABLED", "false").lower() == "true",
        vertex_imagen_model=os.getenv("VERTEX_IMAGEN_MODEL", "imagen-4.0-generate-001"),
        vertex_imagen_edit_model=os.getenv("VERTEX_IMAGEN_EDIT_MODEL", "imagen-4.0-generate-001"),
        vertex_gemini_image_model=os.getenv("VERTEX_GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"),
        vertex_gemini_enabled=os.getenv("VERTEX_GEMINI_ENABLED", "true").lower() == "true",
        vertex_gemini_model=os.getenv("VERTEX_GEMINI_MODEL", "gemini-3.8-flash"),
        vertex_playable_model=os.getenv("VERTEX_PLAYABLE_MODEL", "gemini-3.8-flash"),
        vertex_playable_flash_model=os.getenv("VERTEX_PLAYABLE_FLASH_MODEL", "gemini-3.8-flash"),
        vertex_playable_pro_model=os.getenv("VERTEX_PLAYABLE_PRO_MODEL", "gemini-3.1-pro-preview"),
        vertex_research_model=os.getenv("VERTEX_RESEARCH_MODEL", "gemini-3.8-flash"),
        vertex_video_analysis_model=os.getenv("VERTEX_VIDEO_ANALYSIS_MODEL", "gemini-3.8-flash"),
        google_tts_model=os.getenv("GOOGLE_TTS_MODEL", "gemini-3.1-flash-tts-preview"),
        vertex_lyria_model=os.getenv("VERTEX_LYRIA_MODEL", "lyria-3-clip-preview"),
        vertex_lyria_location=os.getenv("VERTEX_LYRIA_LOCATION", "global"),
        vertex_lyria_enabled=os.getenv("VERTEX_LYRIA_ENABLED", "true").lower() == "true",
        vertex_veo_fast_model=os.getenv("VERTEX_VEO_FAST_MODEL") or "gemini-omni-1.1-flash-preview",
        vertex_veo_location=os.getenv("VERTEX_VEO_LOCATION") or "global",
        vertex_veo_model=os.getenv("VERTEX_VEO_MODEL", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        studio_user_budget_usd=float(os.getenv("STUDIO_USER_BUDGET_USD", "500")),
        veo_fast_estimated_cost_per_second_usd=float(os.getenv("VEO_FAST_ESTIMATED_COST_PER_SECOND_USD", "0.08")),
        studio_copilot_estimated_cost_per_1k_tokens_usd=float(os.getenv("STUDIO_COPILOT_ESTIMATED_COST_PER_1K_TOKENS_USD", "0")),
        studio_copilot_requests_per_minute=int(os.getenv("STUDIO_COPILOT_REQUESTS_PER_MINUTE", "12")),
        studio_copilot_max_message_chars=int(os.getenv("STUDIO_COPILOT_MAX_MESSAGE_CHARS", "12000")),
        creative_core_home=os.getenv("CREATIVE_CORE_HOME", ""),
        playable_capture_chrome_path=os.getenv("PLAYABLE_CAPTURE_CHROME_PATH", ""),
        playable_capture_ffmpeg_path=os.getenv("PLAYABLE_CAPTURE_FFMPEG_PATH", ""),
        gcp_vision_enabled=os.getenv("GCP_VISION_ENABLED", "false").lower() == "true",
        max_image_variants=int(os.getenv("MAX_IMAGE_VARIANTS", "2")),
        max_output_sizes=int(os.getenv("MAX_OUTPUT_SIZES", "32")),
        cors_origins=_split_csv(os.getenv("CORS_ORIGINS")) or [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
    )
