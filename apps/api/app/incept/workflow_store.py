"""SQLite-backed repository for Studio Workflows.

Runs are persisted before a worker may claim them. This keeps browser state,
provider jobs and post-restart recovery independent from FastAPI request scope.
"""

from __future__ import annotations

import json
from datetime import datetime
import hashlib
from uuid import uuid4

from app.incept.db import _connect, _schedule_db_backup, init_db
from app.incept.datetime_utils import utcnow_naive
from app.incept.workflows import (
    Workflow,
    WorkflowCreateRequest,
    WorkflowEvent,
    WorkflowOutput,
    WorkflowLineage,
    WorkflowRun,
    WorkflowRunNode,
    WorkflowRunRequest,
    WorkflowRunStatus,
    WorkflowRevision,
    WorkflowUpdateRequest,
    WorkflowValidationResult,
    new_workflow,
    validate_graph,
)


def _decode(payload: str) -> Workflow:
    return Workflow.model_validate_json(payload)


def create_workflow(request: WorkflowCreateRequest, created_by: str) -> Workflow:
    init_db()
    workflow = new_workflow(request, created_by)
    payload = workflow.model_dump_json()
    with _connect() as con:
        con.execute(
            """INSERT INTO workflows (workflow_id, workspace_id, title, template, status, revision, created_by, payload_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (workflow.workflow_id, workflow.workspace_id, workflow.title, workflow.template.value, workflow.status.value, workflow.revision, workflow.created_by, payload, workflow.created_at.isoformat(), workflow.updated_at.isoformat()),
        )
        con.execute(
            "INSERT INTO workflow_revisions (workflow_id, revision, payload_json, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (workflow.workflow_id, workflow.revision, payload, created_by, workflow.created_at.isoformat()),
        )
    _schedule_db_backup()
    return workflow


def get_workflow(workflow_id: str, workspace_id: str | None = None) -> Workflow | None:
    init_db()
    with _connect() as con:
        if workspace_id:
            row = con.execute("SELECT payload_json FROM workflows WHERE workflow_id = ? AND workspace_id = ?", (workflow_id, workspace_id)).fetchone()
        else:
            row = con.execute("SELECT payload_json FROM workflows WHERE workflow_id = ?", (workflow_id,)).fetchone()
    return _decode(row["payload_json"]) if row else None


def list_workflows(workspace_id: str) -> list[Workflow]:
    init_db()
    with _connect() as con:
        rows = con.execute("SELECT payload_json FROM workflows WHERE workspace_id = ? ORDER BY updated_at DESC", (workspace_id,)).fetchall()
    return [_decode(row["payload_json"]) for row in rows]


def list_revisions(workflow_id: str, workspace_id: str) -> list[WorkflowRevision]:
    if get_workflow(workflow_id, workspace_id) is None:
        raise KeyError("Workflow not found")
    with _connect() as con:
        rows = con.execute("SELECT revision, payload_json, created_by, created_at FROM workflow_revisions WHERE workflow_id = ? ORDER BY revision DESC", (workflow_id,)).fetchall()
    return [WorkflowRevision(workflow_id=workflow_id, revision=row["revision"], created_by=row["created_by"], created_at=datetime.fromisoformat(row["created_at"]), workflow=_decode(row["payload_json"])) for row in rows]


def update_workflow(workflow_id: str, request: WorkflowUpdateRequest, workspace_id: str, created_by: str) -> Workflow:
    current = get_workflow(workflow_id, workspace_id)
    if current is None:
        raise KeyError("Workflow not found")
    if request.expected_revision != current.revision:
        raise ValueError(f"This workflow changed elsewhere. Reload the latest revision ({current.revision}) before saving.")
    validation = validate_graph(request.graph)
    # Drafts can be invalid; validation details are returned independently before run.
    next_workflow = current.model_copy(update={
        "title": request.title.strip() if request.title and request.title.strip() else current.title,
        "graph": request.graph,
        "revision": current.revision + 1,
        "updated_at": utcnow_naive(),
    })
    payload = next_workflow.model_dump_json()
    with _connect() as con:
        changed = con.execute(
            """UPDATE workflows SET title = ?, revision = ?, payload_json = ?, updated_at = ?
               WHERE workflow_id = ? AND workspace_id = ? AND revision = ?""",
            (next_workflow.title, next_workflow.revision, payload, next_workflow.updated_at.isoformat(), workflow_id, workspace_id, current.revision),
        ).rowcount
        if not changed:
            raise ValueError("This workflow changed elsewhere. Reload the latest revision before saving.")
        con.execute(
            "INSERT INTO workflow_revisions (workflow_id, revision, payload_json, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (workflow_id, next_workflow.revision, payload, created_by, next_workflow.updated_at.isoformat()),
        )
    _schedule_db_backup()
    return next_workflow


def delete_workflow(workflow_id: str, workspace_id: str) -> bool:
    with _connect() as con:
        cursor = con.execute("DELETE FROM workflows WHERE workflow_id = ? AND workspace_id = ?", (workflow_id, workspace_id))
        con.execute("DELETE FROM workflow_revisions WHERE workflow_id = ?", (workflow_id,))
        con.execute("DELETE FROM workflow_runs WHERE workflow_id = ?", (workflow_id,))
        con.execute("DELETE FROM workflow_outputs WHERE workflow_id = ? AND workspace_id = ?", (workflow_id, workspace_id))
    _schedule_db_backup()
    return bool(cursor.rowcount)


def validate_workflow(workflow_id: str, workspace_id: str) -> WorkflowValidationResult:
    workflow = get_workflow(workflow_id, workspace_id)
    if workflow is None:
        raise KeyError("Workflow not found")
    return validate_graph(workflow.graph)


def create_run(workflow_id: str, workspace_id: str, request: WorkflowRunRequest, created_by: str) -> WorkflowRun:
    workflow = get_workflow(workflow_id, workspace_id)
    if workflow is None:
        raise KeyError("Workflow not found")
    validation = validate_graph(workflow.graph)
    if not validation.valid:
        raise ValueError("Fix workflow validation issues before running.")
    node_ids = {node.id for node in workflow.graph.nodes}
    unknown_outputs = [node_id for node_id in request.output_node_ids if node_id not in node_ids]
    if unknown_outputs:
        raise ValueError(f"Requested output node does not exist: {unknown_outputs[0]}")
    now = utcnow_naive()
    run = WorkflowRun(
        run_id=f"wfr_{uuid4().hex[:16]}", workflow_id=workflow_id, workspace_id=workspace_id,
        revision=workflow.revision, requested_output_node_ids=request.output_node_ids, priority=request.priority, created_by=created_by,
        created_at=now, updated_at=now,
    )
    with _connect() as con:
        con.execute(
            """INSERT INTO workflow_runs (run_id, workflow_id, workspace_id, revision, status, requested_output_node_ids, priority, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run.run_id, run.workflow_id, run.workspace_id, run.revision, run.status.value, json.dumps(run.requested_output_node_ids), run.priority, run.created_by, now.isoformat(), now.isoformat()),
        )
        con.executemany(
            """INSERT INTO workflow_run_nodes (run_id, node_id, node_type, status, progress, message, result_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(run.run_id, node.id, node.type, "queued", 0, "Waiting for dependencies.", "{}", now.isoformat(), now.isoformat()) for node in workflow.graph.nodes],
        )
    append_event(WorkflowEvent(event_id=f"wfe_{uuid4().hex[:16]}", run_id=run.run_id, type="run.queued", message="Workflow is queued for durable execution.", progress=0))
    _schedule_db_backup()
    return run


def list_events(run_id: str) -> list[WorkflowEvent]:
    with _connect() as con:
        rows = con.execute("SELECT * FROM workflow_events WHERE run_id = ? ORDER BY created_at ASC", (run_id,)).fetchall()
    return [WorkflowEvent(event_id=row["event_id"], run_id=row["run_id"], node_id=row["node_id"], type=row["type"], message=row["message"], progress=row["progress"], created_at=datetime.fromisoformat(row["created_at"])) for row in rows]


def run_in_workspace(run_id: str, workspace_id: str) -> bool:
    with _connect() as con:
        row = con.execute("SELECT 1 FROM workflow_runs WHERE run_id = ? AND workspace_id = ?", (run_id, workspace_id)).fetchone()
    return bool(row)


def get_run(run_id: str, workspace_id: str) -> WorkflowRun | None:
    with _connect() as con:
        row = con.execute("SELECT * FROM workflow_runs WHERE run_id = ? AND workspace_id = ?", (run_id, workspace_id)).fetchone()
    if not row:
        return None
    return WorkflowRun(
        run_id=row["run_id"], workflow_id=row["workflow_id"], workspace_id=row["workspace_id"], revision=row["revision"],
        status=WorkflowRunStatus(row["status"]), requested_output_node_ids=json.loads(row["requested_output_node_ids"]), priority=row["priority"] if "priority" in row.keys() else 0,
        created_by=row["created_by"], created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def retry_run(run_id: str, workspace_id: str, created_by: str) -> WorkflowRun:
    previous = get_run(run_id, workspace_id)
    if previous is None:
        raise KeyError("Workflow run not found")
    if previous.status not in {WorkflowRunStatus.failed, WorkflowRunStatus.cancelled}:
        raise ValueError("Only a failed or cancelled workflow run can be retried.")
    return create_run(
        previous.workflow_id,
        workspace_id,
        WorkflowRunRequest(output_node_ids=previous.requested_output_node_ids, priority=previous.priority),
        created_by,
    )


def list_run_nodes(run_id: str) -> list[WorkflowRunNode]:
    with _connect() as con:
        rows = con.execute("SELECT * FROM workflow_run_nodes WHERE run_id = ? ORDER BY created_at ASC", (run_id,)).fetchall()
    return [WorkflowRunNode(
        run_id=row["run_id"], node_id=row["node_id"], node_type=row["node_type"], status=row["status"], progress=row["progress"],
        message=row["message"], result=json.loads(row["result_json"]), created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]),
    ) for row in rows]


def record_output(
    run: WorkflowRun,
    *,
    node_id: str,
    output_type: str,
    value_id: str,
    metadata: dict | None = None,
) -> WorkflowOutput:
    """Persist an approval once; a retry never mutates the prior run's output."""
    now = utcnow_naive()
    output = WorkflowOutput(
        output_id=f"wfo_{uuid4().hex[:16]}", workflow_id=run.workflow_id, workspace_id=run.workspace_id,
        run_id=run.run_id, node_id=node_id, output_type=output_type, value_id=value_id,
        created_by=run.created_by, metadata=metadata or {}, created_at=now,
    )
    with _connect() as con:
        con.execute(
            """INSERT INTO workflow_outputs (output_id, workflow_id, workspace_id, run_id, node_id, output_type, value_id, created_by, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(run_id, node_id, value_id) DO NOTHING""",
            (output.output_id, output.workflow_id, output.workspace_id, output.run_id, output.node_id, output.output_type, output.value_id, output.created_by, json.dumps(output.metadata), output.created_at.isoformat()),
        )
        row = con.execute(
            "SELECT * FROM workflow_outputs WHERE run_id = ? AND node_id = ? AND value_id = ?",
            (run.run_id, node_id, value_id),
        ).fetchone()
    if row["output_id"] != output.output_id:
        return WorkflowOutput(
            output_id=row["output_id"], workflow_id=row["workflow_id"], workspace_id=row["workspace_id"], run_id=row["run_id"],
            node_id=row["node_id"], output_type=row["output_type"], value_id=row["value_id"], created_by=row["created_by"],
            metadata=json.loads(row["metadata_json"]), created_at=datetime.fromisoformat(row["created_at"]),
        )
    _schedule_db_backup()
    return output


def list_outputs(workflow_id: str, workspace_id: str) -> list[WorkflowOutput]:
    with _connect() as con:
        rows = con.execute(
            "SELECT * FROM workflow_outputs WHERE workflow_id = ? AND workspace_id = ? ORDER BY created_at DESC",
            (workflow_id, workspace_id),
        ).fetchall()
    return [WorkflowOutput(
        output_id=row["output_id"], workflow_id=row["workflow_id"], workspace_id=row["workspace_id"], run_id=row["run_id"],
        node_id=row["node_id"], output_type=row["output_type"], value_id=row["value_id"], created_by=row["created_by"],
        metadata=json.loads(row["metadata_json"]), created_at=datetime.fromisoformat(row["created_at"]),
    ) for row in rows]


def get_lineage(workflow_id: str, workspace_id: str) -> WorkflowLineage:
    workflow = get_workflow(workflow_id, workspace_id)
    if workflow is None:
        raise KeyError("Workflow not found")
    with _connect() as con:
        rows = con.execute("SELECT * FROM workflow_runs WHERE workflow_id = ? AND workspace_id = ? ORDER BY created_at DESC", (workflow_id, workspace_id)).fetchall()
    runs = [WorkflowRun(run_id=row["run_id"], workflow_id=row["workflow_id"], workspace_id=row["workspace_id"], revision=row["revision"], status=WorkflowRunStatus(row["status"]), requested_output_node_ids=json.loads(row["requested_output_node_ids"]), priority=row["priority"] if "priority" in row.keys() else 0, created_by=row["created_by"], created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"])) for row in rows]
    return WorkflowLineage(
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        graph_revision=workflow.revision,
        graph=workflow.graph,
        outputs=list_outputs(workflow_id, workspace_id),
        runs=runs,
        run_nodes=[node for run in runs for node in list_run_nodes(run.run_id)],
    )


def workflow_node_cache_key(workspace_id: str, node_type: str, payload: dict) -> str:
    """Stable cache key for pure workflow steps; never includes credentials or user data."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(f"{workspace_id}:{node_type}:{encoded}".encode()).hexdigest()


def get_cached_node_result(cache_key: str) -> dict | None:
    with _connect() as con:
        row = con.execute("SELECT result_json FROM workflow_node_cache WHERE cache_key = ?", (cache_key,)).fetchone()
    return json.loads(row["result_json"]) if row else None


def cache_node_result(workspace_id: str, node_type: str, cache_key: str, result: dict) -> None:
    now = utcnow_naive().isoformat()
    with _connect() as con:
        con.execute(
            """INSERT INTO workflow_node_cache (cache_key, workspace_id, node_type, result_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(cache_key) DO UPDATE SET result_json = excluded.result_json, updated_at = excluded.updated_at""",
            (cache_key, workspace_id, node_type, json.dumps(result), now, now),
        )
    _schedule_db_backup()


def claim_next_run() -> tuple[WorkflowRun, Workflow] | None:
    """Atomically claim one queued run. A future separate worker process uses the same claim."""
    init_db()
    now = utcnow_naive()
    with _connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM workflow_runs WHERE status = ? ORDER BY priority DESC, created_at ASC LIMIT 1", (WorkflowRunStatus.queued.value,)).fetchone()
        if not row:
            con.commit()
            return None
        changed = con.execute("UPDATE workflow_runs SET status = ?, updated_at = ? WHERE run_id = ? AND status = ?", (WorkflowRunStatus.running.value, now.isoformat(), row["run_id"], WorkflowRunStatus.queued.value)).rowcount
        if not changed:
            con.commit()
            return None
        payload = con.execute("SELECT payload_json FROM workflow_revisions WHERE workflow_id = ? AND revision = ?", (row["workflow_id"], row["revision"])).fetchone()
        con.commit()
    if not payload:
        return None
    run = WorkflowRun(run_id=row["run_id"], workflow_id=row["workflow_id"], workspace_id=row["workspace_id"], revision=row["revision"], status=WorkflowRunStatus.running, requested_output_node_ids=json.loads(row["requested_output_node_ids"]), priority=row["priority"] if "priority" in row.keys() else 0, created_by=row["created_by"], created_at=datetime.fromisoformat(row["created_at"]), updated_at=now)
    append_event(WorkflowEvent(event_id=f"wfe_{uuid4().hex[:16]}", run_id=run.run_id, type="run.running", message="Workflow worker claimed this run.", progress=0))
    return run, _decode(payload["payload_json"])


def update_run_status(run_id: str, status: WorkflowRunStatus, message: str) -> None:
    now = utcnow_naive()
    with _connect() as con:
        con.execute("UPDATE workflow_runs SET status = ?, updated_at = ? WHERE run_id = ?", (status.value, now.isoformat(), run_id))
    append_event(WorkflowEvent(event_id=f"wfe_{uuid4().hex[:16]}", run_id=run_id, type=f"run.{status.value}", message=message, progress=100 if status is WorkflowRunStatus.succeeded else None))
    _schedule_db_backup()


def update_run_node(run_id: str, node_id: str, status: str, message: str, progress: int, result: dict | None = None) -> None:
    now = utcnow_naive()
    with _connect() as con:
        con.execute("UPDATE workflow_run_nodes SET status = ?, message = ?, progress = ?, result_json = ?, updated_at = ? WHERE run_id = ? AND node_id = ?", (status, message, progress, json.dumps(result or {}), now.isoformat(), run_id, node_id))
    append_event(WorkflowEvent(event_id=f"wfe_{uuid4().hex[:16]}", run_id=run_id, node_id=node_id, type=f"node.{status}", message=message, progress=progress))
    _schedule_db_backup()


def is_run_cancelled(run_id: str) -> bool:
    with _connect() as con:
        row = con.execute("SELECT status FROM workflow_runs WHERE run_id = ?", (run_id,)).fetchone()
    return bool(row and row["status"] == WorkflowRunStatus.cancelled.value)


def append_event(event: WorkflowEvent) -> WorkflowEvent:
    with _connect() as con:
        con.execute(
            "INSERT INTO workflow_events (event_id, run_id, node_id, type, message, progress, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event.event_id, event.run_id, event.node_id, event.type, event.message, event.progress, event.created_at.isoformat()),
        )
    _schedule_db_backup()
    return event


def cancel_run(run_id: str, workspace_id: str) -> WorkflowRun | None:
    now = utcnow_naive()
    with _connect() as con:
        row = con.execute("SELECT * FROM workflow_runs WHERE run_id = ? AND workspace_id = ?", (run_id, workspace_id)).fetchone()
        if not row:
            return None
        if row["status"] in {WorkflowRunStatus.succeeded.value, WorkflowRunStatus.failed.value, WorkflowRunStatus.cancelled.value}:
            return WorkflowRun(run_id=row["run_id"], workflow_id=row["workflow_id"], workspace_id=row["workspace_id"], revision=row["revision"], status=WorkflowRunStatus(row["status"]), requested_output_node_ids=json.loads(row["requested_output_node_ids"]), priority=row["priority"] if "priority" in row.keys() else 0, created_by=row["created_by"], created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]))
        con.execute("UPDATE workflow_runs SET status = ?, updated_at = ? WHERE run_id = ?", (WorkflowRunStatus.cancelled.value, now.isoformat(), run_id))
    run = WorkflowRun(run_id=row["run_id"], workflow_id=row["workflow_id"], workspace_id=row["workspace_id"], revision=row["revision"], status=WorkflowRunStatus.cancelled, requested_output_node_ids=json.loads(row["requested_output_node_ids"]), priority=row["priority"] if "priority" in row.keys() else 0, created_by=row["created_by"], created_at=datetime.fromisoformat(row["created_at"]), updated_at=now)
    append_event(WorkflowEvent(event_id=f"wfe_{uuid4().hex[:16]}", run_id=run_id, type="run.cancelled", message="Workflow run cancelled.", progress=0))
    _schedule_db_backup()
    return run
