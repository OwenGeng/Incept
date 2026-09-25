from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.dependencies import get_db
from app.ai_video.models.integration_hub import ComfyWorkflow, CustomEndpoint
from app.ai_video.models.production_control import ProductionArtifact, ProductionRevision
from app.ai_video.schemas.studio.integration_hub import MemoryCreate
from app.ai_video.services.studio.integration_hub import (
    authenticate_api_key,
    create_memory,
    execute_comfy_workflow,
    execute_custom_endpoint,
    list_memories,
)
from app.ai_video.services.studio.production_control import (
    approve_production_revision,
    build_production_workflow_plan,
    snapshot_shot_plan_revision,
)

router = APIRouter()
PROTOCOL_VERSION = "2026-07-28"
LEGACY_VERSION = "2025-11-25"


TOOLS: list[dict[str, Any]] = [
    {
        "name": "production.get_plan",
        "description": "Read the authoritative next action, gates, blockers, and artifact currency for an AI Video project.",
        "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]},
    },
    {
        "name": "production.list_revisions",
        "description": "List immutable production revisions for a project.",
        "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}, "kind": {"type": "string"}}, "required": ["project_id"]},
    },
    {
        "name": "production.list_artifacts",
        "description": "List project artifacts including candidate/selected lifecycle and current/stale currency.",
        "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]},
    },
    {
        "name": "production.snapshot_shot_plan",
        "description": "Create a draft Shot Plan snapshot from persisted shots. This does not approve it.",
        "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]},
    },
    {
        "name": "production.approve_revision",
        "description": "Approve a revision and supersede its prior approved sibling. Requires explicit confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}, "revision_id": {"type": "string"}, "confirm": {"type": "boolean"}},
            "required": ["project_id", "revision_id", "confirm"],
        },
    },
    {
        "name": "memory.search",
        "description": "Search active user and project memories used by the Creative Agent.",
        "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}, "query": {"type": "string"}}, "required": ["project_id"]},
    },
    {
        "name": "memory.put",
        "description": "Save a durable user or project memory with provenance and confidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"}, "scope": {"type": "string", "enum": ["project", "user"]},
                "kind": {"type": "string", "enum": ["preference", "fact", "decision", "summary"]},
                "content": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["project_id", "content"],
        },
    },
    {
        "name": "integrations.list",
        "description": "List configured custom endpoints and imported ComfyUI workflows without credentials.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "integrations.call_endpoint",
        "description": "Preview or call a configured endpoint. A real external call requires confirm=true and write:production.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "endpoint_id": {"type": "string"}, "input": {"type": "object"}, "confirm": {"type": "boolean"},
                "wait_for_result": {"type": "boolean"},
            },
            "required": ["endpoint_id", "input", "confirm"],
        },
    },
    {
        "name": "integrations.run_comfy",
        "description": "Bind semantic inputs and preview or run a ready ComfyUI workflow. Real execution requires confirm=true and write:production.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"}, "input": {"type": "object"}, "confirm": {"type": "boolean"},
                "persist_output": {"type": "boolean"}, "project_id": {"type": "string"}, "shot_id": {"type": "string"},
                "artifact_type": {"type": "string"},
            },
            "required": ["workflow_id", "input", "confirm"],
        },
    },
]


def _rpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _rpc_error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _tool_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    serialized = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return {
        "content": [{"type": "text", "text": serialized}],
        "structuredContent": value if isinstance(value, dict) else {"result": value},
        "isError": is_error,
    }


def _require_scope(key: Any, scope: str) -> None:
    if scope not in set(key.scopes or []):
        raise HTTPException(status_code=403, detail=f"Automation API key requires scope: {scope}")


