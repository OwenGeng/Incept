"""Private Cloud Tasks runner endpoint for Cloud Run deployments."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Response, status

from app.ai_video.tasks.execute_task import run_task

router = APIRouter()


@router.post("/internal/task-executions/{task_id}", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
async def execute_cloud_task(task_id: str) -> Response:
    """Run a task after Cloud Run validates the task's OIDC identity and shared key."""
    await asyncio.to_thread(run_task, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
