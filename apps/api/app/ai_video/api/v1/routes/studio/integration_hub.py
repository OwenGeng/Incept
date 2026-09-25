from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.dependencies import get_db
from app.ai_video.models.integration_hub import (
    AutomationApiKey,
    ComfyWorkflow,
    CustomEndpoint,
    EndpointMarketEntry,
    ProjectMemory,
)
from app.ai_video.schemas.common import ApiResponse, created_response, success_response
from app.ai_video.schemas.studio.integration_hub import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    ComfyWorkflowCreate,
    ComfyWorkflowExecuteRequest,
    ComfyWorkflowExecutionRead,
    ComfyWorkflowRead,
    CustomEndpointCreate,
    CustomEndpointRead,
    CustomEndpointWrite,
    EndpointExecuteRequest,
    EndpointExecutionRead,
    EndpointMarketEntryCreate,
    EndpointMarketEntryRead,
    EndpointValidateRequest,
    MarketInstallRequest,
    MemoryCreate,
    MemoryRead,
)
from app.ai_video.services.studio.integration_hub import (
    create_api_key_record,
    create_comfy_workflow,
    create_custom_endpoint,
    create_market_entry,
    create_memory,
    execute_custom_endpoint,
    execute_comfy_workflow,
    install_market_entry,
    list_memories,
    update_custom_endpoint,
    validate_endpoint_response,
)

router = APIRouter()


@router.get("/integrations/endpoints", response_model=ApiResponse[list[CustomEndpointRead]])
async def list_endpoints(db: AsyncSession = Depends(get_db)) -> ApiResponse[list[CustomEndpointRead]]:
    rows = list((await db.execute(select(CustomEndpoint).order_by(CustomEndpoint.updated_at.desc()))).scalars().all())
    return success_response([CustomEndpointRead.model_validate(row) for row in rows])


