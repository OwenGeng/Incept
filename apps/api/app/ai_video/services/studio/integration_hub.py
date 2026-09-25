from __future__ import annotations

import copy
import asyncio
import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import socket
import tempfile
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse, urlunsplit
from uuid import uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.models.integration_hub import (
    AutomationApiKey,
    ComfyWorkflow,
    CustomEndpoint,
    EndpointMarketEntry,
    ProjectMemory,
)
from app.ai_video.models.studio import Project
from app.ai_video.models.production_control import ProductionArtifact
from app.ai_video.models.studio import Chapter, FileItem, Shot
from app.ai_video.models.types import FileType
from app.ai_video.schemas.studio.integration_hub import (
    ComfyWorkflowCreate,
    ComfyWorkflowExecutionRead,
    CustomEndpointCreate,
    CustomEndpointWrite,
    EndpointExecutionRead,
    EndpointMarketEntryCreate,
    MarketInstallRequest,
    MemoryCreate,
)
from app.ai_video.core import storage
from app.ai_video.config import settings
from app.ai_video.services.studio.file_usages import upsert_file_usage


_TOKEN = re.compile(r"\$\{input\.([A-Za-z0-9_.-]+)\}")
_SECRET_KEYS = {"api_key", "apikey", "access_token", "refresh_token", "secret", "password", "private_key"}
_METADATA_HOSTS = {
    "metadata.google.internal",
    "metadata.google.internal.",
    "instance-data.ec2.internal",
    "instance-data.ec2.internal.",
}


def _parsed_outbound_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=422, detail="Outbound URL must use http or https")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Credentials must not be embedded in an outbound URL")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise HTTPException(status_code=422, detail="Outbound URL requires a hostname")
    if host in {item.rstrip(".") for item in _METADATA_HOSTS}:
        raise HTTPException(status_code=422, detail="Cloud metadata destinations are not allowed")
    return parsed, host


def _private_host_is_deployment_allowed(host: str) -> bool:
    return host in settings.outbound_private_host_allowlist_set


def _reject_non_public_ip(host: str, address: str) -> None:
    try:
        parsed_ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Outbound hostname resolved to an invalid address") from exc
    if parsed_ip.is_link_local or parsed_ip.is_multicast or parsed_ip.is_unspecified or parsed_ip.is_reserved:
        raise HTTPException(status_code=422, detail="Link-local, metadata, multicast, unspecified, and reserved destinations are not allowed")
    if not parsed_ip.is_global and not _private_host_is_deployment_allowed(host):
        raise HTTPException(status_code=422, detail="Private, loopback, link-local, and reserved destinations are not allowed")


async def validate_outbound_url(url: str) -> None:
    """Fail closed for SSRF targets before every server-side request."""

    parsed, host = _parsed_outbound_url(url)
    try:
        _reject_non_public_ip(host, host)
        return
    except HTTPException:
        try:
            ipaddress.ip_address(host.split("%", 1)[0])
        except ValueError:
            pass
        else:
            raise

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Outbound URL has an invalid port") from exc
    loop = asyncio.get_running_loop()
    try:
        records = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise HTTPException(status_code=422, detail="Outbound hostname could not be resolved") from exc
    addresses = {str(record[4][0]) for record in records if record[4]}
    if not addresses:
        raise HTTPException(status_code=422, detail="Outbound hostname resolved to no addresses")
    for address in addresses:
        _reject_non_public_ip(host, address)


