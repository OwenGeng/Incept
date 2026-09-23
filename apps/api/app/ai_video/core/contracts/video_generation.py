"""视频生成共享输入输出契约。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai_video.core.contracts.provider import ProviderKey


def _strip_optional_b64(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    return s if s else None


VideoRatio = Literal["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"]


class VideoReferenceMedia(BaseModel):
    """Deployment-owned reference media for providers that accept object URIs."""

    model_config = ConfigDict(extra="forbid")

    uri: str = Field(..., description="Private deployment-owned media URI, for example gs://bucket/path")
    mime_type: str = Field(..., description="Verified MIME type of the reference media")


class VideoGenerationInput(BaseModel):
    """视频生成输入：支持文本提示词 + 可选的三种帧参考图（纯 base64 或 data URL）。"""

    model_config = ConfigDict(extra="forbid")

    prompt: Optional[str] = Field(None, description="文本提示词；可与参考图二选一或同时存在")

    first_frame_base64: Optional[str] = Field(None, description="首帧图：纯 base64 或 data:image/...;base64,...")
    last_frame_base64: Optional[str] = Field(None, description="尾帧图：纯 base64 或 data URL")
    key_frame_base64: Optional[str] = Field(None, description="关键帧图：纯 base64 或 data URL")
    reference_media: list[VideoReferenceMedia] = Field(
        default_factory=list,
        description="Provider-specific object-store references. These are never accepted from browser requests.",
    )

    model: Optional[str] = Field(None, description="视频模型名称（可选，供应商透传）")
    # HTTP creation routes still require ratio explicitly.  Keeping an internal
    # default maintains compatibility for legacy worker payloads and adapters.
    ratio: VideoRatio = Field("16:9", description="视频宽高比，业务层唯一主参数")
    seconds: Optional[int] = Field(None, description="时长（秒）（可选，供应商透传）")
    seed: Optional[int] = Field(
        None,
        ge=-1,
        le=4294967295,
        description="随机种子，-1 或 [0, 2^32-1]，供应商/模型可能有差异",
    )
    watermark: Optional[bool] = Field(None, description="是否包含水印，供应商/模型可能有差异")
    provider_params: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Provider-specific parameters validated against the selected model's runtime schema. "
            "For Creatify, these are forwarded as input_params after server-side media URL resolution."
        ),
    )

    @model_validator(mode="after")
    def require_prompt_or_any_reference(self) -> "VideoGenerationInput":
        has_prompt = bool((self.prompt or "").strip())
        has_ref = any(
            [
                _strip_optional_b64(self.first_frame_base64),
                _strip_optional_b64(self.last_frame_base64),
                _strip_optional_b64(self.key_frame_base64),
                self.reference_media,
            ]
        )
        if not has_prompt and not has_ref:
            raise ValueError("Require prompt or at least one reference frame (base64)")
        return self


class VideoGenerationResult(BaseModel):
    """视频生成结果：返回视频 URL 和/或 file_id。"""

    model_config = ConfigDict(extra="forbid")

    url: Optional[str] = Field(None, description="生成视频可下载 URL")
    file_id: Optional[str] = Field(None, description="落库后的 FileItem.id（type=video）")
    provider_task_id: Optional[str] = Field(None, description="供应商侧任务/视频 ID（用于调试/追踪）")
    provider: Optional[ProviderKey] = Field(None, description="供应商标识")
    status: Optional[str] = Field(None, description="供应商任务状态")
    artifacts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Provider output metadata retained for task auditability; never contains credentials.",
    )

    @model_validator(mode="after")
    def require_url_or_file_id(self) -> "VideoGenerationResult":
        if not self.url and not self.file_id:
            raise ValueError("Either url or file_id must be set")
        return self
