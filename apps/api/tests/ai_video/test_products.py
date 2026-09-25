from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai_video.core.db import Base
from app.ai_video.models.studio import Chapter, FileItem, FileType, ProductAsset, Project, ProjectStyle, ProjectVisualStyle, Shot
from app.ai_video.schemas.studio.products import ProductAssetCreate, ProductCreate
from app.ai_video.services.studio.products import (
    add_product_asset,
    create_product,
    select_product_asset,
    selected_product_reference_items,
)


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed(db: AsyncSession) -> None:
    db.add(Project(id="project-1", name="Ad", description="", style=ProjectStyle.advertising_general, visual_style=ProjectVisualStyle.live_action))
    db.add_all(
        [
            FileItem(id="anchor-file", type=FileType.image, name="Original packshot", thumbnail="", tags=[], storage_key="products/original.png"),
            FileItem(id="derived-file-1", type=FileType.image, name="Clean packshot", thumbnail="", tags=[], storage_key="products/clean-1.png"),
            FileItem(id="derived-file-2", type=FileType.image, name="Alternate packshot", thumbnail="", tags=[], storage_key="products/clean-2.png"),
        ]
    )
    await db.commit()


@pytest.mark.asyncio
async def test_product_truth_anchor_and_standardized_assets_keep_lineage_and_selection() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        product = await create_product(
            db,
            project_id="project-1",
            body=ProductCreate(name="Bottle", description="Customer supplied bottle", prohibited_changes=["logo", "shape"]),
        )
        anchor = await add_product_asset(
            db,
            project_id="project-1",
            product_id=product.id,
            body=ProductAssetCreate(file_id="anchor-file", role="truth_anchor"),
        )
        first = await add_product_asset(
            db,
            project_id="project-1",
            product_id=product.id,
            body=ProductAssetCreate(file_id="derived-file-1", role="standardized", source_asset_id=anchor.id, prompt="Clean background"),
        )
        second = await add_product_asset(
            db,
            project_id="project-1",
            product_id=product.id,
            body=ProductAssetCreate(file_id="derived-file-2", role="standardized", source_asset_id=anchor.id, prompt="Alternate crop"),
        )
        selected = await select_product_asset(db, project_id="project-1", product_id=product.id, asset_id=first.id, selected_by="producer")
        selected = await select_product_asset(db, project_id="project-1", product_id=product.id, asset_id=second.id, selected_by="producer")
        await db.commit()

        assert selected.selected_asset_id == second.id
        assert anchor.role == "truth_anchor" and anchor.source_asset_id is None
        assert first.source_asset_id == anchor.id and second.source_asset_id == anchor.id
        assert first.lifecycle == "candidate"
        assert second.lifecycle == "selected"
        assert await db.get(ProductAsset, anchor.id) is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_standardized_product_asset_rejects_cross_product_source() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        first = await create_product(db, project_id="project-1", body=ProductCreate(name="First"))
        second = await create_product(db, project_id="project-1", body=ProductCreate(name="Second"))
        anchor = await add_product_asset(
            db,
            project_id="project-1",
            product_id=first.id,
            body=ProductAssetCreate(file_id="anchor-file", role="truth_anchor"),
        )
        with pytest.raises(HTTPException) as exc_info:
            await add_product_asset(
                db,
                project_id="project-1",
                product_id=second.id,
                body=ProductAssetCreate(file_id="derived-file-1", role="standardized", source_asset_id=anchor.id),
            )
        assert exc_info.value.status_code == 409
    await engine.dispose()


@pytest.mark.asyncio
async def test_selected_product_becomes_automatic_shot_frame_reference() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        db.add(Chapter(id="chapter-1", project_id="project-1", index=1, title="Ad"))
        db.add(Shot(id="shot-1", chapter_id="chapter-1", index=1, title="Packshot"))
        await db.flush()
        product = await create_product(db, project_id="project-1", body=ProductCreate(name="Bottle"))
        anchor = await add_product_asset(
            db,
            project_id="project-1",
            product_id=product.id,
            body=ProductAssetCreate(file_id="anchor-file", role="truth_anchor"),
        )
        await select_product_asset(
            db,
            project_id="project-1",
            product_id=product.id,
            asset_id=anchor.id,
            selected_by="producer",
        )
        await db.flush()

        items = await selected_product_reference_items(db, shot_id="shot-1")

        assert len(items) == 1
        assert items[0].type == "product"
        assert items[0].name == "Bottle"
        assert items[0].file_id == "anchor-file"
    await engine.dispose()
