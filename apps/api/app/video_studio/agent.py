from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from google.genai import types as genai_types

from app.incept.vertex_generation import _call_multimodal_text_model

from . import store
from .models import (
    AgentConversation,
    AgentMessage,
    CanvasDocument,
    Position,
    VideoEdge,
    VideoNode,
)


ALLOWED_NODE_TYPES = {
    "text",
    "image",
    "video",
    "audio",
    "imageGeneration",
    "videoGeneration",
    "director3d",
}


def _call_model(prompt: str, parts: list[genai_types.Part]) -> str:
    return _call_multimodal_text_model(prompt=prompt, parts=parts, json_response=True)


def _asset_parts(
    email: str,
    project_id: str,
    asset_paths: list[str],
) -> tuple[list[genai_types.Part], list[dict[str, Any]]]:
    root = store.assets_root(email, project_id)
    parts: list[genai_types.Part] = []
    manifest: list[dict[str, Any]] = []
    total_bytes = 0
    for relative_path in dict.fromkeys(asset_paths):
        path = store.safe_asset_path(root, relative_path)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        size = path.stat().st_size
        mime_type = store.asset_mime_type(path)
        entry: dict[str, Any] = {
            "path": relative_path,
            "name": Path(relative_path).name,
            "mime_type": mime_type,
            "size": size,
            "inspection": "metadata-only",
        }
        if size > 10 * 1024 * 1024 or total_bytes + size > 20 * 1024 * 1024:
            entry["reason"] = "attachment size limit"
            manifest.append(entry)
            continue
        payload = path.read_bytes()
        if mime_type.startswith("text/") or mime_type in {"application/json", "application/xml"}:
            text = payload.decode("utf-8", errors="replace")[:50_000]
            parts.append(genai_types.Part(text=f"Project asset {relative_path}:\n{text}"))
        elif mime_type.startswith(("image/", "audio/", "video/")) or mime_type == "application/pdf":
            parts.append(genai_types.Part.from_bytes(data=payload, mime_type=mime_type))
        else:
            entry["reason"] = "unsupported attachment type"
            manifest.append(entry)
            continue
        total_bytes += size
        entry["inspection"] = "attached"
        manifest.append(entry)
    return parts, manifest


def _parse_response(raw: str) -> dict[str, Any]:
    value = raw.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Agent response must be a JSON object")
    return parsed


def _agent_prompt(
    *,
    user_prompt: str,
    canvas: CanvasDocument,
    conversation: AgentConversation,
    language: str,
    custom_system_prompt: str,
    agent_id: str,
    skills: list[dict[str, str]],
    asset_manifest: list[dict[str, Any]],
    allowed_node_types: set[str],
    allow_canvas_edits: bool,
) -> str:
    history = [
        {"role": message.role, "content": message.content[-4_000:]}
        for message in conversation.messages[-12:]
    ]
    canvas_summary = {
        "nodes": [
            {
                "id": node.id,
                "type": node.type,
                "position": node.position.model_dump(),
                "data": node.data,
            }
            for node in canvas.nodes
        ],
        "edges": [edge.model_dump() for edge in canvas.edges],
    }
    team_instructions = ""
    if agent_id == "storyboard":
        team_instructions = """
Operate as a storyboard team: a director first frames the constraints, a writer drafts the shots, and a reviewer checks story coverage, feasibility and continuity. Return the consolidated result. Do not claim ungenerated media exists.
"""
    return f"""You are LinglongLab Video's production workflow agent.
Help the user plan and edit a node-based video workflow. Respond in {language}.
{custom_system_prompt}
{team_instructions}

Enabled production skills:
{json.dumps(skills, ensure_ascii=False)}

User-selected project assets. Items marked "attached" are included in this model request and may be inspected. Items marked "metadata-only" were not inspected; never claim their contents were seen:
{json.dumps(asset_manifest, ensure_ascii=False)}

Canvas editing is {"enabled" if allow_canvas_edits else "disabled"}. Enabled node types:
{json.dumps(sorted(allowed_node_types), ensure_ascii=False)}

Return one JSON object only with this shape:
{{
  "message": "concise response to the user",
  "operations": [
    {{"action":"add_node","type":"text|image|video|audio|imageGeneration|videoGeneration|director3d","label":"...","data":{{}},"position":{{"x":0,"y":0}}}},
    {{"action":"update_node","id":"existing id","data":{{}}}},
    {{"action":"remove_node","id":"existing id"}},
    {{"action":"connect","source":"existing id","target":"existing id"}},
    {{"action":"disconnect","id":"existing edge id"}}
  ]
}}
Use at most 30 operations. Do not claim media was generated; generation nodes only prepare prompts.
If no canvas edit is needed, return an empty operations array.

Conversation:
{json.dumps(history, ensure_ascii=False)}

Current canvas:
{json.dumps(canvas_summary, ensure_ascii=False)}

User request:
{user_prompt}
"""


