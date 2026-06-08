"""
In-memory session store.

A session = one continuous creative conversation:
  - Tracks reference images the user has uploaded
  - Keeps the last N message exchanges for GPT-4o context
  - Links generation jobs back to the session that created them

Sessions survive for the life of the server process. A future version
can persist them to SQLite using the same pattern as jobs/assets.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.incept.models import Session, SessionMessage

# ── In-memory store ───────────────────────────────────────────────────────────

SESSIONS: dict[str, Session] = {}

# ── Public API ────────────────────────────────────────────────────────────────

def create_session(workspace_id: str) -> Session:
    session = Session(
        session_id=f"sess_{uuid4().hex[:12]}",
        workspace_id=workspace_id,
    )
    SESSIONS[session.session_id] = session
    return session


def get_session(session_id: str) -> Session | None:
    return SESSIONS.get(session_id)


def get_or_create(session_id: str | None, workspace_id: str) -> Session:
    """Return existing session or create a fresh one."""
    if session_id and session_id in SESSIONS:
        return SESSIONS[session_id]
    return create_session(workspace_id)


def add_user_message(
    session_id: str,
    text: str,
    reference_asset_ids: list[str] | None = None,
) -> None:
    session = SESSIONS.get(session_id)
    if not session:
        return
    msg = SessionMessage(role="user", text=text, asset_ids=reference_asset_ids or [])
    session.messages.append(msg)
    # Accumulate reference images across the session
    if reference_asset_ids:
        known = set(session.reference_asset_ids)
        session.reference_asset_ids = list(known | set(reference_asset_ids))
    session.updated_at = datetime.utcnow()


def add_assistant_message(
    session_id: str,
    text: str,
    asset_ids: list[str],
    job_id: str,
) -> None:
    session = SESSIONS.get(session_id)
    if not session:
        return
    msg = SessionMessage(role="assistant", text=text, asset_ids=asset_ids, job_id=job_id)
    session.messages.append(msg)
    session.updated_at = datetime.utcnow()


def get_context_messages(session_id: str, n: int = 6) -> list[dict]:
    """
    Return the last *n* session messages in the format GPT-4o expects:
      [{"role": "user"|"assistant", "content": "..."}]
    """
    session = SESSIONS.get(session_id)
    if not session:
        return []
    result = []
    for msg in session.messages[-n:]:
        content = msg.text
        if msg.role == "assistant" and msg.asset_ids:
            content += f"\n[Generated {len(msg.asset_ids)} image(s), job_id={msg.job_id}]"
        result.append({"role": msg.role, "content": content})
    return result


def get_session_reference_assets(session_id: str) -> list[str]:
    """All reference image asset IDs accumulated in this session."""
    session = SESSIONS.get(session_id)
    return session.reference_asset_ids if session else []
