from __future__ import annotations

import asyncio
import httpx
import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse
from starlette.requests import Request
from starlette.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai_video.api.v1.routes.automation import _call_tool
from app.ai_video.core.db import Base
from app.ai_video.config import settings
from app.ai_video.main import require_linglong_proxy_key
from app.ai_video.models.integration_hub import EndpointMarketEntry
from app.ai_video.models.studio import Project, ProjectStyle, ProjectVisualStyle
from app.ai_video.schemas.studio.integration_hub import (
    ComfyWorkflowCreate,
    CustomEndpointCreate,
    EndpointMarketEntryCreate,
    MarketInstallRequest,
    MemoryCreate,
)
from app.ai_video.services.studio.integration_hub import (
    authenticate_api_key,
    create_api_key_record,
    create_comfy_workflow,
    create_custom_endpoint,
    create_market_entry,
    create_memory,
    execute_comfy_workflow,
    execute_custom_endpoint,
    install_market_entry,
    list_memories,
    validate_outbound_url,
    validate_endpoint_response,
)


@pytest.fixture(autouse=True)
def _resolve_example_test_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    """MockTransport test hosts are public stand-ins and have no real DNS."""

    from app.ai_video.services.studio import integration_hub as module

    original = module.validate_outbound_url

    async def validate(url: str) -> None:
        if (urlparse(url).hostname or "").endswith(".example.test"):
            return
        await original(url)

    monkeypatch.setattr(module, "validate_outbound_url", validate)


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return maker(), engine


async def _project(db: AsyncSession) -> None:
    db.add(Project(id="project-1", name="Ad", description="", style=ProjectStyle.advertising_general, visual_style=ProjectVisualStyle.live_action))
    await db.flush()


