from __future__ import annotations

import uuid
from typing import Any

from app.models.supply import LeadCreate, LeadListPayload, LeadRecord, LeadStatusUpdate
from app.services.bigquery import BigQueryService


def _row_to_record(row: dict[str, Any]) -> LeadRecord:
    def _str(v: Any) -> str:
        return str(v) if v is not None else ""

    def _float_or_none(v: Any) -> float | None:
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    return LeadRecord(
        lead_id=_str(row.get("lead_id")),
        company_name=_str(row.get("company_name")),
        list_source=_str(row.get("list_source")),
        team_routing=_str(row.get("team_routing")),
        sent_to_team=_str(row.get("sent_to_team")),
        notes=_str(row.get("notes")),
        activated_by=_str(row.get("activated_by")),
        status=_str(row.get("status") or "sent"),
        activated_date=str(row.get("activated_date") or ""),
        last_updated=str(row.get("last_updated") or ""),
        converted_date=str(row["converted_date"]) if row.get("converted_date") else None,
        total_spend_90d=_float_or_none(row.get("total_spend_90d")),
        is_attributed=bool(row.get("is_attributed", False)),
    )


class LeadTrackingService:
    def __init__(self) -> None:
        self.bigquery = BigQueryService()
        self.bigquery.ensure_intersight_tables()

    def create_lead(self, payload: LeadCreate) -> LeadRecord:
        lead_id = str(uuid.uuid4())
        lead_dict = {
            "lead_id": lead_id,
            "company_name": payload.company_name,
            "list_source": payload.list_source,
            "team_routing": payload.team_routing,
            "sent_to_team": payload.sent_to_team,
            "notes": payload.notes,
            "activated_by": payload.activated_by,
            "status": "sent",
        }
        self.bigquery.insert_lead(lead_dict)
        return LeadRecord(
            lead_id=lead_id,
            company_name=payload.company_name,
            list_source=payload.list_source,
            team_routing=payload.team_routing,
            sent_to_team=payload.sent_to_team,
            notes=payload.notes,
            activated_by=payload.activated_by,
            status="sent",
            activated_date="",   # set server-side via CURRENT_DATE()
            last_updated="",
        )

    def list_leads(self, run_attribution: bool = False, email_filter: str | None = None) -> LeadListPayload:
        if run_attribution:
            rows = self.bigquery.run_attribution_check(email_filter=email_filter)
        else:
            rows = self.bigquery.list_leads(email_filter=email_filter)

        records = [_row_to_record(r) for r in rows]
        return LeadListPayload(
            leads=records,
            total=len(records),
            attributed_count=sum(1 for r in records if r.is_attributed),
            spending_count=sum(1 for r in records if r.status == "spending"),
        )

    def update_status(self, lead_id: str, update: LeadStatusUpdate) -> dict[str, str]:
        self.bigquery.append_lead_status(lead_id, update.status, update.notes)
        return {"lead_id": lead_id, "status": update.status}
