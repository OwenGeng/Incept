from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ResearchEntryMode = Literal["research", "preset"]
ResearchStatus = Literal["draft", "researching", "ready", "approved"]
ResearchSourceType = Literal[
    "product_page",
    "product_asset",
    "competitor_video",
    "reference_video",
    "brand_guideline",
]


class CreativeBrief(BaseModel):
    advertiser_vertical: str = ""
    delivery_channel: str = ""
    product_name: str = ""
    product_description: str = ""
    product_url: str | None = None
    product_asset_file_ids: list[str] = Field(default_factory=list)
    market: str | None = None
    target_audience: str = ""
    conversion_goal: str = ""
    key_messages: list[str] = Field(default_factory=list)
    cta: str = ""
    legal: str = ""
    prohibited_claims: list[str] = Field(default_factory=list)
    claim_evidence: list[dict[str, str]] = Field(default_factory=list)
    target_duration_seconds: int | None = Field(None, ge=5, le=180)
    aspect_ratios: list[Literal["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]] = Field(default_factory=list)
    language: str = "en"
    required_overlays: list[Literal["logo", "cta", "legal", "end_card"]] = Field(default_factory=list)
    logo_file_id: str | None = Field(None, max_length=64)
    brand_colors: list[str] = Field(default_factory=list)
    brand_font_family: str = Field("Arial", min_length=1, max_length=128, pattern=r"^[^,\r\n]+$")
    safe_area_percent: int = Field(5, ge=3, le=20)
    budget_amount: Decimal | None = Field(None, ge=0)
    budget_currency: str | None = Field(None, min_length=3, max_length=3)
    default_image_model_id: str | None = Field(None, max_length=64)
    default_video_model_id: str | None = Field(None, max_length=64)
    creative_format: str | None = None
    creative_playbook: str | None = None
    visual_direction: str | None = None
    script_direction: str | None = None

    @field_validator("brand_colors")
    @classmethod
    def validate_brand_colors(cls, values: list[str]) -> list[str]:
        for value in values:
            if len(value) != 7 or not value.startswith("#"):
                raise ValueError("Brand colors must use #RRGGBB format")
            try:
                int(value[1:], 16)
            except ValueError as exc:
                raise ValueError("Brand colors must use #RRGGBB format") from exc
        return values

    @model_validator(mode="after")
    def require_product_input(self) -> "CreativeBrief":
        if not (self.product_url and self.product_url.strip()) and not self.product_asset_file_ids:
            raise ValueError("A product webpage or at least one product asset is required")
        return self


class ResearchSource(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    type: ResearchSourceType
    title: str = Field(min_length=1, max_length=255)
    url: str | None = None
    file_id: str | None = None
    notes: str = ""
    rights_confirmed: bool = False


class ResearchFinding(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    observation: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)


class CreativeDirection(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    creative_format: str = Field(min_length=1)
    creative_playbook: str = Field(min_length=1)
    visual_direction: str = Field(min_length=1)
    script_direction: str = Field(min_length=1)
    rationale: str = ""
    evidence_finding_ids: list[str] = Field(default_factory=list)


class ProjectResearchWrite(BaseModel):
    entry_mode: ResearchEntryMode = "research"
    status: ResearchStatus = "draft"
    brief: CreativeBrief
    sources: list[ResearchSource] = Field(default_factory=list)
    findings: list[ResearchFinding] = Field(default_factory=list)
    creative_directions: list[CreativeDirection] = Field(default_factory=list)
    approved_direction_id: str | None = None

    @model_validator(mode="after")
    def validate_document(self) -> "ProjectResearchWrite":
        direction_ids = [item.id for item in self.creative_directions]
        if len(direction_ids) != len(set(direction_ids)):
            raise ValueError("Creative direction IDs must be unique")
        if self.approved_direction_id and self.approved_direction_id not in direction_ids:
            raise ValueError("approved_direction_id must reference a creative direction")
        if self.status == "approved" and not self.approved_direction_id:
            raise ValueError("Approved research requires an approved creative direction")
        if self.entry_mode == "preset" and self.status != "approved":
            raise ValueError("Preset projects require a pre-approved creative direction")
        return self


class ProjectResearchRead(ProjectResearchWrite):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    exists: bool = True


class ResearchApprovalRequest(BaseModel):
    direction_id: str = Field(min_length=1, max_length=64)


__all__ = [
    "CreativeBrief",
    "CreativeDirection",
    "ProjectResearchRead",
    "ProjectResearchWrite",
    "ResearchApprovalRequest",
    "ResearchFinding",
    "ResearchSource",
]