async def _call_tool(db: AsyncSession, key: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
    project_id = str(args.get("project_id") or "")
    if name == "production.get_plan":
        _require_scope(key, "read:production")
        return _tool_result((await build_production_workflow_plan(db, project_id=project_id)).model_dump(mode="json"))
    if name == "production.list_revisions":
        _require_scope(key, "read:production")
        stmt = select(ProductionRevision).where(ProductionRevision.project_id == project_id)
        if args.get("kind"):
            stmt = stmt.where(ProductionRevision.kind == str(args["kind"]))
        rows = list((await db.execute(stmt.order_by(ProductionRevision.created_at.desc()))).scalars().all())
        return _tool_result({"revisions": [
            {"id": row.id, "kind": row.kind, "scope_type": row.scope_type, "scope_id": row.scope_id, "revision_number": row.revision_number, "state": row.state, "payload": row.payload, "input_fingerprint": row.input_fingerprint}
            for row in rows
        ]})
    if name == "production.list_artifacts":
        _require_scope(key, "read:production")
        rows = list((await db.execute(select(ProductionArtifact).where(ProductionArtifact.project_id == project_id).order_by(ProductionArtifact.created_at.desc()))).scalars().all())
        return _tool_result({"artifacts": [
            {"id": row.id, "shot_id": row.shot_id, "artifact_type": row.artifact_type, "file_id": row.file_id, "currency": row.currency, "lifecycle": row.lifecycle, "input_fingerprint": row.input_fingerprint}
            for row in rows
        ]})
    if name == "production.snapshot_shot_plan":
        _require_scope(key, "write:production")
        row = await snapshot_shot_plan_revision(db, project_id=project_id, created_by=f"external:{key.key_prefix}")
        return _tool_result({"revision_id": row.id, "state": row.state, "revision_number": row.revision_number})
    if name == "production.approve_revision":
        _require_scope(key, "write:production")
        if args.get("confirm") is not True:
            return _tool_result({"code": "confirmation_required", "message": "Set confirm=true only after explicit user approval."}, is_error=True)
        row = await approve_production_revision(
            db,
            project_id=project_id,
            revision_id=str(args.get("revision_id") or ""),
            approved_by=f"external:{key.key_prefix}",
        )
        return _tool_result({"revision_id": row.id, "state": row.state})
    if name == "memory.search":
        _require_scope(key, "read:memory")
        rows = await list_memories(db, project_id=project_id, query=str(args.get("query") or "") or None)
        return _tool_result({"memories": [
            {"id": row.id, "scope": row.scope, "kind": row.kind, "content": row.content, "tags": row.tags, "source": row.source, "pinned": row.pinned, "confidence": row.confidence}
            for row in rows
        ]})
    if name == "memory.put":
        _require_scope(key, "write:memory")
        body = MemoryCreate(
            scope=args.get("scope") or "project",
            kind=args.get("kind") or "fact",
            content=str(args.get("content") or ""),
            tags=args.get("tags") or [],
            source=f"mcp:{key.key_prefix}",
            confidence=float(args.get("confidence", 1)),
        )
        row = await create_memory(db, project_id=project_id, body=body, owner_key="local-user")
        return _tool_result({"memory_id": row.id, "scope": row.scope, "kind": row.kind})
    if name == "integrations.list":
        _require_scope(key, "read:production")
        endpoints = list((await db.execute(select(CustomEndpoint).order_by(CustomEndpoint.name.asc()))).scalars().all())
        workflows = list((await db.execute(select(ComfyWorkflow).order_by(ComfyWorkflow.name.asc()))).scalars().all())
        return _tool_result({
            "endpoints": [{"id": row.id, "name": row.name, "category": row.category, "status": row.status, "capabilities": row.capabilities} for row in endpoints],
            "comfy_workflows": [{"id": row.id, "name": row.name, "status": row.status, "endpoint_id": row.endpoint_id, "capabilities": row.capabilities} for row in workflows],
        })
    if name == "integrations.call_endpoint":
        confirmed = args.get("confirm") is True
        _require_scope(key, "write:production" if confirmed else "read:production")
        endpoint = await db.get(CustomEndpoint, str(args.get("endpoint_id") or ""))
        if endpoint is None:
            raise HTTPException(status_code=404, detail="Custom endpoint not found")
        result = await execute_custom_endpoint(
            db,
            endpoint,
            inputs=args.get("input") if isinstance(args.get("input"), dict) else {},
            confirm_external_call=confirmed,
            wait_for_result=bool(args.get("wait_for_result")),
        )
        return _tool_result(result.model_dump(mode="json"))
    if name == "integrations.run_comfy":
        confirmed = args.get("confirm") is True
        _require_scope(key, "write:production" if confirmed else "read:production")
        workflow = await db.get(ComfyWorkflow, str(args.get("workflow_id") or ""))
        if workflow is None:
            raise HTTPException(status_code=404, detail="ComfyUI workflow not found")
        result = await execute_comfy_workflow(
            db,
            workflow,
            inputs=args.get("input") if isinstance(args.get("input"), dict) else {},
            confirm_external_call=confirmed,
            wait_for_result=bool(args.get("wait_for_result", True)),
            persist_output=bool(args.get("persist_output")),
            project_id=str(args.get("project_id") or "") or None,
            shot_id=str(args.get("shot_id") or "") or None,
            artifact_type=str(args.get("artifact_type") or "") or None,
        )
        return _tool_result(result.model_dump(mode="json"))
    return _tool_result({"code": "unknown_tool", "message": f"Unknown tool: {name}"}, is_error=True)


@router.post("/automation/mcp")
async def mcp_endpoint(
    request: Request,
    authorization: str | None = Header(None),
    x_incept_mcp_authorization: str | None = Header(None, alias="X-Incept-MCP-Authorization"),
    mcp_protocol_version: str | None = Header(None, alias="MCP-Protocol-Version"),
    mcp_method: str | None = Header(None, alias="Mcp-Method"),
    mcp_name: str | None = Header(None, alias="Mcp-Name"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    automation_authorization = x_incept_mcp_authorization or authorization
    if not automation_authorization or not automation_authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer automation API key required")
    key = await authenticate_api_key(db, automation_authorization.split(" ", 1)[1].strip())
    body = await request.json()
    request_id = body.get("id")
    method = str(body.get("method") or "")
    params = body.get("params") if isinstance(body.get("params"), dict) else {}

    if mcp_protocol_version == PROTOCOL_VERSION:
        expected_name = str(params.get("name") or "") if method == "tools/call" else None
        if mcp_method != method or (expected_name and mcp_name != expected_name):
            return JSONResponse(_rpc_error(request_id, -32020, "MCP routing headers do not match the request"), status_code=400)
    try:
        if method == "server/discover":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "supportedProtocolVersions": [PROTOCOL_VERSION, LEGACY_VERSION],
                "serverInfo": {"name": "incept-ai-video", "version": "1.0.0"},
                "capabilities": {"tools": {"listChanged": False}},
            }
        elif method == "initialize":
            result = {
                "protocolVersion": LEGACY_VERSION,
                "serverInfo": {"name": "incept-ai-video", "version": "1.0.0"},
                "capabilities": {"tools": {"listChanged": False}},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = await _call_tool(db, key, str(params.get("name") or ""), params.get("arguments") or {})
        elif method == "ping":
            result = {}
        else:
            return JSONResponse(_rpc_error(request_id, -32601, "Method not found"))
        return JSONResponse(_rpc_result(request_id, result))
    except HTTPException as exc:
        return JSONResponse(_rpc_error(request_id, -32000, str(exc.detail)), status_code=200)
    except Exception as exc:
        return JSONResponse(_rpc_error(request_id, -32603, "Internal error", {"type": type(exc).__name__}), status_code=200)


__all__ = ["router", "TOOLS"]
