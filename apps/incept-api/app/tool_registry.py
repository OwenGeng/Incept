from app.models import ToolDefinition, ToolStatus


TOOLS = [
    ToolDefinition(
        id="openai-image-2",
        name="OpenAI Image 2",
        category="image_generation",
        status="enabled",
        provider="openai",
        owner="Creative Studio",
        description="Primary quality benchmark for high-fidelity creative image generation.",
    ),
    ToolDefinition(
        id="gemini-image",
        name="Gemini Image",
        category="image_generation",
        status="enabled",
        provider="gemini",
        owner="Creative Studio",
        description="Fast multimodal image generation and iteration candidate.",
    ),
    ToolDefinition(
        id="veo-video",
        name="Veo Video",
        category="video_generation",
        status="mock",
        provider="mock",
        owner="Growth AI",
        description="Mock adapter for image-to-video and reference-based video workflows.",
    ),
    ToolDefinition(
        id="lightweight-gif",
        name="Lightweight GIF",
        category="gif_generation",
        status="mock",
        provider="mock",
        owner="Creative Automation",
        description="Mock adapter for lightweight creative and end-card generation.",
    ),
    ToolDefinition(
        id="bq-performance",
        name="BigQuery Performance",
        category="performance_analysis",
        status="mock",
        provider="bigquery",
        owner="IM GM",
        description="Mock adapter for joining Incept asset lineage with BigQuery performance data.",
    ),
]


def get_tools() -> list[ToolDefinition]:
    return TOOLS


def update_tool_status(tool_id: str, status: ToolStatus) -> ToolDefinition | None:
    for index, tool in enumerate(TOOLS):
        if tool.id == tool_id:
            updated = tool.model_copy(update={"status": status})
            TOOLS[index] = updated
            return updated
    return None