@router.post(
    "/integrations/endpoints",
    response_model=ApiResponse[CustomEndpointRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_endpoint(body: CustomEndpointCreate, db: AsyncSession = Depends(get_db)) -> ApiResponse[CustomEndpointRead]:
    row = await create_custom_endpoint(db, body)
    return created_response(CustomEndpointRead.model_validate(row))


@router.put("/integrations/endpoints/{endpoint_id}", response_model=ApiResponse[CustomEndpointRead])
async def update_endpoint(
    endpoint_id: str,
    body: CustomEndpointWrite,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CustomEndpointRead]:
    row = await db.get(CustomEndpoint, endpoint_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Custom endpoint not found")
    row = await update_custom_endpoint(db, row, body)
    return success_response(CustomEndpointRead.model_validate(row))


@router.post("/integrations/endpoints/{endpoint_id}/validate", response_model=ApiResponse[EndpointExecutionRead])
async def validate_endpoint(
    endpoint_id: str,
    body: EndpointValidateRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[EndpointExecutionRead]:
    row = await db.get(CustomEndpoint, endpoint_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Custom endpoint not found")
    return success_response(validate_endpoint_response(row, body.sample_response))


@router.post("/integrations/endpoints/{endpoint_id}/execute", response_model=ApiResponse[EndpointExecutionRead])
async def execute_endpoint(
    endpoint_id: str,
    body: EndpointExecuteRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[EndpointExecutionRead]:
    row = await db.get(CustomEndpoint, endpoint_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Custom endpoint not found")
    return success_response(
        await execute_custom_endpoint(
            db,
            row,
            inputs=body.input,
            confirm_external_call=body.confirm_external_call,
            wait_for_result=body.wait_for_result,
        )
    )


@router.get("/integrations/market", response_model=ApiResponse[list[EndpointMarketEntryRead]])
async def list_market(db: AsyncSession = Depends(get_db)) -> ApiResponse[list[EndpointMarketEntryRead]]:
    rows = list((await db.execute(select(EndpointMarketEntry).order_by(EndpointMarketEntry.updated_at.desc()))).scalars().all())
    return success_response([EndpointMarketEntryRead.model_validate(row) for row in rows])


@router.post(
    "/integrations/market",
    response_model=ApiResponse[EndpointMarketEntryRead],
    status_code=status.HTTP_201_CREATED,
)
async def publish_market_entry(
    body: EndpointMarketEntryCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[EndpointMarketEntryRead]:
    row = await create_market_entry(db, body)
    return created_response(EndpointMarketEntryRead.model_validate(row))


@router.post("/integrations/market/{entry_id}/install", response_model=ApiResponse[dict])
async def install_market(
    entry_id: str,
    body: MarketInstallRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    entry = await db.get(EndpointMarketEntry, entry_id)
    if entry is None or entry.status != "published":
        raise HTTPException(status_code=404, detail="Published market entry not found")
    endpoint, workflow = await install_market_entry(db, entry, body)
    return success_response(
        {
            "endpoint": CustomEndpointRead.model_validate(endpoint).model_dump(mode="json") if endpoint else None,
            "comfy_workflow": ComfyWorkflowRead.model_validate(workflow).model_dump(mode="json") if workflow else None,
        }
    )


@router.get("/integrations/comfy-workflows", response_model=ApiResponse[list[ComfyWorkflowRead]])
async def list_comfy_workflows(db: AsyncSession = Depends(get_db)) -> ApiResponse[list[ComfyWorkflowRead]]:
    rows = list((await db.execute(select(ComfyWorkflow).order_by(ComfyWorkflow.updated_at.desc()))).scalars().all())
    return success_response([ComfyWorkflowRead.model_validate(row) for row in rows])


@router.post(
    "/integrations/comfy-workflows",
    response_model=ApiResponse[ComfyWorkflowRead],
    status_code=status.HTTP_201_CREATED,
)
async def import_comfy_workflow(
    body: ComfyWorkflowCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ComfyWorkflowRead]:
    row = await create_comfy_workflow(db, body)
    return created_response(ComfyWorkflowRead.model_validate(row))


@router.post(
    "/integrations/comfy-workflows/{workflow_id}/execute",
    response_model=ApiResponse[ComfyWorkflowExecutionRead],
)
async def run_comfy_workflow(
    workflow_id: str,
    body: ComfyWorkflowExecuteRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ComfyWorkflowExecutionRead]:
    workflow = await db.get(ComfyWorkflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="ComfyUI workflow not found")
    return success_response(
        await execute_comfy_workflow(
            db,
            workflow,
            inputs=body.input,
            confirm_external_call=body.confirm_external_call,
            wait_for_result=body.wait_for_result,
            persist_output=body.persist_output,
            project_id=body.project_id,
            shot_id=body.shot_id,
            artifact_type=body.artifact_type,
        )
    )


@router.get("/automation/api-keys", response_model=ApiResponse[list[ApiKeyRead]])
async def list_api_keys(db: AsyncSession = Depends(get_db)) -> ApiResponse[list[ApiKeyRead]]:
    rows = list((await db.execute(select(AutomationApiKey).order_by(AutomationApiKey.created_at.desc()))).scalars().all())
    return success_response([ApiKeyRead.model_validate(row) for row in rows])


@router.post(
    "/automation/api-keys",
    response_model=ApiResponse[ApiKeyCreated],
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(body: ApiKeyCreate, db: AsyncSession = Depends(get_db)) -> ApiResponse[ApiKeyCreated]:
    row, token = create_api_key_record(body.name, body.scopes)
    db.add(row)
    await db.flush()
    return created_response(ApiKeyCreated(id=row.id, name=row.name, key_prefix=row.key_prefix, scopes=row.scopes, token=token))


@router.post("/automation/api-keys/{key_id}/revoke", response_model=ApiResponse[ApiKeyRead])
async def revoke_api_key(key_id: str, db: AsyncSession = Depends(get_db)) -> ApiResponse[ApiKeyRead]:
    row = await db.get(AutomationApiKey, key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Automation API key not found")
    row.status = "revoked"
    await db.flush()
    await db.refresh(row)
    return success_response(ApiKeyRead.model_validate(row))


@router.get("/projects/{project_id}/memories", response_model=ApiResponse[list[MemoryRead]])
async def get_memories(
    project_id: str,
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[MemoryRead]]:
    rows = await list_memories(db, project_id=project_id, query=q)
    return success_response([MemoryRead.model_validate(row) for row in rows])


@router.post(
    "/projects/{project_id}/memories",
    response_model=ApiResponse[MemoryRead],
    status_code=status.HTTP_201_CREATED,
)
async def put_memory(
    project_id: str,
    body: MemoryCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[MemoryRead]:
    row = await create_memory(db, project_id=project_id, body=body)
    return created_response(MemoryRead.model_validate(row))


@router.post("/projects/{project_id}/memories/{memory_id}/archive", response_model=ApiResponse[MemoryRead])
async def archive_memory(
    project_id: str,
    memory_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[MemoryRead]:
    row = await db.get(ProjectMemory, memory_id)
    if row is None or (row.project_id not in {None, project_id}):
        raise HTTPException(status_code=404, detail="Memory not found")
    row.status = "archived"
    await db.flush()
    await db.refresh(row)
    return success_response(MemoryRead.model_validate(row))


__all__ = ["router"]
