from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from app.ai_video.core.contracts.video_generation import VideoRatio

class VideoGenerationTaskRequest(BaseModel):
    """视频生成任务请求。"""

    shot_id: str = Field(..., description="镜头 ID")
    reference_mode: Literal["first", "last", "key", "first_last", "first_last_key", "text_only"] = Field(
        ...,
        description="参考模式：first | last | key | first_last | first_last_key | text_only",
    )
    # 文本模式必填；非文本模式可选作为补充描述
    prompt: str | None = Field(None, description="视频提示词（text_only 必填）")
    images: list[str] = Field(
        default_factory=list,
        description="参考图 file_id 列表，数量需与 reference_mode 严格匹配",
    )

    ratio: VideoRatio = Field(..., description="视频画幅比例，如 16:9 / 9:16")
    model_id: str | None = Field(
        None,
        description="可选 models.id；不传则使用默认视频模型",
    )
    provider_params: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Model-specific runtime parameters. Creatify fields must match the synchronized schema; "
            "use linglong-file://<file_id> for server-resolved reference media."
        ),
    )
    # seconds 由 ShotDetail.duration 自动确定；请求体不再接收覆盖值。


class ConfirmedVideoGenerationTaskRequest(VideoGenerationTaskRequest):
    quote_fingerprint: str = Field(..., min_length=64, max_length=64, description="预检返回的报价指纹")
    confirmed_by: str = Field(..., min_length=1, max_length=255, description="确认费用的操作者")


class VideoGenerationQuoteRead(BaseModel):
    complete: bool
    currency: str
    amount: str
    quantity: str
    unit: str
    unit_amount: str
    model_id: str
    estimate_kind: str | None = None
    estimate_scope: str | None = None
    exclusions: list[str] = Field(default_factory=list)
    pricing_snapshot: dict[str, Any] | None = None
    quote_fingerprint: str