def _reject_embedded_secrets(value: Any, *, path: str = "template") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _SECRET_KEYS and item is not None and item not in ("", "${credential}"):
                raise HTTPException(status_code=422, detail=f"Secret material is not allowed in {path}.{key}; use credential_env")
            _reject_embedded_secrets(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_embedded_secrets(item, path=f"{path}[{index}]")


def _read_path(value: Any, path: str | None) -> Any:
    if not path:
        return None
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def _render_template(value: Any, inputs: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render_template(item, inputs) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_template(item, inputs) for item in value]
    if not isinstance(value, str):
        return value
    match = _TOKEN.fullmatch(value)
    if match:
        return _read_path(inputs, match.group(1))
    return _TOKEN.sub(lambda item: str(_read_path(inputs, item.group(1)) or ""), value)


def _request_preview(endpoint: CustomEndpoint, inputs: dict[str, Any], contract: dict[str, Any] | None = None) -> dict[str, Any]:
    contract = contract or endpoint.request_contract or {}
    base = endpoint.base_url.rstrip("/")
    path = str(_render_template(contract.get("path") or "", inputs))
    return {
        "method": str(contract.get("method") or "POST").upper(),
        "url": f"{base}/{path.lstrip('/')}",
        "headers": _render_template(contract.get("headers") or {}, inputs),
        "body": _render_template(contract.get("body_template") or {}, inputs),
        "credential_env": endpoint.credential_env,
        "auth_type": endpoint.auth_type,
    }


def validate_endpoint_response(
    endpoint: CustomEndpoint,
    response: dict[str, Any],
    response_contract: dict[str, Any] | None = None,
) -> EndpointExecutionRead:
    contract = response_contract or endpoint.response_contract or {}
    output = _read_path(response, contract.get("output_path"))
    job_id = _read_path(response, contract.get("job_id_path"))
    remote_status = _read_path(response, contract.get("status_path"))
    error = _read_path(response, contract.get("error_path"))
    if output is None and job_id is None and error is None and remote_status is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "response_mapping_failed",
                "message": "The response matched none of output_path, job_id_path, or error_path",
            },
        )
    return EndpointExecutionRead(
        request_preview={},
        status=str(remote_status or ("failed" if error else "submitted" if job_id is not None else "succeeded")),
        output=output,
        job_id=job_id,
        error=error,
        response_preview=response,
    )


async def create_custom_endpoint(db: AsyncSession, body: CustomEndpointCreate) -> CustomEndpoint:
    endpoint_id = body.id or f"endpoint_{uuid4().hex}"
    if await db.get(CustomEndpoint, endpoint_id) is not None:
        raise HTTPException(status_code=409, detail="Endpoint ID already exists")
    parsed = urlparse(str(body.base_url))
    if parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Credentials must not be embedded in base_url")
    _parsed_outbound_url(str(body.base_url))
    _reject_embedded_secrets(body.request_contract, path="request_contract")
    endpoint = CustomEndpoint(
        id=endpoint_id,
        **body.model_dump(exclude={"id", "base_url"}),
        base_url=str(body.base_url).rstrip("/"),
    )
    db.add(endpoint)
    await db.flush()
    await db.refresh(endpoint)
    return endpoint


async def update_custom_endpoint(db: AsyncSession, endpoint: CustomEndpoint, body: CustomEndpointWrite) -> CustomEndpoint:
    parsed = urlparse(str(body.base_url))
    if parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Credentials must not be embedded in base_url")
    _parsed_outbound_url(str(body.base_url))
    _reject_embedded_secrets(body.request_contract, path="request_contract")
    data = body.model_dump(exclude={"base_url"})
    for key, value in data.items():
        setattr(endpoint, key, value)
    endpoint.base_url = str(body.base_url).rstrip("/")
    endpoint.config_version += 1
    await db.flush()
    await db.refresh(endpoint)
    return endpoint