def _apply_operations(
    canvas: CanvasDocument,
    operations: Any,
    *,
    allowed_node_types: set[str] | None = None,
    allow_canvas_edits: bool = True,
) -> CanvasDocument:
    if not allow_canvas_edits:
        return canvas
    enabled_types = allowed_node_types if allowed_node_types is not None else ALLOWED_NODE_TYPES
    nodes = {node.id: node for node in canvas.nodes}
    edges = {edge.id: edge for edge in canvas.edges}
    for operation in operations if isinstance(operations, list) else []:
        if not isinstance(operation, dict):
            continue
        action = operation.get("action")
        if action == "add_node" and len(nodes) < 2_000:
            node_type = str(operation.get("type") or "text")
            if node_type not in enabled_types:
                continue
            node_id = f"{node_type}-{uuid.uuid4()}"
            position = operation.get("position") if isinstance(operation.get("position"), dict) else {}
            data = operation.get("data") if isinstance(operation.get("data"), dict) else {}
            data = {
                **data,
                "kind": node_type,
                "label": str(operation.get("label") or data.get("label") or node_type)[:120],
                "status": "idle",
            }
            nodes[node_id] = VideoNode(
                id=node_id,
                type=node_type,
                position=Position(
                    x=float(position.get("x", 120 + (len(nodes) % 4) * 260)),
                    y=float(position.get("y", 100 + (len(nodes) // 4) * 180)),
                ),
                data=data,
            )
        elif action == "update_node" and str(operation.get("id")) in nodes:
            node = nodes[str(operation["id"])]
            patch = operation.get("data") if isinstance(operation.get("data"), dict) else {}
            node.data = {**node.data, **patch}
        elif action == "remove_node" and str(operation.get("id")) in nodes:
            node_id = str(operation["id"])
            nodes.pop(node_id)
            edges = {
                edge_id: edge
                for edge_id, edge in edges.items()
                if edge.source != node_id and edge.target != node_id
            }
        elif action == "connect":
            source, target = str(operation.get("source")), str(operation.get("target"))
            if source in nodes and target in nodes and source != target and len(edges) < 4_000:
                edge_id = f"edge-{uuid.uuid4()}"
                edges[edge_id] = VideoEdge(id=edge_id, source=source, target=target)
        elif action == "disconnect" and str(operation.get("id")) in edges:
            edges.pop(str(operation["id"]))
    return canvas.model_copy(update={"nodes": list(nodes.values()), "edges": list(edges.values())})


def run_agent(
    *,
    email: str,
    project_id: str,
    prompt: str,
    conversation_id: str | None,
    agent_id: str | None = None,
    asset_paths: list[str] | None = None,
) -> tuple[AgentConversation, CanvasDocument, str]:
    project = store.get_project(email, project_id)
    settings = store.get_settings(email)
    catalog = store.get_catalog(email)
    enabled_extensions = {item.id for item in catalog.extensions if item.enabled}
    selected_agent = agent_id or settings.default_agent
    if f"agent-{selected_agent}" not in enabled_extensions:
        raise ValueError(f"Agent is disabled: {selected_agent}")
    selected_assets = asset_paths or []
    if selected_assets and "tool-workspace" not in enabled_extensions:
        raise ValueError("Workspace asset access is disabled")
    parts, asset_manifest = _asset_parts(email, project_id, selected_assets)
    enabled_node_types = {
        node_type
        for node_type in ALLOWED_NODE_TYPES
        if f"node-{node_type.lower()}" in enabled_extensions
    }
    allow_canvas_edits = "tool-canvas" in enabled_extensions
    if conversation_id:
        conversation = store.get_conversation(email, project_id, conversation_id)
    else:
        conversation = AgentConversation(id=uuid.uuid4().hex, name=prompt.strip()[:60])
    conversation.messages.append(
        AgentMessage(id=uuid.uuid4().hex, role="user", content=prompt.strip())
    )
    raw = _call_model(
        _agent_prompt(
            user_prompt=prompt,
            canvas=project.canvas,
            conversation=conversation,
            language=settings.language,
            custom_system_prompt=settings.agent_system_prompt,
            agent_id=selected_agent,
            skills=[
                {"name": skill.name, "description": skill.description, "instructions": skill.instructions}
                for skill in catalog.skills
                if skill.enabled
            ],
            asset_manifest=asset_manifest,
            allowed_node_types=enabled_node_types,
            allow_canvas_edits=allow_canvas_edits,
        ),
        parts,
    )
    result = _parse_response(raw)
    message = str(result.get("message") or "Done").strip()[:20_000]
    canvas = _apply_operations(
        project.canvas,
        result.get("operations"),
        allowed_node_types=enabled_node_types,
        allow_canvas_edits=allow_canvas_edits,
    )
    canvas = store.save_canvas(email, project_id, canvas)
    conversation.messages.append(
        AgentMessage(id=uuid.uuid4().hex, role="assistant", content=message)
    )
    store.save_conversation(email, project_id, conversation)
    return conversation, canvas, message
