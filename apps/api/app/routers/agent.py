from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services.auth import require_internal_key
from app.services.agent_service import AgentService

router = APIRouter(
    prefix="/api/v1/agent",
    tags=["agent"],
    dependencies=[Depends(require_internal_key)],
)

_service: AgentService | None = None


def _get_service() -> AgentService:
    global _service
    if _service is None:
        _service = AgentService()
    return _service


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    module: str = "supply"
    dataset: str = "no-sdk-no-ua"
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    module: str


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    service = _get_service()
    history = [{"role": m.role, "content": m.content} for m in req.history]
    reply = await service.chat(req.message, req.module, history, req.dataset)
    return ChatResponse(reply=reply, module=req.module)