async def execute_custom_endpoint(
    db: AsyncSession,
    endpoint: CustomEndpoint,
    *,
    inputs: dict[str, Any],
    confirm_external_call: bool,
    wait_for_result: bool = False,
    client: httpx.AsyncClient | None = None,
) -> EndpointExecutionRead:
    preview = _request_preview(endpoint, inputs)
    if not confirm_external_call:
        return EndpointExecutionRead(request_preview=preview, status="confirmation_required")
    if endpoint.status not in {"testing", "active"}:
        raise HTTPException(status_code=409, detail="Endpoint must be testing or active before execution")
    headers = dict(preview["headers"])
    if endpoint.auth_type != "none":
        secret = os.getenv(endpoint.credential_env or "")
        if not secret:
            raise HTTPException(status_code=409, detail=f"Credential environment variable is unavailable: {endpoint.credential_env}")
        if endpoint.auth_type == "bearer":
            headers[endpoint.auth_header] = f"Bearer {secret}"
        else:
            headers[endpoint.auth_header] = secret
    timeout = float((endpoint.capabilities or {}).get("timeout_seconds") or 30)
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout)
    try:
        await validate_outbound_url(str(preview["url"]))
        response = await active_client.request(
            preview["method"],
            preview["url"],
            headers=headers,
            json=preview["body"] if preview["method"] != "GET" else None,
            params=preview["body"] if preview["method"] == "GET" else None,
            follow_redirects=False,
        )
        if response.is_redirect:
            raise HTTPException(status_code=502, detail="Custom endpoint redirects are not allowed")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail="Endpoint response must be a JSON object")
        result = validate_endpoint_response(endpoint, payload)
        result.request_preview = preview
        if wait_for_result and result.job_id is not None and endpoint.polling_contract:
            submitted_job_id = result.job_id
            polling = endpoint.polling_contract
            method = str(polling.get("method") or "GET").upper()
            path = str(polling.get("path") or "")
            if method not in {"GET", "POST", "PUT", "PATCH"} or not path.startswith("/") or "://" in path:
                raise HTTPException(status_code=422, detail="polling_contract requires an explicit method and absolute path")
            max_attempts = min(max(int(polling.get("max_attempts") or 20), 1), 60)
            interval_seconds = min(max(float(polling.get("interval_seconds", 2)), 0), 10)
            terminal_statuses = {str(item).lower() for item in polling.get("terminal_statuses", ["succeeded", "success", "completed", "failed", "error"])}
            pending_statuses = {str(item).lower() for item in polling.get("pending_statuses", ["submitted", "queued", "pending", "running", "processing"])}
            poll_inputs = {**inputs, "job_id": result.job_id}
            for attempt in range(max_attempts):
                if attempt and interval_seconds:
                    await asyncio.sleep(interval_seconds)
                poll_preview = _request_preview(endpoint, poll_inputs, polling)
                await validate_outbound_url(str(poll_preview["url"]))
                poll_response = await active_client.request(
                    poll_preview["method"],
                    poll_preview["url"],
                    headers=headers | dict(poll_preview["headers"]),
                    json=poll_preview["body"] if poll_preview["method"] != "GET" else None,
                    params=poll_preview["body"] if poll_preview["method"] == "GET" else None,
                    follow_redirects=False,
                )
                if poll_response.is_redirect:
                    raise HTTPException(status_code=502, detail="Custom endpoint polling redirects are not allowed")
                poll_response.raise_for_status()
                poll_payload = poll_response.json()
                if not isinstance(poll_payload, dict):
                    raise HTTPException(status_code=502, detail="Endpoint polling response must be a JSON object")
                result = validate_endpoint_response(endpoint, poll_payload, polling.get("response_contract"))
                if result.job_id is None:
                    result.job_id = submitted_job_id
                result.request_preview = poll_preview
                normalized_status = result.status.lower()
                if result.output is not None or result.error is not None or normalized_status in terminal_statuses:
                    break
                if normalized_status not in pending_statuses:
                    break
        endpoint.last_test_status = "passed"
        endpoint.last_tested_at = datetime.now(UTC)
        endpoint.last_test_detail = {"http_status": response.status_code, "mapped_status": result.status}
        await db.flush()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        endpoint.last_test_status = "failed"
        endpoint.last_tested_at = datetime.now(UTC)
        endpoint.last_test_detail = {"error_type": type(exc).__name__, "message": str(exc)[:500]}
        await db.flush()
        raise HTTPException(status_code=502, detail="Custom endpoint request failed; inspect last_test_detail") from exc
    finally:
        if owns_client:
            await active_client.aclose()


def infer_comfy_capabilities(workflow: dict[str, Any]) -> dict[str, Any]:
    nodes = workflow.get("nodes") if isinstance(workflow.get("nodes"), list) else None
    prompt_nodes = workflow if nodes is None else {str(item.get("id")): item for item in nodes if isinstance(item, dict)}
    class_names: list[str] = []
    for node in prompt_nodes.values() if isinstance(prompt_nodes, dict) else []:
        if not isinstance(node, dict):
            continue
        name = node.get("class_type") or node.get("type")
        if name:
            class_names.append(str(name))
    lowered = " ".join(class_names).lower()
    return {
        "node_count": len(prompt_nodes) if isinstance(prompt_nodes, dict) else 0,
        "node_types": sorted(set(class_names)),
        "produces_image": any(token in lowered for token in ("saveimage", "previewimage", "vae")),
        "produces_video": any(token in lowered for token in ("video", "animated", "savewebm")),
        "has_text_input": any(token in lowered for token in ("cliptextencode", "text")),
        "has_image_input": any(token in lowered for token in ("loadimage", "imageinput")),
    }


