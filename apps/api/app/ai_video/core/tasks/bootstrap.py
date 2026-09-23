"""任务执行器注册入口。"""

from __future__ import annotations

from app.ai_video.core.tasks.audio_generation_tasks import AudioGenerationTask
from app.ai_video.core.tasks.image_generation_tasks import ImageGenerationTask
from app.ai_video.core.tasks.registry import register_task_adapter
from app.ai_video.core.tasks.video_generation_tasks import VideoGenerationTask


TASK_ADAPTER_SPECS = (
    ("audio_generation", "openai", AudioGenerationTask._build_openai_impl),
    ("audio_generation", "creatify", AudioGenerationTask._build_creatify_impl),
    ("audio_generation", "vertex", AudioGenerationTask._build_vertex_impl),
    ("image_generation", "openai", ImageGenerationTask._build_openai_impl),
    ("image_generation", "vertex", ImageGenerationTask._build_vertex_impl),
    ("video_generation", "openai", VideoGenerationTask._build_openai_impl),
    ("video_generation", "vertex", VideoGenerationTask._build_vertex_impl),
)


def bootstrap_task_adapters() -> None:
    """注册内置任务执行器（幂等）。"""

    for task_kind, provider, factory in TASK_ADAPTER_SPECS:
        register_task_adapter(task_kind, provider, factory)