def _endpoint_body() -> CustomEndpointCreate:
    return CustomEndpointCreate(
        name="User supplied video endpoint",
        category="video",
        base_url="https://endpoint.example.test",
        status="testing",
        request_contract={
            "method": "POST",
            "path": "/user-confirmed-submit",
            "body_template": {"prompt": "${input.prompt}", "seconds": "${input.duration}"},
        },
        response_contract={"output_path": "data.url", "job_id_path": "data.job_id", "error_path": "error.message"},
        capabilities={"ratios": ["16:9", "9:16"]},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8188/prompt",
        "http://10.0.0.8/internal",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/admin",
        "http://metadata.google.internal/computeMetadata/v1",
    ],
)
async def test_outbound_url_validation_rejects_private_and_metadata_targets(url: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await validate_outbound_url(url)

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_outbound_url_validation_rejects_dns_that_resolves_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()
    resolver = AsyncMock(return_value=[(2, 1, 6, "", ("10.20.30.40", 443))])
    monkeypatch.setattr(loop, "getaddrinfo", resolver)

    with pytest.raises(HTTPException) as exc_info:
        await validate_outbound_url("https://attacker-controlled.example/private")

    assert exc_info.value.status_code == 422
    resolver.assert_awaited_once()


@pytest.mark.asyncio
async def test_custom_endpoint_rejects_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _session()
    async with db:
        endpoint = await create_custom_endpoint(db, _endpoint_body())

        async def _allow_public(_url: str) -> None:
            return None

        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8000/private"})

        monkeypatch.setattr("app.ai_video.services.studio.integration_hub.validate_outbound_url", _allow_public)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(HTTPException) as exc_info:
            await execute_custom_endpoint(
                db,
                endpoint,
                inputs={"prompt": "Show the product", "duration": 5},
                confirm_external_call=True,
                client=client,
            )
        await client.aclose()

        assert exc_info.value.status_code == 502
        assert "redirect" in str(exc_info.value.detail).lower()
    await engine.dispose()


@pytest.mark.asyncio
async def test_custom_endpoint_preview_offline_validation_and_explicit_execution() -> None:
    db, engine = await _session()
    async with db:
        endpoint = await create_custom_endpoint(db, _endpoint_body())
        mapped = validate_endpoint_response(endpoint, {"data": {"url": "https://cdn.example.test/result.mp4"}})
        assert mapped.status == "succeeded"
        assert mapped.output.endswith("result.mp4")

        preview = await execute_custom_endpoint(
            db,
            endpoint,
            inputs={"prompt": "Show the product", "duration": 5},
            confirm_external_call=False,
        )
        assert preview.status == "confirmation_required"
        assert preview.request_preview["body"] == {"prompt": "Show the product", "seconds": 5}

        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/user-confirmed-submit"
            return httpx.Response(200, json={"data": {"job_id": "remote-1"}})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        result = await execute_custom_endpoint(
            db,
            endpoint,
            inputs={"prompt": "Show the product", "duration": 5},
            confirm_external_call=True,
            client=client,
        )
        await client.aclose()
        assert result.status == "submitted"
        assert result.job_id == "remote-1"
        assert endpoint.last_test_status == "passed"
    await engine.dispose()


@pytest.mark.asyncio
async def test_custom_endpoint_uses_only_declared_polling_contract() -> None:
    db, engine = await _session()
    async with db:
        body = _endpoint_body()
        body.polling_contract = {
            "method": "GET",
            "path": "/jobs/${input.job_id}",
            "body_template": {},
            "interval_seconds": 0,
            "max_attempts": 3,
            "response_contract": {"output_path": "result.url", "status_path": "status", "error_path": "error"},
        }
        endpoint = await create_custom_endpoint(db, body)
        calls: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if request.url.path == "/user-confirmed-submit":
                return httpx.Response(200, json={"data": {"job_id": "job-42"}})
            if len(calls) == 2:
                return httpx.Response(200, json={"status": "running"})
            return httpx.Response(200, json={"status": "completed", "result": {"url": "https://files.example.test/result.mp4"}})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        result = await execute_custom_endpoint(
            db,
            endpoint,
            inputs={"prompt": "Show the product", "duration": 5},
            confirm_external_call=True,
            wait_for_result=True,
            client=client,
        )
        await client.aclose()
        assert calls == ["/user-confirmed-submit", "/jobs/job-42", "/jobs/job-42"]
        assert result.status == "completed"
        assert result.job_id == "job-42"
        assert result.output.endswith("result.mp4")
    await engine.dispose()


@pytest.mark.asyncio
async def test_comfy_import_infers_capabilities_and_market_install_is_a_local_copy() -> None:
    db, engine = await _session()
    async with db:
        workflow_body = ComfyWorkflowCreate(
            name="Product keyframe",
            workflow={
                "1": {"class_type": "CLIPTextEncode", "inputs": {}},
                "2": {"class_type": "SaveImage", "inputs": {}},
            },
            bindings={"prompt": {"node_id": "1", "input": "text"}},
        )
        workflow = await create_comfy_workflow(db, workflow_body)
        assert workflow.capabilities["has_text_input"] is True
        assert workflow.capabilities["produces_image"] is True

        entry = await create_market_entry(
            db,
            EndpointMarketEntryCreate(
                name="Reviewed local template",
                description="No credentials included",
                publisher="Incept user",
                trust_level="reviewed",
                status="published",
                categories=["workflow"],
                credential_destination="Environment variable on the Incept API host",
                template={"endpoint": _endpoint_body().model_dump(mode="json"), "comfy_workflow": workflow_body.model_dump(mode="json")},
            ),
        )
        installed_endpoint, installed_workflow = await install_market_entry(
            db,
            entry,
            MarketInstallRequest(endpoint_name="My installed endpoint"),
        )
        assert installed_endpoint is not None and installed_endpoint.id != entry.id
        assert installed_endpoint.status == "draft"
        assert installed_endpoint.source_market_entry_id == entry.id
        assert installed_workflow is not None and installed_workflow.endpoint_id == installed_endpoint.id
    await engine.dispose()


@pytest.mark.asyncio
async def test_comfy_execution_binds_inputs_and_persists_candidate_artifact() -> None:
    db, engine = await _session()
    async with db:
        await _project(db)
        endpoint = await create_custom_endpoint(
            db,
            CustomEndpointCreate(
                **{
                    **_endpoint_body().model_dump(),
                    "request_contract": {
                        "method": "POST",
                        "path": "/user-confirmed-submit",
                        "body_template": {"prompt": "${input.workflow}"},
                    },
                }
            ),
        )
        workflow = await create_comfy_workflow(
            db,
            ComfyWorkflowCreate(
                name="Executable product keyframe",
                endpoint_id=endpoint.id,
                status="ready",
                workflow={
                    "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "old"}},
                    "2": {"class_type": "SaveImage", "inputs": {}},
                },
                bindings={"prompt": {"node_id": "1", "input": "text"}},
            ),
        )

        async def endpoint_handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/user-confirmed-submit"
            assert b"Show the product" in request.content
            return httpx.Response(200, json={"data": {"url": "https://files.example.test/result.png"}})

        async def asset_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "image/png"}, content=b"image-bytes")

        endpoint_client = httpx.AsyncClient(transport=httpx.MockTransport(endpoint_handler))
        asset_client = httpx.AsyncClient(transport=httpx.MockTransport(asset_handler))
        with patch("app.ai_video.services.studio.integration_hub.storage.upload_file", new=AsyncMock()) as upload:
            result = await execute_comfy_workflow(
                db,
                workflow,
                inputs={"prompt": "Show the product"},
            confirm_external_call=True,
            wait_for_result=True,
            persist_output=True,
                project_id="project-1",
                shot_id=None,
                artifact_type="keyframe",
                endpoint_client=endpoint_client,
                asset_client=asset_client,
            )
        await endpoint_client.aclose()
        await asset_client.aclose()
        upload.assert_awaited_once()
        assert result.bound_workflow["1"]["inputs"]["text"] == "Show the product"
        assert result.persistence_status == "persisted"
        assert result.file_id is not None
        assert result.artifact_id is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_api_key_is_hashed_and_mcp_tools_share_production_and_memory_contracts() -> None:
    db, engine = await _session()
    async with db:
        await _project(db)
        key, token = create_api_key_record("External creative agent", ["read:production", "read:memory", "write:memory"])
        db.add(key)
        await db.flush()
        assert token not in key.key_hash
        authenticated = await authenticate_api_key(db, token)
        assert authenticated.id == key.id

        memory = await create_memory(
            db,
            project_id="project-1",
            body=MemoryCreate(scope="project", kind="decision", content="Use product proof before the CTA", tags=["script"]),
        )
        memories = await list_memories(db, project_id="project-1", query="product proof")
        assert [item.id for item in memories] == [memory.id]

        plan_result = await _call_tool(db, key, "production.get_plan", {"project_id": "project-1"})
        assert plan_result["structuredContent"]["next_action"]["type"] == "approve_research"
        memory_result = await _call_tool(db, key, "memory.search", {"project_id": "project-1", "query": "CTA"})
        assert memory_result["structuredContent"]["memories"][0]["kind"] == "decision"
    await engine.dispose()


@pytest.mark.asyncio
async def test_mcp_path_bypasses_only_proxy_key_and_keeps_route_auth_authoritative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "internal_api_key", "proxy-secret")
    called: list[str] = []

    async def next_handler(request: Request) -> Response:
        called.append(request.url.path)
        return Response(status_code=204)

    def request_for(path: str) -> Request:
        return Request({
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "server": ("example.test", 443),
            "client": ("127.0.0.1", 1234),
            "root_path": "",
        })

    mcp_response = await require_linglong_proxy_key(request_for("/ai-video/api/v1/automation/mcp"), next_handler)
    blocked_response = await require_linglong_proxy_key(request_for("/ai-video/api/v1/studio/projects"), next_handler)
    assert mcp_response.status_code == 204
    assert blocked_response.status_code == 401
    assert called == ["/ai-video/api/v1/automation/mcp"]