async def create_comfy_workflow(db: AsyncSession, body: ComfyWorkflowCreate) -> ComfyWorkflow:
    if not body.workflow:
        raise HTTPException(status_code=422, detail="ComfyUI workflow JSON cannot be empty")
    if body.endpoint_id and await db.get(CustomEndpoint, body.endpoint_id) is None:
        raise HTTPException(status_code=404, detail="Custom endpoint not found")
    workflow = ComfyWorkflow(
        id=body.id or f"comfy_{uuid4().hex}",
        name=body.name,
        description=body.description,
        endpoint_id=body.endpoint_id,
        workflow=body.workflow,
        input_schema=body.input_schema,
        bindings=body.bindings,
        capabilities=infer_comfy_capabilities(body.workflow),
        status=body.status,
    )
    db.add(workflow)
    await db.flush()
    await db.refresh(workflow)
    return workflow


def bind_comfy_workflow(workflow: ComfyWorkflow, inputs: dict[str, Any]) -> dict[str, Any]:
    """Apply explicit semantic-input bindings without guessing node fields."""
    bound = copy.deepcopy(workflow.workflow)
    nodes = bound.get("nodes") if isinstance(bound.get("nodes"), list) else None
    for semantic_name, binding in (workflow.bindings or {}).items():
        if semantic_name not in inputs:
            continue
        if not isinstance(binding, dict):
            raise HTTPException(status_code=422, detail=f"Invalid binding for {semantic_name}")
        node_id = str(binding.get("node_id") or "")
        input_name = str(binding.get("input") or "")
        if not node_id or not input_name:
            raise HTTPException(status_code=422, detail=f"Binding {semantic_name} requires node_id and input")
        if nodes is None:
            node = bound.get(node_id)
            if not isinstance(node, dict):
                raise HTTPException(status_code=422, detail=f"ComfyUI node not found: {node_id}")
            node_inputs = node.setdefault("inputs", {})
            if not isinstance(node_inputs, dict):
                raise HTTPException(status_code=422, detail=f"ComfyUI node inputs are not an object: {node_id}")
            node_inputs[input_name] = inputs[semantic_name]
            continue
        node = next((item for item in nodes if isinstance(item, dict) and str(item.get("id")) == node_id), None)
        if node is None:
            raise HTTPException(status_code=422, detail=f"ComfyUI node not found: {node_id}")
        node_inputs = node.setdefault("inputs", {})
        if not isinstance(node_inputs, dict):
            raise HTTPException(status_code=422, detail=f"ComfyUI node inputs are not an object: {node_id}")
        node_inputs[input_name] = inputs[semantic_name]
    return bound


def _output_url(output: Any) -> str | None:
    if isinstance(output, str) and output.startswith(("http://", "https://")):
        return output
    if isinstance(output, dict):
        for key in ("url", "download_url", "output_url"):
            value = output.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
    return None


def _media_details(url: str, content_type: str | None) -> tuple[FileType, str]:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    suffix = os.path.splitext(urlparse(url).path)[1].lower()
    if media_type.startswith("image/") or suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return FileType.image, suffix or mimetypes.guess_extension(media_type) or ".png"
    if media_type.startswith("video/") or suffix in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
        return FileType.video, suffix or mimetypes.guess_extension(media_type) or ".mp4"
    if media_type.startswith("audio/") or suffix in {".mp3", ".wav", ".m4a", ".aac", ".ogg"}:
        return FileType.audio, suffix or mimetypes.guess_extension(media_type) or ".mp3"
    raise HTTPException(status_code=422, detail="ComfyUI output is not a supported image, video, or audio file")


