import enum
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, func
from app.database import Base


class ItemStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(String(1000), nullable=True)
    price = Column(Float, nullable=False, default=0.0)
    status = Column(Enum(ItemStatus, values_callable=lambda obj: [e.value for e in obj]), default=ItemStatus.ACTIVE, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)