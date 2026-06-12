"""Redis client for caching scan results, news, and session state."""

import redis.asyncio as aioredis
from loguru import logger

from core.config import settings

_redis: aioredis.Redis | None = None


async def init_redis():
    global _redis
    _redis = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    await _redis.ping()
    logger.info("Redis connection OK")


async def close_redis():
    if _redis:
        await _redis.aclose()


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialized")
    return _redis


async def cache_set(key: str, value: str, ttl: int = 300):
    await get_redis().setex(key, ttl, value)


async def cache_get(key: str) -> str | None:
    return await get_redis().get(key)


async def cache_delete(key: str):
    await get_redis().delete(key)
