"""API Gateway - proxies requests to microservices."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import httpx

from shared.config import (
    AUTH_SERVICE_URL,
    CATALOG_SERVICE_URL,
    ORDER_SERVICE_URL,
    PAYMENT_SERVICE_URL,
    HTTP_TIMEOUT_SECONDS,
)
from shared.metrics import get_metrics_text
from shared.health import check_upstream_service, build_health_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["gateway"])


class ProxyError(Exception):
    """Custom exception for proxy errors."""
    pass


async def proxy_request(
    method: str,
    service_url: str,
    path: str,
    json_data: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Generic proxy for forwarding requests to microservices.
    """
    url = f"{service_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            if method == "GET":
                response = await client.get(url)
            elif method == "POST":
                response = await client.post(url, json=json_data)
            else:
                raise ProxyError(f"Unsupported method: {method}")

            if response.status_code >= 500:
                logger.error(f"Upstream error: {url} returned {response.status_code}")
                raise ProxyError(f"Upstream service error: {response.status_code}")

            return response.json()

    except httpx.TimeoutException:
        logger.error(f"Timeout calling {url}")
        raise ProxyError("Upstream service timeout")

    except httpx.RequestError as e:
        logger.error(f"Request error to {url}: {e}")
        raise ProxyError("Upstream service unavailable")

    except ProxyError:
        raise

    except Exception as e:
        logger.error(f"Unexpected error proxying to {url}: {e}")
        raise ProxyError("Gateway error")


@router.get("/products")
async def list_products() -> Dict[str, Any]:
    """Proxy GET /products to catalog service."""
    try:
        result = await proxy_request("GET", CATALOG_SERVICE_URL, "/products")
        return {"data": result}
    except ProxyError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/products/{product_id}")
async def get_product(product_id: str) -> Dict[str, Any]:
    """Proxy GET /products/{id} to catalog service."""
    try:
        result = await proxy_request("GET", CATALOG_SERVICE_URL, f"/products/{product_id}")
        return {"data": result}
    except ProxyError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/auth/validate")
async def validate_auth(credentials: Dict[str, Any]) -> Dict[str, Any]:
    """Proxy POST /auth/validate to auth service."""
    try:
        result = await proxy_request(
            "POST", AUTH_SERVICE_URL, "/auth/validate", credentials
        )
        return {"data": result}
    except ProxyError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/auth/login")
async def login(credentials: Dict[str, Any]) -> Dict[str, Any]:
    """Proxy POST /auth/login to auth service."""
    try:
        result = await proxy_request(
            "POST", AUTH_SERVICE_URL, "/auth/login", credentials
        )
        return {"data": result}
    except ProxyError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/orders")
async def create_order(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """Proxy POST /orders to order service."""
    try:
        result = await proxy_request(
            "POST", ORDER_SERVICE_URL, "/orders", order_data
        )
        return {"data": result}
    except ProxyError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/orders/{order_id}")
async def get_order(order_id: str) -> Dict[str, Any]:
    """Proxy GET /orders/{id} to order service."""
    try:
        result = await proxy_request(
            "GET", ORDER_SERVICE_URL, f"/orders/{order_id}"
        )
        return {"data": result}
    except ProxyError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/charge")
async def charge(payment_data: Dict[str, Any]) -> Dict[str, Any]:
    """Proxy POST /charge to payment service."""
    try:
        result = await proxy_request(
            "POST", PAYMENT_SERVICE_URL, "/charge", payment_data
        )
        return {"data": result}
    except ProxyError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/health", tags=["monitoring"])
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for API gateway.
    Checks all downstream services.
    """
    checks = {}

    # Check all downstream services
    checks["auth_service"] = await check_upstream_service(
        "auth", AUTH_SERVICE_URL
    )
    checks["catalog_service"] = await check_upstream_service(
        "catalog", CATALOG_SERVICE_URL
    )
    checks["order_service"] = await check_upstream_service(
        "order", ORDER_SERVICE_URL
    )
    checks["payment_service"] = await check_upstream_service(
        "payment", PAYMENT_SERVICE_URL
    )

    is_healthy, response = build_health_response(checks)
    status_code = 200 if is_healthy else 503

    return {"status_code": status_code, **response}


@router.get("/metrics", tags=["monitoring"])
async def metrics():
    """Return Prometheus metrics."""
    return get_metrics_text()
