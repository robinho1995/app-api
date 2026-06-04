from pydantic import BaseModel, Field
from datetime import datetime
from app.models import ItemStatus
from typing import Optional


class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    price: float = Field(..., ge=0)
    status: ItemStatus = ItemStatus.ACTIVE


class ItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    price: Optional[float] = Field(None, ge=0)
    status: Optional[ItemStatus] = None


class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float
    status: ItemStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ItemListResponse(BaseModel):
    items: list[ItemResponse]
    total: int
    page: int
    page_size: int