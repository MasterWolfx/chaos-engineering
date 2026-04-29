import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, init_db
from app.models import Item
from app.cache import cache_get, cache_set, cache_delete
from prometheus_fastapi_instrumentator import Instrumentator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Chaos Demo API",
    description="Backend per il progetto Chaos Engineering su Kubernetes",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)


class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float = 0.0


class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float

    model_config = {"from_attributes": True}


ITEMS_CACHE_KEY = "items:all"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/items", response_model=List[ItemResponse])
async def list_items(db: AsyncSession = Depends(get_db)):
    cached = await cache_get(ITEMS_CACHE_KEY)
    if cached is not None:
        logger.info("Cache HIT for %s", ITEMS_CACHE_KEY)
        return cached

    logger.info("Cache MISS for %s — querying DB", ITEMS_CACHE_KEY)
    result = await db.execute(select(Item).order_by(Item.id))
    items = result.scalars().all()
    data = [ItemResponse.model_validate(i).model_dump() for i in items]
    await cache_set(ITEMS_CACHE_KEY, data)
    return data


@app.post("/api/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(payload: ItemCreate, db: AsyncSession = Depends(get_db)):
    item = Item(**payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    await cache_delete(ITEMS_CACHE_KEY)
    return item


@app.get("/api/items/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)):
    key = f"items:{item_id}"
    cached = await cache_get(key)
    if cached is not None:
        return cached

    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    data = ItemResponse.model_validate(item).model_dump()
    await cache_set(key, data)
    return data


@app.delete("/api/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)
    await db.commit()
    await cache_delete(ITEMS_CACHE_KEY)
    await cache_delete(f"items:{item_id}")
