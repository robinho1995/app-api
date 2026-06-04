from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, check_db_connection

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    db_ok = await check_db_connection()
    if not db_ok:
        return JSONResponse(status_code=503, content={"status": "not ready", "database": "unavailable"})
    return {"status": "ready", "database": "connected"}