async def _persist_remote_output(
    db: AsyncSession,
    *,
    output_url: str,
    project_id: str,
    shot_id: str | None,
    artifact_type: str | None,
    workflow: ComfyWorkflow,
    client: httpx.AsyncClient | None,
) -> tuple[FileItem, ProductionArtifact]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if shot_id:
        shot = await db.get(Shot, shot_id)
        if shot is None:
            raise HTTPException(status_code=404, detail="Shot not found")
        chapter = await db.get(Chapter, shot.chapter_id)
        if chapter is None or chapter.project_id != project_id:
            raise HTTPException(status_code=409, detail="Shot does not belong to the persistence project")
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=120, follow_redirects=False)
    staged = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        await validate_outbound_url(output_url)
        async with active_client.stream("GET", output_url, follow_redirects=False) as response:
            if response.is_redirect:
                raise HTTPException(status_code=502, detail="ComfyUI output redirects are not allowed")
            response.raise_for_status()
            declared_size = int(response.headers.get("content-length") or 0)
            max_bytes = 250 * 1024 * 1024
            if declared_size > max_bytes:
                raise HTTPException(status_code=413, detail="ComfyUI output exceeds the 250 MB ingestion limit")
            byte_count = 0
            async for chunk in response.aiter_bytes():
                byte_count += len(chunk)
                if byte_count > max_bytes:
                    raise HTTPException(status_code=413, detail="ComfyUI output exceeds the 250 MB ingestion limit")
                staged.write(chunk)
            file_type, suffix = _media_details(output_url, response.headers.get("content-type"))
            content_type = response.headers.get("content-type")
    except HTTPException:
        staged.close()
        raise
    except Exception as exc:
        staged.close()
        raise HTTPException(status_code=502, detail="Could not ingest the confirmed ComfyUI output") from exc
    finally:
        if owns_client:
            await active_client.aclose()

    file_id = str(uuid4())
    key = f"files/{file_id}-comfy-output{suffix}"
    staged.seek(0)
    try:
        await storage.upload_file(key=key, data=staged, content_type=content_type)
    finally:
        staged.close()
    parsed_output = urlparse(output_url)
    safe_host = parsed_output.hostname or ""
    if ":" in safe_host and not safe_host.startswith("["):
        safe_host = f"[{safe_host}]"
    safe_netloc = f"{safe_host}:{parsed_output.port}" if parsed_output.port else safe_host
    safe_output_url = urlunsplit((parsed_output.scheme, safe_netloc, "", "", ""))
    file_item = FileItem(
        id=file_id,
        type=file_type,
        name=f"{workflow.name} output",
        thumbnail=file_id,
        tags=["comfyui", workflow.id],
        storage_key=key,
    )
    db.add(file_item)
    await db.flush()
    usage_kind = {
        FileType.image: "shot_frame",
        FileType.video: "generated_video",
        FileType.audio: "generated_audio",
    }[file_type]
    await upsert_file_usage(
        db,
        file_id=file_id,
        project_id=project_id,
        chapter_id=None,
        shot_id=shot_id,
        usage_kind=usage_kind,
        source_ref=f"comfy:{workflow.id}",
    )
    artifact = ProductionArtifact(
        id=str(uuid4()),
        project_id=project_id,
        shot_id=shot_id,
        artifact_type=artifact_type or ("render" if file_type == FileType.video else "keyframe" if file_type == FileType.image else "audio"),
        file_id=file_id,
        input_fingerprint=hashlib.sha256(json.dumps({"workflow": workflow.id, "url": output_url}, sort_keys=True).encode()).hexdigest(),
        currency="current",
        lifecycle="candidate",
        metadata_json={"source": "comfyui", "workflow_id": workflow.id, "remote_output_url": safe_output_url},
    )
    db.add(artifact)
    await db.flush()
    await db.refresh(file_item)
    await db.refresh(artifact)
    return file_item, artifact


async def execute_comfy_workflow(
    db: AsyncSession,
    workflow: ComfyWorkflow,
    *,
    inputs: dict[str, Any],
    confirm_external_call: bool,
    wait_for_result: bool,
    persist_output: bool,
    project_id: str | None,
    shot_id: str | None,
    artifact_type: str | None,
    endpoint_client: httpx.AsyncClient | None = None,
    asset_client: httpx.AsyncClient | None = None,
) -> ComfyWorkflowExecutionRead:
    if persist_output and (not confirm_external_call or not project_id):
        raise HTTPException(status_code=422, detail="Persisting output requires an explicit external-call confirmation and project_id")
    if workflow.status != "ready":
        raise HTTPException(status_code=409, detail="ComfyUI workflow must be ready before execution")
    if not workflow.endpoint_id:
        raise HTTPException(status_code=409, detail="ComfyUI workflow has no execution endpoint")
    endpoint = await db.get(CustomEndpoint, workflow.endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="ComfyUI execution endpoint not found")
    bound = bind_comfy_workflow(workflow, inputs)
    result = await execute_custom_endpoint(
        db,
        endpoint,
        inputs={**inputs, "workflow": bound},
        confirm_external_call=confirm_external_call,
        wait_for_result=wait_for_result,
        client=endpoint_client,
    )
    response = ComfyWorkflowExecutionRead(endpoint_result=result, bound_workflow=bound)
    if not persist_output:
        return response
    if result.output is None:
        response.persistence_status = "output_pending" if result.job_id is not None else "unsupported_output"
        return response
    url = _output_url(result.output)
    if url is None:
        response.persistence_status = "unsupported_output"
        return response
    file_item, artifact = await _persist_remote_output(
        db,
        output_url=url,
        project_id=project_id or "",
        shot_id=shot_id,
        artifact_type=artifact_type,
        workflow=workflow,
        client=asset_client,
    )
    response.file_id = file_item.id
    response.artifact_id = artifact.id
    response.persistence_status = "persisted"
    return response


