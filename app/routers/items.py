from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app import crud, schemas
from app.models import ItemStatus
from typing import Optional

router = APIRouter(prefix="/api/v1/items", tags=["items"])


@router.get("", response_model=schemas.ItemListResponse)
async def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[ItemStatus] = None,
    db: AsyncSession = Depends(get_db),
):
    items, total = await crud.get_items(db, page=page, page_size=page_size, status=status)
    return schemas.ItemListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/{item_id}", response_model=schemas.ItemResponse)
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await crud.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.post("", response_model=schemas.ItemResponse, status_code=201)
async def create_item(item_data: schemas.ItemCreate, db: AsyncSession = Depends(get_db)):
    return await crud.create_item(db, item_data)


@router.delete("/{item_id}", status_code=204)
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await crud.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await crud.delete_item(db, item)