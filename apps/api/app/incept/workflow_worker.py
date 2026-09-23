"""Durable Studio Workflow worker loop.

This runner deliberately claims persisted runs from SQLite instead of being a
FastAPI BackgroundTask. It is safe to run in a dedicated process later; the
current API lifespan starts one daemon worker for local/single-instance use.
"""

from __future__ import annotations

import logging
import threading
import asyncio
from time import sleep

from app.incept.workflow_store import (
    cache_node_result,
    claim_next_run,
    get_cached_node_result,
    is_run_cancelled,
    record_output,
    update_run_node,
    update_run_status,
    workflow_node_cache_key,
)
from app.incept.workflows import Workflow, WorkflowNode, WorkflowRunStatus
from app.incept.config import get_settings
from app.incept.models import GenerationRequest, JobStatus, Role, User, VideoGenerationMode, VideoGenerationRequest, VideoPlanRequest
from app.incept.store import JOBS, create_image_generation_job, run_generation_background
from app.incept.models import VideoProductionAgentRequest, VideoProductionAssetLink, VideoProductionCreateRequest, VideoProductionUpdateRequest
from app.incept.video_production_store import (
    create_video_production,
    update_video_production,
    run_creative_director,
    run_director_agent,
    run_production_designer,
    run_script_agent,
)
from app.incept.video_store import (
    assert_video_budget_available,
    confirm_video_generation_plan_for_request,
    create_or_update_video_plan,
    create_video_generation_job,
    run_video_generation_background,
)

logger = logging.getLogger(__name__)
_stop = threading.Event()


def _ordered_nodes(workflow: Workflow) -> list[WorkflowNode]:
    by_id = {node.id: node for node in workflow.graph.nodes}
    incoming = {node.id: 0 for node in workflow.graph.nodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in workflow.graph.nodes}
    for edge in workflow.graph.edges:
        if edge.source_node_id in by_id and edge.target_node_id in by_id:
            outgoing[edge.source_node_id].append(edge.target_node_id)
            incoming[edge.target_node_id] += 1
    ready = [node.id for node in workflow.graph.nodes if incoming[node.id] == 0]
    ordered: list[WorkflowNode] = []
    while ready:
        node_id = ready.pop(0)
        ordered.append(by_id[node_id])
        for child in outgoing[node_id]:
            incoming[child] -= 1
            if incoming[child] == 0:
                ready.append(child)
    return ordered


def _nodes_for_requested_outputs(workflow: Workflow, output_node_ids: list[str]) -> list[WorkflowNode]:
    """Return requested outputs plus only the upstream nodes they depend on."""
    ordered = _ordered_nodes(workflow)
    if not output_node_ids:
        return ordered
    by_id = {node.id: node for node in workflow.graph.nodes}
    upstream: dict[str, list[str]] = {node.id: [] for node in workflow.graph.nodes}
    for edge in workflow.graph.edges:
        if edge.source_node_id in by_id and edge.target_node_id in by_id:
            upstream[edge.target_node_id].append(edge.source_node_id)
    required: set[str] = set()
    pending = [node_id for node_id in output_node_ids if node_id in by_id]
    while pending:
        node_id = pending.pop()
        if node_id in required:
            continue
        required.add(node_id)
        pending.extend(upstream[node_id])
    return [node for node in ordered if node.id in required]


def _missing_configuration(node: WorkflowNode) -> str | None:
    if node.type == "incept.prompt.v1" and not str(node.params.get("prompt", "")).strip():
        return "Add a prompt before running image generation."
    if node.type == "incept.asset.keyframe.v1" and not node.params.get("asset_id"):
        return "Choose an approved keyframe before generating a video shot."
    if node.type == "incept.asset.reference.v1" and not (node.params.get("asset_ids") or node.params.get("brand_asset_ids") or str(node.params.get("brief", "")).strip()):
        return "Attach a reference or brand asset, or write a brief before running this workflow."
    if node.type == "incept.video.generate.v1" and not str(node.params.get("prompt", "")).strip():
        return "Describe the shot before generating a video."
    if node.type in {"incept.approval.image.v1", "incept.approval.video.v1"} and not node.params.get("asset_id"):
        return "Select one generated candidate before continuing."
    if node.type == "incept.approval.script.v1" and not node.params.get("production_id"):
        return "Review the generated script, then approve it before continuing."
    return None


