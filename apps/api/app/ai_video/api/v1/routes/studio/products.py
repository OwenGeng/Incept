"""First-class advertising products and immutable truth-anchor assets."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.dependencies import get_db
from app.ai_video.schemas.common import ApiResponse, created_response, success_response
from app.ai_video.schemas.studio.products import (
    ProductAssetCreate,
    ProductAssetRead,
    ProductAssetSelection,
    ProductCreate,
    ProductRead,
    ProductUpdate,
)
from app.ai_video.services.studio.products import (
    add_product_asset,
    create_product,
    list_products,
    select_product_asset,
    update_product,
)

router = APIRouter()


@router.get("/projects/{project_id}/products", response_model=ApiResponse[list[ProductRead]])
async def get_products(project_id: str, db: AsyncSession = Depends(get_db)) -> ApiResponse[list[ProductRead]]:
    return success_response([ProductRead.model_validate(item) for item in await list_products(db, project_id=project_id)])


@router.post(
    "/projects/{project_id}/products",
    response_model=ApiResponse[ProductRead],
    status_code=status.HTTP_201_CREATED,
)
async def post_product(
    project_id: str,
    body: ProductCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProductRead]:
    product = await create_product(db, project_id=project_id, body=body)
    return created_response(ProductRead.model_validate(product))


@router.patch("/projects/{project_id}/products/{product_id}", response_model=ApiResponse[ProductRead])
async def patch_product(
    project_id: str,
    product_id: str,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProductRead]:
    product = await update_product(db, project_id=project_id, product_id=product_id, body=body)
    return success_response(ProductRead.model_validate(product))

@router.post(
    "/projects/{project_id}/products/{product_id}/assets",
    response_model=ApiResponse[ProductAssetRead],
    status_code=status.HTTP_201_CREATED,
)
async def post_product_asset(
    project_id: str,
    product_id: str,
    body: ProductAssetCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProductAssetRead]:
    asset = await add_product_asset(db, project_id=project_id, product_id=product_id, body=body)
    return created_response(ProductAssetRead.model_validate(asset))


@router.post(
    "/projects/{project_id}/products/{product_id}/assets/{asset_id}/select",
    response_model=ApiResponse[ProductRead],
)
async def post_product_asset_selection(
    project_id: str,
    product_id: str,
    asset_id: str,
    body: ProductAssetSelection,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProductRead]:
    product = await select_product_asset(
        db,
        project_id=project_id,
        product_id=product_id,
        asset_id=asset_id,
        selected_by=body.selected_by,
    )
    return success_response(ProductRead.model_validate(product))
