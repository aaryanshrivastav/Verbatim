"""Redis client configuration and cache utilities."""

import json
import logging
from typing import Any, Optional

import redis
from redis.asyncio import Redis as AsyncRedis

from shared.config import REDIS_URL, REDIS_CACHE_TTL

logger = logging.getLogger(__name__)

_redis_client: Optional[AsyncRedis] = None


async def init_redis() -> AsyncRedis:
    """Initialize and return Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


async def get_redis_client() -> AsyncRedis:
    """Dependency for FastAPI to inject Redis client."""
    return await init_redis()


async def cache_get(key: str, redis_client: AsyncRedis) -> Optional[Any]:
    """Get value from cache."""
    try:
        value = await redis_client.get(key)
        if value:
            return json.loads(value)
    except Exception as e:
        logger.warning(f"Cache get failed for key {key}: {e}")
    return None


async def cache_set(
    key: str, value: Any, redis_client: AsyncRedis, ttl: int = REDIS_CACHE_TTL
) -> bool:
    """Set value in cache with TTL."""
    try:
        await redis_client.setex(key, ttl, json.dumps(value))
        return True
    except Exception as e:
        logger.warning(f"Cache set failed for key {key}: {e}")
        return False


async def cache_delete(key: str, redis_client: AsyncRedis) -> bool:
    """Delete key from cache."""
    try:
        await redis_client.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Cache delete failed for key {key}: {e}")
        return False