def _workflow_user(user_id: str) -> User:
    """Worker calls existing adapters with an auditable user identity."""
    return User(id=user_id, name="Workflow user", email=f"{user_id}@workflow.local", role=Role.user, team="workflow")


def _run_image_node(run_id: str, workflow: Workflow, node: WorkflowNode) -> tuple[bool, str]:
    prompt_node = next((item for item in workflow.graph.nodes if item.type == "incept.prompt.v1"), None)
    prompt = str(node.params.get("prompt") or (prompt_node.params.get("prompt") if prompt_node else "") or "").strip()
    settings = get_settings()
    request = GenerationRequest(
        workspace_id=workflow.workspace_id,
        prompt=prompt,
        provider=str(node.params.get("provider", "gemini")),
        model=str(node.params.get("model") or settings.vertex_gemini_image_model),
        variants=max(1, min(3, int(node.params.get("variants", 1)))),
        aspect_ratio=str(node.params.get("aspect_ratio", "1:1")),
        output_sizes=[str(node.params.get("output_size", "1200x628"))],
        reference_asset_ids=[str(value) for value in (node.params.get("reference_asset_ids") or (prompt_node.params.get("reference_asset_ids", []) if prompt_node else [])) if value],
        created_by=workflow.created_by,
        theme=str(node.params.get("theme", workflow.title)),
    )
    user = _workflow_user(workflow.created_by)
    update_run_node(run_id, node.id, "running", "Submitting image generation.", 25)
    job = create_image_generation_job(request, user)
    if job.status is JobStatus.running:
        asyncio.run(run_generation_background(job.job_id, request, user))
        job = JOBS.get(job.job_id, job)
    if job.status is JobStatus.completed:
        update_run_node(run_id, node.id, "succeeded", "Image candidates are ready. Select one before downstream use.", 100, {"job_id": job.job_id, "asset_ids": job.output_asset_ids})
        return True, job.job_id
    update_run_node(run_id, node.id, "failed", job.message or "Image generation failed.", job.progress, {"job_id": job.job_id})
    return False, job.message or "Image generation failed."


def _workflow_brief(workflow: Workflow) -> str:
    reference = next((node for node in workflow.graph.nodes if node.type == "incept.asset.reference.v1"), None)
    return str(reference.params.get("brief", "") if reference else "").strip()


def _workflow_reference_asset_ids(workflow: Workflow) -> list[str]:
    reference = next((node for node in workflow.graph.nodes if node.type == "incept.asset.reference.v1"), None)
    if not reference:
        return []
    values = reference.params.get("asset_ids", [])
    return [str(asset_id) for asset_id in values if str(asset_id)] if isinstance(values, list) else []


def _workflow_brand_asset_ids(workflow: Workflow) -> list[str]:
    reference = next((node for node in workflow.graph.nodes if node.type == "incept.asset.reference.v1"), None)
    if not reference:
        return []
    values = reference.params.get("brand_asset_ids", [])
    return [str(asset_id) for asset_id in values if str(asset_id)] if isinstance(values, list) else []


def _workflow_production_settings(workflow: Workflow) -> tuple[int, str, str]:
    reference = next((node for node in workflow.graph.nodes if node.type == "incept.asset.reference.v1"), None)
    params = reference.params if reference else {}
    seconds = int(params.get("target_seconds", 30))
    target_seconds = seconds if seconds in {15, 30, 60} else 30
    aspect_ratio = str(params.get("aspect_ratio", "9:16"))
    resolution = str(params.get("resolution", "720p"))
    return target_seconds, aspect_ratio if aspect_ratio in {"9:16", "16:9"} else "9:16", resolution if resolution in {"720p", "1080p"} else "720p"


