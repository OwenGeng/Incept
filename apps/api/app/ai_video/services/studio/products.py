from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai_video.models.production_control import ProductionAuditEvent
from app.ai_video.models.studio import Chapter, FileItem, FileType, Product, ProductAsset, Project, Shot
from app.ai_video.schemas.studio.products import ProductAssetCreate, ProductCreate, ProductUpdate
from app.ai_video.schemas.studio.shots import ShotLinkedAssetItem
from app.ai_video.services.studio.file_usages import upsert_file_usage
from app.ai_video.services.studio.production_control import canonical_fingerprint


async def _load_product(db: AsyncSession, *, project_id: str, product_id: str, lock: bool = False) -> Product:
    stmt = (
        select(Product)
        .options(selectinload(Product.assets))
        .where(Product.id == product_id, Product.project_id == project_id)
    )
    if lock:
        stmt = stmt.with_for_update()
    product = (await db.execute(stmt)).scalars().first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


async def list_products(db: AsyncSession, *, project_id: str) -> list[Product]:
    stmt = (
        select(Product)
        .options(selectinload(Product.assets))
        .where(Product.project_id == project_id)
        .order_by(Product.created_at.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def create_product(db: AsyncSession, *, project_id: str, body: ProductCreate) -> Product:
    if await db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    product = Product(
        id=str(uuid4()),
        project_id=project_id,
        name=body.name,
        description=body.description,
        claims=body.claims,
        prohibited_changes=body.prohibited_changes,
    )
    db.add(product)
    await db.flush()
    return await _load_product(db, project_id=project_id, product_id=product.id)


async def update_product(
    db: AsyncSession,
    *,
    project_id: str,
    product_id: str,
    body: ProductUpdate,
) -> Product:
    product = await _load_product(db, project_id=project_id, product_id=product_id, lock=True)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    await db.flush()
    return product


async def add_product_asset(
    db: AsyncSession,
    *,
    project_id: str,
    product_id: str,
    body: ProductAssetCreate,
) -> ProductAsset:
    product = await _load_product(db, project_id=project_id, product_id=product_id, lock=True)
    file_obj = await db.get(FileItem, body.file_id)
    allowed_types = {FileType.image, FileType.video} if body.role == "truth_anchor" else {FileType.image}
    if file_obj is None or file_obj.type not in allowed_types:
        raise HTTPException(status_code=409, detail=f"{body.role} requires a valid {'image or video' if body.role == 'truth_anchor' else 'image'} file")
    source: ProductAsset | None = None
    if body.source_asset_id:
        source = await db.get(ProductAsset, body.source_asset_id)
        if source is None or source.product_id != product.id or source.role != "truth_anchor":
            raise HTTPException(status_code=409, detail="Standardized asset must derive from this product's truth anchor")
    fingerprint = body.input_fingerprint or canonical_fingerprint(
        {
            "file_id": body.file_id,
            "role": body.role,
            "source_asset_id": body.source_asset_id,
            "prompt": body.prompt,
            "metadata": body.metadata,
        }
    )
    asset = ProductAsset(
        id=str(uuid4()),
        product_id=product.id,
        file_id=body.file_id,
        role=body.role,
        lifecycle="candidate",
        source_asset_id=body.source_asset_id,
        prompt=body.prompt,
        input_fingerprint=fingerprint,
        metadata_json=body.metadata,
    )
    db.add(asset)
    await db.flush()
    await upsert_file_usage(
        db,
        file_id=file_obj.id,
        project_id=project_id,
        chapter_id=None,
        shot_id=None,
        usage_kind="asset_image" if file_obj.type == FileType.image else "upload",
        source_ref=f"product:{product.id}:{asset.id}",
    )
    return asset


async def select_product_asset(
    db: AsyncSession,
    *,
    project_id: str,
    product_id: str,
    asset_id: str,
    selected_by: str | None,
) -> Product:
    product = await _load_product(db, project_id=project_id, product_id=product_id, lock=True)
    # The session is configured with ``autoflush=False`` and callers may add an
    # asset and select it in the same transaction.  Query the assets directly
    # instead of trusting a previously-loaded relationship collection, which
    # can legitimately be stale in that situation.
    assets_stmt = (
        select(ProductAsset)
        .where(ProductAsset.product_id == product.id)
        .order_by(ProductAsset.created_at.asc())
        .with_for_update()
    )
    assets = list((await db.execute(assets_stmt)).scalars().all())
    selected = next((item for item in assets if item.id == asset_id), None)
    if selected is None:
        raise HTTPException(status_code=404, detail="Product asset not found")
    for asset in assets:
        if asset.id == selected.id:
            asset.lifecycle = "selected"
        elif asset.lifecycle == "selected":
            asset.lifecycle = "candidate"
    product.selected_asset_id = selected.id
    db.add(
        ProductionAuditEvent(
            id=str(uuid4()),
            project_id=project_id,
            actor=selected_by,
            action="product_asset.selected",
            target_type="product_asset",
            target_id=selected.id,
            detail={
                "product_id": product.id,
                "file_id": selected.file_id,
                "role": selected.role,
                "truth_anchor_id": selected.source_asset_id if selected.role == "standardized" else selected.id,
            },
            created_at=datetime.now(UTC),
        )
    )
    await db.flush()
    return product


async def selected_product_reference_items(db: AsyncSession, *, shot_id: str) -> list[ShotLinkedAssetItem]:
    """Return the project-level product selections that must anchor shot frames.

    Product selection is explicit and durable.  Frame generation consumes that
    selection automatically so a producer cannot accidentally omit the packshot
    while still keeping caller-provided references in their original order.
    """
    project_id_stmt = (
        select(Chapter.project_id)
        .join(Shot, Shot.chapter_id == Chapter.id)
        .where(Shot.id == shot_id)
    )
    project_id = (await db.execute(project_id_stmt)).scalars().first()
    if project_id is None:
        return []
    stmt = (
        select(Product, ProductAsset)
        .join(ProductAsset, ProductAsset.id == Product.selected_asset_id)
        .where(Product.project_id == project_id)
        .order_by(Product.created_at.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        ShotLinkedAssetItem(
            type="product",
            id=product.id,
            image_id=None,
            file_id=asset.file_id,
            name=product.name,
            thumbnail=f"/api/v1/studio/files/{asset.file_id}/download",
        )
        for product, asset in rows
    ]


__all__ = [
    "add_product_asset",
    "create_product",
    "list_products",
    "select_product_asset",
    "selected_product_reference_items",
    "update_product",
]
