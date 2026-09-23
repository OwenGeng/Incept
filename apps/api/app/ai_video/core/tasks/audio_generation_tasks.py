"""Audio-generation task adapters for OpenAI, Creatify, and Vertex Lyria."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from app.ai_video.core.contracts.audio_generation import AudioGenerationInput, AudioGenerationResult
from app.ai_video.core.contracts.provider import ProviderConfig
from app.ai_video.core.integrations.creatify.text_to_speech import CreatifyTextToSpeechAdapter
from app.ai_video.core.integrations.openai.audio import OpenAIAudioApiAdapter
from app.ai_video.core.integrations.vertex.music import VertexMusicApiAdapter
from app.ai_video.core.task_manager.types import BaseTask
from app.ai_video.core.tasks.registry import resolve_task_adapter

__all__ = [
    "AudioGenerationInput",
    "AudioGenerationResult",
    "AudioGenerationTask",
]


class AbstractAudioGenerationTask(BaseTask, ABC):
    """Task lifecycle shared by each provider-specific audio adapter."""

    def __init__(self, *, provider_config: ProviderConfig, input_: AudioGenerationInput, timeout_s: float = 600.0) -> None:
        self._cfg = provider_config
        self._input = input_
        self._timeout_s = timeout_s
        self._result: AudioGenerationResult | None = None
        self._error = ""

    @abstractmethod
    async def _generate(self) -> AudioGenerationResult:
        """Run the provider request and normalize the result."""

    async def run(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any] | None:  # type: ignore[override]
        try:
            self._result = await self._generate()
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            self._result = None
        return None

    async def status(self) -> dict[str, Any]:  # type: ignore[override]
        return {
            "task": "audio_generation",
            "provider": self._cfg.provider,
            "provider_task_id": self._result.provider_task_id if self._result else None,
            "done": await self.is_done(),
            "has_result": self._result is not None,
            "error": self._error,
            "status": self._result.status if self._result else None,
        }

    async def is_done(self) -> bool:  # type: ignore[override]
        return self._result is not None or bool(self._error)

    async def get_result(self) -> AudioGenerationResult | None:  # type: ignore[override]
        return self._result


class OpenAIAudioGenerationTask(AbstractAudioGenerationTask):
    async def _generate(self) -> AudioGenerationResult:
        return await OpenAIAudioApiAdapter().generate(cfg=self._cfg, inp=self._input, timeout_s=self._timeout_s)


class VertexMusicGenerationTask(AbstractAudioGenerationTask):
    async def _generate(self) -> AudioGenerationResult:
        return await VertexMusicApiAdapter().generate(cfg=self._cfg, inp=self._input, timeout_s=self._timeout_s)


class CreatifySpeechGenerationTask(AbstractAudioGenerationTask):
    """Poll Creatify TTS until its documented terminal state is returned."""

    async def _generate(self) -> AudioGenerationResult:
        adapter = CreatifyTextToSpeechAdapter()
        accent = str(self._input.provider_params.get("accent") or "").strip() or None
        job = await adapter.create(
            cfg=self._cfg,
            script=self._input.prompt,
            accent=accent,
            # Linglong Lab owns durable status through GenerationTask polling.
            # Accepting arbitrary browser-supplied callback URLs would create a
            # second unverified delivery path and is unnecessary here.
            webhook_url=None,
            timeout_s=min(self._timeout_s, 60.0),
        )
        waited = 0.0
        while not job.is_terminal:
            if waited >= self._timeout_s:
                raise TimeoutError("Creatify Text-to-Speech did not finish before task timeout")
            await asyncio.sleep(5.0)
            waited += 5.0
            job = await adapter.get(cfg=self._cfg, job_id=job.id, timeout_s=min(self._timeout_s, 60.0))
        if not job.is_successful:
            raise RuntimeError(job.failed_reason or f"Creatify Text-to-Speech failed with status={job.status}")
        if not job.output_url:
            raise RuntimeError("Creatify Text-to-Speech completed without an output URL")
        return AudioGenerationResult(
            url=job.output_url,
            provider="creatify",
            provider_task_id=job.id,
            status="succeeded",
            duration_seconds=job.duration_seconds,
        )


class AudioGenerationTask(BaseTask):
    """Dispatch an audio request through the registered provider adapter."""

    def __init__(self, *, provider_config: ProviderConfig, input_: AudioGenerationInput, timeout_s: float = 600.0) -> None:
        from app.ai_video.bootstrap import bootstrap_all_registries

        bootstrap_all_registries()
        factory = resolve_task_adapter("audio_generation", provider_config.provider)
        self._impl: AbstractAudioGenerationTask = factory(
            provider_config=provider_config,
            input_=input_,
            timeout_s=timeout_s,
        )  # type: ignore[assignment]

    @staticmethod
    def _build_openai_impl(
        *, provider_config: ProviderConfig, input_: AudioGenerationInput, timeout_s: float = 600.0
    ) -> AbstractAudioGenerationTask:
        return OpenAIAudioGenerationTask(provider_config=provider_config, input_=input_, timeout_s=timeout_s)

    @staticmethod
    def _build_creatify_impl(
        *, provider_config: ProviderConfig, input_: AudioGenerationInput, timeout_s: float = 600.0
    ) -> AbstractAudioGenerationTask:
        return CreatifySpeechGenerationTask(provider_config=provider_config, input_=input_, timeout_s=timeout_s)

    @staticmethod
    def _build_vertex_impl(
        *, provider_config: ProviderConfig, input_: AudioGenerationInput, timeout_s: float = 600.0
    ) -> AbstractAudioGenerationTask:
        return VertexMusicGenerationTask(provider_config=provider_config, input_=input_, timeout_s=timeout_s)

    async def run(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any] | None:  # type: ignore[override]
        return await self._impl.run(*args, **kwargs)

    async def status(self) -> dict[str, Any]:  # type: ignore[override]
        return await self._impl.status()

    async def is_done(self) -> bool:  # type: ignore[override]
        return await self._impl.is_done()

    async def get_result(self) -> AudioGenerationResult | None:  # type: ignore[override]
        return await self._impl.get_result()