def _run_agent_node(run_id: str, workflow: Workflow, node: WorkflowNode, context: dict[str, str]) -> tuple[bool, str]:
    user = _workflow_user(workflow.created_by)
    brief = _workflow_brief(workflow)
    production_id = context.get("production_id")
    update_run_node(run_id, node.id, "running", f"Running {node.label}.", 20)
    if node.type == "incept.agent.creative-strategist.v1":
        target_seconds, aspect_ratio, resolution = _workflow_production_settings(workflow)
        reference_asset_ids = _workflow_reference_asset_ids(workflow)
        brand_asset_ids = _workflow_brand_asset_ids(workflow)
        production = create_video_production(VideoProductionCreateRequest(workspace_id=workflow.workspace_id, title=workflow.title, target_seconds=target_seconds, aspect_ratio=aspect_ratio, resolution=resolution), user)
        if reference_asset_ids or brand_asset_ids:
            production = update_video_production(
                production.production_id,
                VideoProductionUpdateRequest(
                    reference_asset_ids=reference_asset_ids,
                    asset_links=[
                        *[VideoProductionAssetLink(asset_id=asset_id, role="reference") for asset_id in reference_asset_ids],
                        *[VideoProductionAssetLink(asset_id=asset_id, role="brand") for asset_id in brand_asset_ids if asset_id not in reference_asset_ids],
                    ],
                ),
                user,
            )
        production = run_creative_director(production.production_id, VideoProductionAgentRequest(message=brief or "Create an original commercial direction from the supplied workflow inputs."), user)
        context["production_id"] = production.production_id
        direction = production.creative_direction
        update_run_node(
            run_id,
            node.id,
            "succeeded",
            "Creative direction and source contracts are ready.",
            100,
            {
                "production_id": production.production_id,
                "creative_direction": {
                    "reference_summary": direction.reference_summary,
                    "commercial_type": direction.commercial_type,
                    "output_language": direction.output_language,
                    "strengths_to_adapt": direction.strengths_to_adapt[:4],
                    "story_structure": direction.story_structure[:6],
                    "scene_and_character_notes": direction.scene_and_character_notes[:5],
                    "asset_request": direction.asset_request[:6],
                    "risks": direction.risks[:4],
                },
            },
        )
        return True, production.production_id
    if not production_id:
        return False, "Creative Strategist must complete before this agent can run."
    if node.type == "incept.agent.screenwriter.v1":
        production = run_script_agent(production_id, VideoProductionAgentRequest(message="Expand the approved creative direction into a timed commercial script."), user)
        update_run_node(run_id, node.id, "succeeded", "Structured script is ready for review.", 100, {"production_id": production.production_id, "script_revision": production.script.revision, "logline": production.script.logline, "script_text": production.script.raw_script})
        return True, production.production_id
    if node.type == "incept.agent.production-designer.v1":
        production = run_production_designer(production_id, VideoProductionAgentRequest(message="Create the reusable AI asset packs required by the script."), user)
        update_run_node(run_id, node.id, "succeeded", "Production design bible and asset-pack plan are ready.", 100, {"production_id": production.production_id})
        return True, production.production_id
    if node.type == "incept.agent.storyboard-director.v1":
        production = run_director_agent(production_id, VideoProductionAgentRequest(message="Create an editable storyboard from the script and design rules."), user)
        update_run_node(run_id, node.id, "succeeded", "Storyboard shot cards are ready for keyframe approval.", 100, {"production_id": production.production_id, "shot_count": len(production.shots)})
        return True, production.production_id
    return False, f"No adapter is registered for {node.type}."


