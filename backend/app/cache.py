import os
import json
import logging
from typing import Optional
import redis.asyncio as aioredis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
CACHE_TTL = 30

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None

async def get_redis() -> Optional[aioredis.Redis]:
    global _redis
    if _redis is None:
        try:
            _redis = aioredis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_timeout=1.0,
                socket_connect_timeout=1.0
            )
            await _redis.ping()
        except Exception as exc:
            logger.warning("Redis unavailable: %s — cache disabled", exc)
            _redis = None
    return _redis

async def cache_get(key: str) -> Optional[dict]:
    global _redis
    r = await get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("Cache GET failed for %s: %s", key, exc)
        _redis = None
        return None

async def cache_set(key: str, value: dict, ttl: int = CACHE_TTL) -> None:
    global _redis
    r = await get_redis()
    if r is None:
        return
    try:
        await r.setex(key, ttl, json.dumps(value))
    except Exception as exc:
        logger.warning("Cache SET failed for %s: %s", key, exc)
        _redis = None

async def cache_delete(key: str) -> None:
    global _redis
    r = await get_redis()
    if r is None:
        return
    try:
        await r.delete(key)
    except Exception as exc:
        logger.warning("Cache DEL failed for %s: %s", key, exc)
        _redis = None
