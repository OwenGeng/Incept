from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services.auth import require_internal_key
from app.services.bigquery import BigQueryService

router = APIRouter(
    prefix="/api/v1/feedback",
    tags=["feedback"],
    dependencies=[Depends(require_internal_key)],
)

_bq: BigQueryService | None = None


def _get_bq() -> BigQueryService:
    global _bq
    if _bq is None:
        _bq = BigQueryService()
        _bq.ensure_intersight_tables()
    return _bq


class FeedbackRequest(BaseModel):
    content: str
    user_email: str = ""


@router.post("", status_code=201)
async def submit_feedback(req: FeedbackRequest) -> dict:
    bq = _get_bq()
    feedback_id = str(uuid.uuid4())
    bq.write_feedback({"feedback_id": feedback_id, "content": req.content, "user_email": req.user_email})
    return {"feedback_id": feedback_id}