def _run_video_node(run_id: str, workflow: Workflow, node: WorkflowNode) -> tuple[bool, str]:
    keyframe = next((item for item in workflow.graph.nodes if item.type == "incept.asset.keyframe.v1"), None)
    source_asset_id = str(node.params.get("source_asset_id") or (keyframe.params.get("asset_id") if keyframe else "") or "")
    request = VideoGenerationRequest(
        workspace_id=workflow.workspace_id,
        prompt=str(node.params.get("prompt", "")).strip(),
        model=str(node.params.get("model", "")),
        created_by=workflow.created_by,
        source_asset_id=source_asset_id,
        video_generation_mode=VideoGenerationMode.image_to_video,
        aspect_ratio=str(node.params.get("aspect_ratio", "9:16")),
        duration_seconds=int(node.params.get("duration_seconds", 4)),
        resolution=str(node.params.get("resolution", "720p")),
        variants=int(node.params.get("variants", 1)),
        include_audio=False,
        camera_preset=str(node.params.get("camera_preset", "")) or None,
    )
    user = _workflow_user(workflow.created_by)
    update_run_node(run_id, node.id, "running", "Submitting video generation.", 25)
    try:
        # The Run button is the user's explicit execution confirmation. Still use
        # the same persisted planning and budget guards as the dedicated Video UI;
        # a Workflow must never bypass either of them.
        plan = create_or_update_video_plan(
            VideoPlanRequest(
                workspace_id=request.workspace_id,
                prompt=f"Generate this approved workflow shot: {request.prompt}",
                created_by=workflow.created_by,
                source_asset_id=source_asset_id,
                reference_asset_ids=request.reference_asset_ids,
                video_generation_mode=request.video_generation_mode,
                aspect_ratio=request.aspect_ratio,
                duration_seconds=request.duration_seconds,
                resolution=request.resolution,
                variants=request.variants,
                include_audio=False,
            ),
            user,
        ).plan
        request = request.model_copy(update={"plan_id": plan.plan_id})
        request = confirm_video_generation_plan_for_request(request, user)
        assert_video_budget_available(request, user)
        job = create_video_generation_job(request, user)
    except RuntimeError as exc:
        detail = str(exc)
        update_run_node(run_id, node.id, "failed", detail, 0)
        return False, detail
    asyncio.run(run_video_generation_background(job.job_id, request, user))
    job = JOBS.get(job.job_id, job)
    if job.status is JobStatus.completed:
        update_run_node(run_id, node.id, "succeeded", "Video takes are ready. Select one before downstream use.", 100, {"job_id": job.job_id, "asset_ids": job.output_asset_ids})
        return True, job.job_id
    update_run_node(run_id, node.id, "failed", job.message or "Video generation failed.", job.progress, {"job_id": job.job_id})
    return False, job.message or "Video generation failed."


def _has_selected_output(workflow: Workflow, approval_type: str) -> bool:
    return any(node.type == approval_type and bool(node.params.get("asset_id")) for node in workflow.graph.nodes)


def _approved_script_production_id(workflow: Workflow) -> str:
    approval = next((node for node in workflow.graph.nodes if node.type == "incept.approval.script.v1"), None)
    return str(approval.params.get("production_id", "") if approval else "")


def _pure_node_cache_key(workflow: Workflow, node: WorkflowNode) -> str | None:
    """Only cache nodes that cannot submit provider work or create productions.

    Image/video/agent nodes deliberately stay out of this cache: reusing them could
    conceal a charge or a side effect. Their explicit selected-output reuse remains
    separate and visible to the user.
    """
    if node.type not in {
        "incept.asset.reference.v1", "incept.asset.keyframe.v1", "incept.prompt.v1",
    }:
        return None
    return workflow_node_cache_key(workflow.workspace_id, node.type, {"params": node.params})


