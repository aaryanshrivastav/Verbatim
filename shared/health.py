"""Health check utilities for services."""

import logging
from typing import Optional, Dict, Any

from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import httpx

from shared.config import HTTP_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class HealthCheckResult:
    """Result of a health check."""

    def __init__(self, healthy: bool, checks: Dict[str, Any]):
        self.healthy = healthy
        self.checks = checks

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return {
            "healthy": self.healthy,
            "checks": self.checks,
        }


async def check_database(db: AsyncSession, timeout: float = HTTP_TIMEOUT_SECONDS) -> Dict[str, Any]:
    """Check database connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "service": "database"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "down", "service": "database", "error": str(e)}


async def check_redis(
    redis_client: AsyncRedis, timeout: float = HTTP_TIMEOUT_SECONDS
) -> Dict[str, Any]:
    """Check Redis connectivity."""
    try:
        pong = await redis_client.ping()
        if pong:
            return {"status": "ok", "service": "redis"}
        return {"status": "down", "service": "redis"}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {"status": "down", "service": "redis", "error": str(e)}


async def check_upstream_service(
    service_name: str, service_url: str, timeout: float = HTTP_TIMEOUT_SECONDS
) -> Dict[str, Any]:
    """Check remote upstream service."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{service_url}/health")
            if response.status_code == 200:
                return {"status": "ok", "service": service_name}
            return {
                "status": "down",
                "service": service_name,
                "status_code": response.status_code,
            }
    except httpx.TimeoutException:
        logger.error(f"Upstream service {service_name} health check timeout")
        return {"status": "down", "service": service_name, "error": "timeout"}
    except Exception as e:
        logger.error(f"Upstream service {service_name} health check failed: {e}")
        return {"status": "down", "service": service_name, "error": str(e)}


def build_health_response(checks: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
    """
    Build health response from checks.
    Returns (is_healthy, response_dict).
    """
    all_ok = all(check.get("status") == "ok" for check in checks.values())
    
    response = {
        "healthy": all_ok,
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
    }
    
    return all_ok, response
