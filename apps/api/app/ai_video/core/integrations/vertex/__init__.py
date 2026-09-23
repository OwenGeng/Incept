"""Google Vertex AI adapters using Application Default Credentials (ADC)."""

from app.ai_video.core.integrations.vertex.images import VertexImageApiAdapter
from app.ai_video.core.integrations.vertex.video import VertexVideoApiAdapter

__all__ = ["VertexImageApiAdapter", "VertexVideoApiAdapter"]