def execute_one_queued_run() -> bool:
    claimed = claim_next_run()
    if not claimed:
        return False
    run, workflow = claimed
    context: dict[str, str] = {}
    approved_script_production_id = _approved_script_production_id(workflow)
    if approved_script_production_id:
        context["production_id"] = approved_script_production_id
    try:
        for node in _nodes_for_requested_outputs(workflow, run.requested_output_node_ids):
            if is_run_cancelled(run.run_id):
                return True
            if node.type == "incept.group.v1":
                update_run_node(run.run_id, node.id, "succeeded", "Canvas group is non-executable and was skipped.", 100, {"group_member_ids": node.params.get("group_member_ids", [])})
                continue
            update_run_node(run.run_id, node.id, "running", "Preparing node execution.", 10)
            missing = _missing_configuration(node)
            if missing:
                update_run_node(run.run_id, node.id, "blocked", missing, 0)
                update_run_status(run.run_id, WorkflowRunStatus.failed, f"{node.label}: {missing}")
                return True
            cache_key = _pure_node_cache_key(workflow, node)
            cached = get_cached_node_result(cache_key) if cache_key else None
            if cached is not None:
                update_run_node(run.run_id, node.id, "succeeded", "Reused a cached deterministic node result.", 100, {**cached, "cache_hit": True})
                continue
            # Input nodes are deterministic. Provider and agent adapters are added
            # one by one below this boundary, never as arbitrary graph code.
            if node.type.startswith("incept.asset.") or node.type == "incept.prompt.v1":
                result = {"params": node.params}
                update_run_node(run.run_id, node.id, "succeeded", "Input is ready for downstream nodes.", 100, result)
                if cache_key:
                    cache_node_result(workflow.workspace_id, node.type, cache_key, result)
                continue
            if node.type == "incept.image.generate.v1":
                if _has_selected_output(workflow, "incept.approval.image.v1"):
                    update_run_node(run.run_id, node.id, "succeeded", "Reusing the candidate selected in this workflow.", 100)
                    continue
                succeeded, detail = _run_image_node(run.run_id, workflow, node)
                if not succeeded:
                    update_run_status(run.run_id, WorkflowRunStatus.failed, detail)
                    return True
                continue
            if node.type.startswith("incept.agent."):
                if workflow.template.value == "script" and approved_script_production_id and node.type in {
                    "incept.agent.creative-strategist.v1", "incept.agent.screenwriter.v1",
                }:
                    update_run_node(run.run_id, node.id, "succeeded", "Reusing the reviewed script production.", 100, {"production_id": approved_script_production_id})
                    continue
                succeeded, detail = _run_agent_node(run.run_id, workflow, node, context)
                if not succeeded:
                    update_run_node(run.run_id, node.id, "failed", detail, 0)
                    update_run_status(run.run_id, WorkflowRunStatus.failed, detail)
                    return True
                continue
            if node.type == "incept.video.generate.v1":
                if _has_selected_output(workflow, "incept.approval.video.v1"):
                    update_run_node(run.run_id, node.id, "succeeded", "Reusing the take selected in this workflow.", 100)
                    continue
                succeeded, detail = _run_video_node(run.run_id, workflow, node)
                if not succeeded:
                    update_run_status(run.run_id, WorkflowRunStatus.failed, detail)
                    return True
                continue
            if node.type in {"incept.approval.image.v1", "incept.approval.video.v1"}:
                asset_id = str(node.params.get("asset_id"))
                output = record_output(
                    run, node_id=node.id, output_type="video" if node.type.endswith("video.v1") else "image", value_id=asset_id,
                    metadata={"approval_node_type": node.type},
                )
                update_run_node(run.run_id, node.id, "approved", "Selected candidate is approved for downstream use.", 100, {"asset_id": asset_id, "output_id": output.output_id})
                if cache_key:
                    cache_node_result(workflow.workspace_id, node.type, cache_key, {"asset_id": asset_id, "output_id": output.output_id})
                continue
            if node.type == "incept.approval.script.v1":
                production_id = str(node.params.get("production_id"))
                output = record_output(run, node_id=node.id, output_type="script", value_id=production_id, metadata={"script_revision": node.params.get("script_revision")})
                update_run_node(run.run_id, node.id, "approved", "Reviewed script is approved for production design and storyboarding.", 100, {"production_id": production_id, "script_revision": node.params.get("script_revision"), "output_id": output.output_id})
                if cache_key:
                    cache_node_result(workflow.workspace_id, node.type, cache_key, {"production_id": production_id, "script_revision": node.params.get("script_revision"), "output_id": output.output_id})
                continue
            if node.type == "incept.delivery.v1":
                production_id = context.get("production_id")
                if not production_id:
                    update_run_node(run.run_id, node.id, "blocked", "Storyboard Director must complete before delivery can be prepared.", 0)
                    update_run_status(run.run_id, WorkflowRunStatus.failed, "Commercial delivery is missing its storyboard.")
                    return True
                output = record_output(run, node_id=node.id, output_type="commercial", value_id=production_id, metadata={"stage": "storyboard"})
                update_run_node(run.run_id, node.id, "succeeded", "Commercial production is ready for shot and asset review.", 100, {"production_id": production_id, "output_id": output.output_id})
                continue
            update_run_node(run.run_id, node.id, "blocked", f"{node.label} is not connected to its production adapter yet.", 0)
            update_run_status(run.run_id, WorkflowRunStatus.failed, f"{node.label} needs its production adapter configured.")
            return True
        update_run_status(run.run_id, WorkflowRunStatus.succeeded, "Workflow completed.")
    except Exception:
        logger.exception("Workflow run %s failed", run.run_id)
        update_run_status(run.run_id, WorkflowRunStatus.failed, "The workflow worker encountered an unexpected error. You can retry after reviewing the node details.")
    return True


def worker_loop(poll_seconds: float = 0.8) -> None:
    while not _stop.is_set():
        if not execute_one_queued_run():
            _stop.wait(poll_seconds)


def start_workflow_worker() -> threading.Thread:
    _stop.clear()
    thread = threading.Thread(target=worker_loop, daemon=True, name="studio-workflow-worker")
    thread.start()
    return thread


def stop_workflow_worker() -> None:
    _stop.set()
