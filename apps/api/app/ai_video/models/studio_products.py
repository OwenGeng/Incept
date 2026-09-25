from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.ai_video.core.db import Base
from app.ai_video.models.base import TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    prohibited_changes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    selected_asset_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    assets: Mapped[list["ProductAsset"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProductAsset.created_at",
    )

    __table_args__ = (Index("ix_products_project_name", "project_id", "name"),)


class ProductAsset(Base, TimestampMixin):
    __tablename__ = "product_assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("files.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False, default="candidate")
    source_asset_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("product_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    product: Mapped[Product] = relationship(back_populates="assets", foreign_keys=[product_id])

    __table_args__ = (
        Index("ix_product_assets_product_role", "product_id", "role", "lifecycle"),
    )


__all__ = ["Product", "ProductAsset"]