async def create_market_entry(db: AsyncSession, body: EndpointMarketEntryCreate) -> EndpointMarketEntry:
    _reject_embedded_secrets(body.template)
    entry = EndpointMarketEntry(
        id=body.id or f"market_{uuid4().hex}",
        **body.model_dump(exclude={"id", "source_url"}),
        source_url=str(body.source_url) if body.source_url else None,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


async def install_market_entry(
    db: AsyncSession,
    entry: EndpointMarketEntry,
    request: MarketInstallRequest,
) -> tuple[CustomEndpoint | None, ComfyWorkflow | None]:
    template = copy.deepcopy(entry.template or {})
    endpoint: CustomEndpoint | None = None
    workflow: ComfyWorkflow | None = None
    endpoint_template = template.get("endpoint")
    if isinstance(endpoint_template, dict):
        endpoint_template["id"] = None
        endpoint_template["name"] = request.endpoint_name or endpoint_template.get("name") or entry.name
        endpoint_template["credential_env"] = request.credential_env
        endpoint_template["status"] = "draft"
        endpoint = await create_custom_endpoint(db, CustomEndpointCreate.model_validate(endpoint_template))
        endpoint.source_market_entry_id = entry.id
    workflow_template = template.get("comfy_workflow")
    if isinstance(workflow_template, dict):
        workflow_template["id"] = None
        workflow_template["endpoint_id"] = endpoint.id if endpoint else workflow_template.get("endpoint_id")
        workflow = await create_comfy_workflow(db, ComfyWorkflowCreate.model_validate(workflow_template))
    return endpoint, workflow


def create_api_key_record(name: str, scopes: list[str]) -> tuple[AutomationApiKey, str]:
    token = f"incept_mcp_{secrets.token_urlsafe(32)}"
    record = AutomationApiKey(
        id=f"key_{uuid4().hex}",
        name=name,
        key_prefix=token[:20],
        key_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        scopes=scopes,
        status="active",
    )
    return record, token


async def authenticate_api_key(db: AsyncSession, token: str) -> AutomationApiKey:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    key = (await db.execute(select(AutomationApiKey).where(AutomationApiKey.key_hash == digest))).scalars().first()
    if key is None or key.status != "active":
        raise HTTPException(status_code=401, detail="Invalid automation API key")
    key.last_used_at = datetime.now(UTC)
    await db.flush()
    return key


async def create_memory(
    db: AsyncSession,
    *,
    project_id: str,
    body: MemoryCreate,
    owner_key: str = "local-user",
) -> ProjectMemory:
    if await db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    memory = ProjectMemory(
        id=f"memory_{uuid4().hex}",
        project_id=project_id if body.scope == "project" else None,
        owner_key=owner_key,
        **body.model_dump(),
    )
    db.add(memory)
    await db.flush()
    await db.refresh(memory)
    return memory


async def list_memories(
    db: AsyncSession,
    *,
    project_id: str,
    owner_key: str = "local-user",
    query: str | None = None,
    limit: int = 100,
) -> list[ProjectMemory]:
    if await db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    stmt = select(ProjectMemory).where(
        ProjectMemory.owner_key == owner_key,
        ProjectMemory.status == "active",
        or_(ProjectMemory.project_id == project_id, ProjectMemory.project_id.is_(None)),
    )
    if query and query.strip():
        needle = f"%{query.strip()}%"
        stmt = stmt.where(or_(ProjectMemory.content.ilike(needle), cast(ProjectMemory.tags, String).ilike(needle)))
    stmt = stmt.order_by(ProjectMemory.pinned.desc(), ProjectMemory.updated_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


def memories_as_prompt(memories: list[ProjectMemory]) -> str:
    if not memories:
        return "No saved user or project memories."
    return "\n".join(
        f"- [{item.scope}/{item.kind}; confidence={item.confidence:.2f}] {item.content}"
        for item in memories[:30]
    )


__all__ = [name for name in globals() if not name.startswith("_")]
