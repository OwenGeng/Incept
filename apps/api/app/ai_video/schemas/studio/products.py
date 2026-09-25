from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    claims: list[dict[str, Any]] = Field(default_factory=list)
    prohibited_changes: list[str] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    claims: list[dict[str, Any]] | None = None
    prohibited_changes: list[str] | None = None


class ProductAssetCreate(BaseModel):
    file_id: str = Field(min_length=1, max_length=64)
    role: Literal["truth_anchor", "standardized"]
    source_asset_id: str | None = Field(None, max_length=64)
    prompt: str = ""
    input_fingerprint: str = Field("", max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_lineage(self) -> "ProductAssetCreate":
        if self.role == "truth_anchor" and self.source_asset_id:
            raise ValueError("Truth anchors cannot derive from another product asset")
        if self.role == "standardized" and not self.source_asset_id:
            raise ValueError("Standardized product assets require a truth-anchor source_asset_id")
        return self


class ProductAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str
    file_id: str
    role: str
    lifecycle: str
    source_asset_id: str | None
    prompt: str
    input_fingerprint: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    description: str
    claims: list[dict[str, Any]]
    prohibited_changes: list[str]
    selected_asset_id: str | None
    assets: list[ProductAssetRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProductAssetSelection(BaseModel):
    selected_by: str | None = Field(None, max_length=255)


__all__ = [
    "ProductAssetCreate",
    "ProductAssetRead",
    "ProductAssetSelection",
    "ProductCreate",
    "ProductRead",
    "ProductUpdate",
]
