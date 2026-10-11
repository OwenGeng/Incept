from __future__ import annotations

import json

from app.routers.video_legacy import _sync_vue_canvas, _vue_canvas_document, _vue_canvas_snapshot
from app.video_studio import store
from app.video_studio.models import CanvasCreate, ProjectCreate


def test_vue_canvas_document_is_pure_and_ignores_non_canvas_payloads():
    payload = {"linglonglabVideoCanvas": True, "nodes": [
        {"id": "group", "type": "group", "position": {"x": 12, "y": 20},
         "data": {"label": "Approved"}, "style": {"width": "600px"}}
    ], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}

    canvas = _vue_canvas_document(json.dumps(payload).encode())

    assert canvas is not None
    assert _vue_canvas_snapshot(canvas)["nodes"] == payload["nodes"]
    assert _vue_canvas_document(b"not json") is None
    assert _vue_canvas_document(b"[]") is None
    assert _vue_canvas_document(b'{"nodes": []}') is None


def test_agent_canvas_roundtrip_preserves_groups_layout_and_custom_edges(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    email = "canvas-safety@linglonglab.internal"
    project = store.create_project(email, ProjectCreate(name="Canvas safety"))
    nodes = [
        {"id": "group", "type": "group", "position": {"x": 12, "y": 20},
         "data": {"label": "Approved shots"}, "style": {"width": "600px", "height": "300px"},
         "dimensions": {"width": 600, "height": 300}, "draggable": True},
        {"id": "image", "type": "remote-imageNode", "position": {"x": 40, "y": 60},
         "data": {"url": "library/customer.png"}, "parentNode": "group", "extent": "parent",
         "expandParent": True, "zIndex": 4, "selected": False, "width": 200, "height": 120},
        {"id": "future", "type": "future-custom-node", "position": {"x": 90, "y": 60},
         "data": {"custom": "retained"}, "parentNode": "group", "class": "customer-node"},
    ]
    edges = [{"id": "edge", "source": "image", "target": "future", "sourceHandle": "out",
              "targetHandle": "in", "type": "smoothstep", "animated": True,
              "style": {"stroke": "#f00"}, "label": "Source", "data": {"approved": True}},
             {"id": "plain-edge", "source": "future", "target": "image", "animated": False}]
    payload = {"linglonglabVideoCanvas": True, "nodes": nodes, "edges": edges,
               "viewport": {"x": 15, "y": 10, "zoom": 0.5}}

    _sync_vue_canvas(email, project.id, json.dumps(payload).encode())
    saved = store.get_project(email, project.id).canvas
    snapshot = _vue_canvas_snapshot(saved)

    assert snapshot["nodes"] == nodes
    assert snapshot["edges"] == edges
    assert snapshot["viewport"] == payload["viewport"]
    changed = saved.model_copy(deep=True)
    changed.nodes[1].data["caption"] = "Agent edit"
    assert _vue_canvas_snapshot(changed)["nodes"][1]["parentNode"] == "group"


def test_sync_named_canvas_does_not_overwrite_active_canvas(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    email = "canvas-safety@linglonglab.internal"
    project = store.create_project(email, ProjectCreate(name="Two canvases"))
    original_id = project.active_canvas_id
    second = store.create_canvas(email, project.id, CanvasCreate(name="Second"))
    payload = {"linglonglabVideoCanvas": True, "nodes": [
        {"id": "requested", "type": "remote-textNode", "position": {"x": 0, "y": 0}, "data": {}}
    ], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}

    _sync_vue_canvas(email, project.id, json.dumps(payload).encode(), canvas_id=original_id)

    assert store.get_project_canvas(email, project.id, original_id).nodes[0].id == "requested"
    assert store.get_project_canvas(email, project.id, second.active_canvas_id).nodes == []
    assert store.get_project(email, project.id).active_canvas_id == second.active_canvas_id
