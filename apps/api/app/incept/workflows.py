"""Server-owned contracts for the Studio Workflows canvas.

The graph is deliberately product-typed: browser coordinates are persisted, but
only this module decides which ports can connect and which template operations
may be queued. Provider credentials and model selection never enter a graph.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class WorkflowTemplate(str, Enum):
    script = "script"
    image = "image"
    video = "video"
    commercial = "commercial"


class WorkflowStatus(str, Enum):
    draft = "draft"
    archived = "archived"


class WorkflowRunStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class WorkflowNodeStatus(str, Enum):
    draft = "draft"
    valid = "valid"
    blocked = "blocked"
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    approved = "approved"
    stale = "stale"
    failed = "failed"
    cancelled = "cancelled"


class WorkflowPortDefinition(BaseModel):
    id: str
    value_type: str
    required: bool = False
    multiple: bool = False


class WorkflowNodeDefinition(BaseModel):
    type: str
    display_name: str
    category: str
    description: str
    inputs: list[WorkflowPortDefinition] = Field(default_factory=list)
    outputs: list[WorkflowPortDefinition] = Field(default_factory=list)
    operation: Literal["input", "agent", "image", "video", "approval", "delivery"]
    requires_approval: bool = False
    costed: bool = False


NODE_DEFINITIONS: tuple[WorkflowNodeDefinition, ...] = (
    WorkflowNodeDefinition(
        type="incept.asset.reference.v1", display_name="Creative reference", category="Inputs",
        description="Reference video, image, brand assets, and a creative brief that downstream agents must follow.",
        outputs=[WorkflowPortDefinition(id="reference", value_type="creative_reference")], operation="input",
    ),
    WorkflowNodeDefinition(
        type="incept.prompt.v1", display_name="Prompt & references", category="Inputs",
        description="Image generation brief, optional visual references, and output framing.",
        outputs=[WorkflowPortDefinition(id="prompt", value_type="image_prompt")], operation="input",
    ),
    WorkflowNodeDefinition(
        type="incept.asset.keyframe.v1", display_name="Approved keyframe", category="Inputs",
        description="A selected image asset used as the visual starting state for a video shot.",
        outputs=[WorkflowPortDefinition(id="keyframe", value_type="approved_keyframe")], operation="input", requires_approval=True,
    ),
    WorkflowNodeDefinition(
        type="incept.agent.creative-strategist.v1", display_name="Creative Strategist", category="Agents",
        description="Analyses source material and writes the Creative Contract for an original production.",
        inputs=[WorkflowPortDefinition(id="reference", value_type="creative_reference", required=True)],
        outputs=[WorkflowPortDefinition(id="direction", value_type="creative_contract")], operation="agent",
    ),
    WorkflowNodeDefinition(
        type="incept.agent.screenwriter.v1", display_name="Senior Screenwriter", category="Agents",
        description="Turns the approved direction into a timed, editable screenplay.",
        inputs=[WorkflowPortDefinition(id="direction", value_type="creative_contract", required=True)],
        outputs=[WorkflowPortDefinition(id="script", value_type="script")], operation="agent",
    ),
    WorkflowNodeDefinition(
        type="incept.agent.production-designer.v1", display_name="Production Designer", category="Agents",
        description="Builds reusable character, environment, UI, and visual-state requirements from the script.",
        inputs=[WorkflowPortDefinition(id="direction", value_type="creative_contract", required=True)],
        outputs=[WorkflowPortDefinition(id="design", value_type="design_contract")], operation="agent",
    ),
    WorkflowNodeDefinition(
        type="incept.agent.storyboard-director.v1", display_name="Storyboard Director", category="Agents",
        description="Creates user-readable shots and continuity rules from the script and design contract.",
        inputs=[
            WorkflowPortDefinition(id="script", value_type="script", required=True),
            WorkflowPortDefinition(id="design", value_type="design_contract", required=True),
        ],
        outputs=[WorkflowPortDefinition(id="storyboard", value_type="storyboard")], operation="agent",
    ),
    WorkflowNodeDefinition(
        type="incept.image.generate.v1", display_name="Generate image", category="Image",
        description="Creates image candidates using the configured Studio image adapter.",
        inputs=[WorkflowPortDefinition(id="prompt", value_type="image_prompt", required=True)],
        outputs=[WorkflowPortDefinition(id="candidates", value_type="image_candidates")], operation="image", costed=True,
    ),
    WorkflowNodeDefinition(
        type="incept.video.generate.v1", display_name="Generate video shot", category="Video",
        description="Creates video takes from an approved keyframe and motion prompt after plan and budget checks.",
        inputs=[WorkflowPortDefinition(id="keyframe", value_type="approved_keyframe", required=True)],
        outputs=[WorkflowPortDefinition(id="takes", value_type="video_candidates")], operation="video", costed=True,
    ),
    WorkflowNodeDefinition(
        type="incept.approval.image.v1", display_name="Select image candidate", category="Delivery",
        description="Requires an explicit user selection before an image can be consumed downstream.",
        inputs=[WorkflowPortDefinition(id="candidates", value_type="image_candidates", required=True)],
        outputs=[WorkflowPortDefinition(id="image", value_type="approved_image")], operation="approval", requires_approval=True,
    ),
    WorkflowNodeDefinition(
        type="incept.approval.video.v1", display_name="Select video take", category="Delivery",
        description="Requires an explicit user selection before a video take can be consumed downstream.",
        inputs=[WorkflowPortDefinition(id="takes", value_type="video_candidates", required=True)],
        outputs=[WorkflowPortDefinition(id="video", value_type="approved_video")], operation="approval", requires_approval=True,
    ),
    WorkflowNodeDefinition(
        type="incept.approval.script.v1", display_name="Approve script", category="Delivery",
        description="Makes the reviewed script available for production design and storyboarding.",
        inputs=[WorkflowPortDefinition(id="script", value_type="script", required=True)],
        outputs=[WorkflowPortDefinition(id="approved_script", value_type="approved_script")], operation="approval", requires_approval=True,
    ),
    WorkflowNodeDefinition(
        type="incept.delivery.v1", display_name="Commercial delivery", category="Delivery",
        description="Collects the approved campaign production for shot, asset, and CTA review.",
        inputs=[WorkflowPortDefinition(id="storyboard", value_type="storyboard", required=True)],
        outputs=[WorkflowPortDefinition(id="delivery", value_type="commercial_delivery")], operation="delivery",
    ),
    WorkflowNodeDefinition(
        type="incept.group.v1", display_name="Workflow group", category="Canvas",
        description="A visual, non-executable label used to keep related nodes together on the canvas.",
        operation="input",
    ),
)


def list_node_definitions() -> list[WorkflowNodeDefinition]:
    return list(NODE_DEFINITIONS)


class WorkflowNode(BaseModel):
    id: str
    type: str
    label: str
    params: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    status: WorkflowNodeStatus = WorkflowNodeStatus.draft


class WorkflowEdge(BaseModel):
    id: str
    source_node_id: str
    source_port: str = "output"
    target_node_id: str
    target_port: str = "input"


class WorkflowGraph(BaseModel):
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    viewport: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "zoom": 1.0})


class Workflow(BaseModel):
    workflow_id: str
    workspace_id: str
    title: str
    template: WorkflowTemplate
    status: WorkflowStatus = WorkflowStatus.draft
    revision: int = 1
    graph: WorkflowGraph
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class WorkflowCreateRequest(BaseModel):
    workspace_id: str
    template: WorkflowTemplate
    title: str | None = None


class WorkflowUpdateRequest(BaseModel):
    title: str | None = None
    graph: WorkflowGraph
    expected_revision: int


class WorkflowValidationIssue(BaseModel):
    node_id: str | None = None
    port_id: str | None = None
    message: str


class WorkflowValidationResult(BaseModel):
    valid: bool
    issues: list[WorkflowValidationIssue] = Field(default_factory=list)


class WorkflowRevision(BaseModel):
    workflow_id: str
    revision: int
    created_by: str
    created_at: datetime
    workflow: Workflow


class WorkflowRun(BaseModel):
    run_id: str
    workflow_id: str
    workspace_id: str
    revision: int
    status: WorkflowRunStatus = WorkflowRunStatus.queued
    requested_output_node_ids: list[str] = Field(default_factory=list)
    priority: int = 0
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class WorkflowRunRequest(BaseModel):
    output_node_ids: list[str] = Field(default_factory=list)
    priority: int = Field(default=0, ge=-10, le=10)


class WorkflowRunNode(BaseModel):
    run_id: str
    node_id: str
    node_type: str
    status: WorkflowNodeStatus = WorkflowNodeStatus.queued
    progress: int = 0
    message: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class WorkflowOutput(BaseModel):
    """An immutable, explicitly approved value emitted by a workflow run."""
    output_id: str
    workflow_id: str
    workspace_id: str
    run_id: str
    node_id: str
    output_type: Literal["image", "video", "script", "commercial"]
    value_id: str
    created_by: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WorkflowLineage(BaseModel):
    workflow_id: str
    workspace_id: str
    graph_revision: int
    graph: WorkflowGraph
    outputs: list[WorkflowOutput] = Field(default_factory=list)
    runs: list[WorkflowRun] = Field(default_factory=list)
    run_nodes: list[WorkflowRunNode] = Field(default_factory=list)


class WorkflowEvent(BaseModel):
    event_id: str
    run_id: str
    node_id: str | None = None
    type: str
    message: str
    progress: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


def _node(node_id: str, type_: str, label: str, x: float, y: float, *, status: WorkflowNodeStatus = WorkflowNodeStatus.draft) -> WorkflowNode:
    return WorkflowNode(id=node_id, type=type_, label=label, position={"x": x, "y": y}, status=status)


def template_graph(template: WorkflowTemplate) -> WorkflowGraph:
    """Official starter graphs. IDs are stable within a new graph only."""
    if template is WorkflowTemplate.script:
        nodes = [
            _node("reference", "incept.asset.reference.v1", "Creative reference", 32, 170),
            _node("strategy", "incept.agent.creative-strategist.v1", "Creative Strategist", 310, 170),
            _node("screenwriter", "incept.agent.screenwriter.v1", "Senior Screenwriter", 610, 170),
            _node("script", "incept.approval.script.v1", "Approved script", 910, 170),
        ]
    elif template is WorkflowTemplate.image:
        nodes = [
            _node("prompt", "incept.prompt.v1", "Prompt & references", 32, 170),
            _node("image", "incept.image.generate.v1", "Generate image", 350, 170),
            _node("selection", "incept.approval.image.v1", "Select candidate", 670, 170),
        ]
    elif template is WorkflowTemplate.video:
        nodes = [
            _node("keyframe", "incept.asset.keyframe.v1", "Approved keyframe", 32, 170),
            _node("shot", "incept.video.generate.v1", "Generate video shot", 350, 170),
            _node("take", "incept.approval.video.v1", "Select take", 670, 170),
        ]
    else:
        nodes = [
            _node("reference", "incept.asset.reference.v1", "Reference & brand assets", 32, 260),
            _node("strategy", "incept.agent.creative-strategist.v1", "Creative Strategist", 300, 120),
            _node("script", "incept.agent.screenwriter.v1", "Senior Screenwriter", 580, 120),
            _node("design", "incept.agent.production-designer.v1", "Production Designer", 580, 370),
            _node("director", "incept.agent.storyboard-director.v1", "Storyboard Director", 860, 245),
            _node("delivery", "incept.delivery.v1", "Commercial delivery", 1160, 245),
        ]
    if template is WorkflowTemplate.script:
        edges = [
            WorkflowEdge(id="reference-strategy", source_node_id="reference", source_port="reference", target_node_id="strategy", target_port="reference"),
            WorkflowEdge(id="strategy-screenwriter", source_node_id="strategy", source_port="direction", target_node_id="screenwriter", target_port="direction"),
            WorkflowEdge(id="screenwriter-script", source_node_id="screenwriter", source_port="script", target_node_id="script", target_port="script"),
        ]
    elif template is WorkflowTemplate.image:
        edges = [
            WorkflowEdge(id="prompt-image", source_node_id="prompt", source_port="prompt", target_node_id="image", target_port="prompt"),
            WorkflowEdge(id="image-selection", source_node_id="image", source_port="candidates", target_node_id="selection", target_port="candidates"),
        ]
    elif template is WorkflowTemplate.video:
        edges = [
            WorkflowEdge(id="keyframe-shot", source_node_id="keyframe", source_port="keyframe", target_node_id="shot", target_port="keyframe"),
            WorkflowEdge(id="shot-take", source_node_id="shot", source_port="takes", target_node_id="take", target_port="takes"),
        ]
    else:
        edges = [
            WorkflowEdge(id="reference-strategy", source_node_id="reference", source_port="reference", target_node_id="strategy", target_port="reference"),
            WorkflowEdge(id="strategy-script", source_node_id="strategy", source_port="direction", target_node_id="script", target_port="direction"),
            WorkflowEdge(id="strategy-design", source_node_id="strategy", source_port="direction", target_node_id="design", target_port="direction"),
            WorkflowEdge(id="script-director", source_node_id="script", source_port="script", target_node_id="director", target_port="script"),
            WorkflowEdge(id="design-director", source_node_id="design", source_port="design", target_node_id="director", target_port="design"),
            WorkflowEdge(id="director-delivery", source_node_id="director", source_port="storyboard", target_node_id="delivery", target_port="storyboard"),
        ]
    return WorkflowGraph(nodes=nodes, edges=edges)


def new_workflow(request: WorkflowCreateRequest, created_by: str) -> Workflow:
    title = request.title.strip() if request.title and request.title.strip() else {
        WorkflowTemplate.script: "Untitled script workflow",
        WorkflowTemplate.image: "Untitled image workflow",
        WorkflowTemplate.video: "Untitled video workflow",
        WorkflowTemplate.commercial: "Untitled commercial workflow",
    }[request.template]
    return Workflow(workflow_id=f"wf_{uuid4().hex[:16]}", workspace_id=request.workspace_id, title=title, template=request.template, graph=template_graph(request.template), created_by=created_by)


def validate_graph(graph: WorkflowGraph) -> WorkflowValidationResult:
    issues: list[WorkflowValidationIssue] = []
    node_ids = {node.id for node in graph.nodes}
    definitions = {definition.type: definition for definition in NODE_DEFINITIONS}
    known_node_types = set(definitions)
    if not node_ids:
        issues.append(WorkflowValidationIssue(message="Add at least one node before validating."))
    for node in graph.nodes:
        if node.type not in known_node_types:
            issues.append(WorkflowValidationIssue(node_id=node.id, message=f"'{node.label}' is not a supported workflow node."))
    if len(node_ids) != len(graph.nodes):
        issues.append(WorkflowValidationIssue(message="Each workflow node needs a unique ID."))
    incoming_ports: set[tuple[str, str]] = set()
    for edge in graph.edges:
        if edge.source_node_id not in node_ids:
            issues.append(WorkflowValidationIssue(node_id=edge.target_node_id, message=f"Connection source '{edge.source_node_id}' does not exist."))
        if edge.target_node_id not in node_ids:
            issues.append(WorkflowValidationIssue(node_id=edge.source_node_id, message=f"Connection target '{edge.target_node_id}' does not exist."))
        if edge.source_node_id == edge.target_node_id:
            issues.append(WorkflowValidationIssue(node_id=edge.source_node_id, message="A node cannot connect to itself."))
            continue
        source = next((node for node in graph.nodes if node.id == edge.source_node_id), None)
        target = next((node for node in graph.nodes if node.id == edge.target_node_id), None)
        if not source or not target or source.type not in definitions or target.type not in definitions:
            continue
        source_definition = definitions[source.type]
        target_definition = definitions[target.type]
        # Pre-v1 graphs used generic `output` / `input`; retain those documents
        # when a node has exactly one applicable port, but all new edges are typed.
        source_port = edge.source_port if edge.source_port != "output" else (source_definition.outputs[0].id if len(source_definition.outputs) == 1 else edge.source_port)
        target_port = edge.target_port if edge.target_port != "input" else (target_definition.inputs[0].id if len(target_definition.inputs) == 1 else edge.target_port)
        output = next((port for port in source_definition.outputs if port.id == source_port), None)
        input_ = next((port for port in target_definition.inputs if port.id == target_port), None)
        if output is None:
            issues.append(WorkflowValidationIssue(node_id=source.id, port_id=edge.source_port, message=f"'{source.label}' has no output port '{edge.source_port}'."))
            continue
        if input_ is None:
            issues.append(WorkflowValidationIssue(node_id=target.id, port_id=edge.target_port, message=f"'{target.label}' has no input port '{edge.target_port}'."))
            continue
        if output.value_type != input_.value_type:
            issues.append(WorkflowValidationIssue(node_id=target.id, port_id=input_.id, message=f"'{target.label}' expects {input_.value_type}, but this connection provides {output.value_type}."))
        port_key = (target.id, input_.id)
        if port_key in incoming_ports and not input_.multiple:
            issues.append(WorkflowValidationIssue(node_id=target.id, port_id=input_.id, message=f"'{target.label}' accepts only one connection on '{input_.id}'."))
        incoming_ports.add(port_key)
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    reverse_adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in graph.edges:
        if edge.source_node_id in adjacency and edge.target_node_id in adjacency:
            adjacency[edge.source_node_id].append(edge.target_node_id)
            reverse_adjacency[edge.target_node_id].append(edge.source_node_id)
    if len(node_ids) > 1:
        for node in graph.nodes:
            if not adjacency[node.id] and not reverse_adjacency[node.id]:
                issues.append(WorkflowValidationIssue(node_id=node.id, message=f"Connect '{node.label}' or remove it before running."))
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node_id: str) -> None:
        if node_id in visiting:
            issues.append(WorkflowValidationIssue(node_id=node_id, message="Workflow contains a circular dependency."))
            return
        if node_id in visited:
            return
        visiting.add(node_id)
        for target in adjacency[node_id]:
            visit(target)
        visiting.remove(node_id)
        visited.add(node_id)
    for node_id in node_ids:
        visit(node_id)
    for node in graph.nodes:
        definition = definitions.get(node.type)
        if not definition:
            continue
        connected = {edge.target_port if edge.target_port != "input" else (definition.inputs[0].id if len(definition.inputs) == 1 else edge.target_port) for edge in graph.edges if edge.target_node_id == node.id}
        for port in definition.inputs:
            if port.required and port.id not in connected:
                issues.append(WorkflowValidationIssue(node_id=node.id, port_id=port.id, message=f"Connect the required '{port.id}' input for '{node.label}'."))
    return WorkflowValidationResult(valid=not issues, issues=issues)
