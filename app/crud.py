from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Item, ItemStatus
from app.schemas import ItemCreate, ItemUpdate
from typing import Optional


async def get_items(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: Optional[ItemStatus] = None,
) -> tuple[list[Item], int]:
    query = select(Item)
    count_query = select(func.count(Item.id))

    if status:
        query = query.where(Item.status == status)
        count_query = count_query.where(Item.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size).order_by(Item.id)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def get_item(db: AsyncSession, item_id: int) -> Optional[Item]:
    result = await db.execute(select(Item).where(Item.id == item_id))
    return result.scalar_one_or_none()


async def create_item(db: AsyncSession, item_data: ItemCreate) -> Item:
    item = Item(**item_data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def update_item(db: AsyncSession, item: Item, item_data: ItemUpdate) -> Item:
    update_data = item_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return item


async def delete_item(db: AsyncSession, item: Item) -> None:
    await db.delete(item)
    await db.commit()