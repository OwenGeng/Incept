from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.incept.db as db
from app.incept.auth import get_current_user
from app.incept.models import Role, User
from app.routers.incept import router
from app.incept.workflow_store import cache_node_result, get_cached_node_result, workflow_node_cache_key
from app.incept.workflows import WorkflowEdge, WorkflowGraph, WorkflowNode, WorkflowTemplate, template_graph, validate_graph


def _test_user() -> User:
    return User(
        id="workflow-test",
        name="Workflow Test",
        email="workflow@test.local",
        role=Role.user,
        team="test",
    )


def test_workflow_lifecycle_endpoints_keep_runs_durable(tmp_path, monkeypatch) -> None:
    """The canvas contract works without starting the provider worker."""
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "workflow-api.db")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _test_user
    client = TestClient(app, raise_server_exceptions=True)

    created = client.post("/studio-workflows", json={"workspace_id": "wsp_test", "template": "image"})
    assert created.status_code == 200
    workflow = created.json()
    graph = workflow["graph"]
    graph["nodes"][0]["params"] = {"prompt": "a sunlit flower bouquet"}

    saved = client.put(
        f"/studio-workflows/{workflow['workflow_id']}?workspace_id=wsp_test",
        json={"graph": graph, "expected_revision": workflow["revision"]},
    )
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2
    assert client.post(f"/studio-workflows/{workflow['workflow_id']}/validate?workspace_id=wsp_test").json()["valid"]

    run = client.post(
        f"/studio-workflows/{workflow['workflow_id']}/runs?workspace_id=wsp_test",
        json={"output_node_ids": ["image"]},
    )
    assert run.status_code == 200
    run_id = run.json()["run_id"]
    assert len(client.get(f"/studio-workflow-runs/{run_id}/nodes?workspace_id=wsp_test").json()) == 3
    assert client.post(f"/studio-workflow-runs/{run_id}/cancel?workspace_id=wsp_test").status_code == 200
    retried = client.post(f"/studio-workflow-runs/{run_id}/retry?workspace_id=wsp_test")
    assert retried.status_code == 200
    assert retried.json()["run_id"] != run_id

    catalog = client.get("/studio-workflow-node-definitions")
    assert catalog.status_code == 200
    assert any(node["type"] == "incept.video.generate.v1" for node in catalog.json())

    lineage = client.get(f"/studio-workflows/{workflow['workflow_id']}/lineage?workspace_id=wsp_test")
    assert lineage.status_code == 200
    assert lineage.json()["runs"]
    assert lineage.json()["run_nodes"]


def test_workflow_graph_rejects_mismatched_ports_and_persists_safe_node_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "workflow-cache.db")
    db.init_db()
    graph = WorkflowGraph(
        nodes=[
            WorkflowNode(id="keyframe", type="incept.asset.keyframe.v1", label="Keyframe"),
            WorkflowNode(id="image", type="incept.image.generate.v1", label="Image"),
        ],
        edges=[WorkflowEdge(id="wrong-type", source_node_id="keyframe", source_port="keyframe", target_node_id="image", target_port="prompt")],
    )
    result = validate_graph(graph)
    assert not result.valid
    assert any("expects image_prompt" in issue.message for issue in result.issues)

    cache_key = workflow_node_cache_key("wsp_test", "incept.prompt.v1", {"params": {"prompt": "flowers"}})
    cache_node_result("wsp_test", "incept.prompt.v1", cache_key, {"params": {"prompt": "flowers"}})
    assert get_cached_node_result(cache_key) == {"params": {"prompt": "flowers"}}

    for template in WorkflowTemplate:
        assert validate_graph(template_graph(template)).valid
