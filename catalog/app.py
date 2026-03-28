"""Catalog service with Redis caching."""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis as AsyncRedis

import sys
sys.path.append("..")
from models import Product

from shared.db import get_db_session
from shared.redis_client import get_redis_client, cache_get, cache_set, cache_delete
from shared.config import REDIS_CACHE_TTL
from shared.metrics import get_metrics_text
from shared.health import check_database, check_redis, build_health_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["catalog"])


class ProductResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    price: str
    stock_quantity: int

    class Config:
        from_attributes = True


@router.get("", response_model=List[ProductResponse])
async def list_products(
    db: AsyncSession = Depends(get_db_session),
    redis_client: AsyncRedis = Depends(get_redis_client),
) -> List[ProductResponse]:
    """
    List all products. Each product tries Redis cache first.
    """
    try:
        result = await db.execute(select(Product))
        products = result.scalars().all()

        response = []
        for product in products:
            cache_key = f"product:{product.id}"
            
            # Try cache first
            cached = await cache_get(cache_key, redis_client)
            if cached:
                response.append(ProductResponse(**cached))
                continue

            # Cache miss - serialize and cache
            product_dict = {
                "id": str(product.id),
                "name": product.name,
                "description": product.description,
                "price": str(product.price),
                "stock_quantity": product.stock_quantity,
            }
            await cache_set(cache_key, product_dict, redis_client, REDIS_CACHE_TTL)
            response.append(ProductResponse(**product_dict))

        return response

    except Exception as e:
        logger.error(f"List products error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    db: AsyncSession = Depends(get_db_session),
    redis_client: AsyncRedis = Depends(get_redis_client),
) -> ProductResponse:
    """
    Get single product. Try Redis cache first, fall back to DB.
    """
    try:
        cache_key = f"product:{product_id}"

        # Try cache
        cached = await cache_get(cache_key, redis_client)
        if cached:
            return ProductResponse(**cached)

        # Cache miss - fetch from DB
        try:
            uuid_id = UUID(product_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid product ID format")

        result = await db.execute(select(Product).where(Product.id == uuid_id))
        product = result.scalars().first()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        product_dict = {
            "id": str(product.id),
            "name": product.name,
            "description": product.description,
            "price": str(product.price),
            "stock_quantity": product.stock_quantity,
        }

        # Cache the result
        await cache_set(cache_key, product_dict, redis_client, REDIS_CACHE_TTL)

        return ProductResponse(**product_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get product error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health", tags=["monitoring"])
async def health_check(
    db: AsyncSession = Depends(get_db_session),
    redis_client: AsyncRedis = Depends(get_redis_client),
):
    """Health check endpoint for catalog service."""
    checks = {}

    # Check database
    checks["database"] = await check_database(db)

    # Check Redis
    checks["redis"] = await check_redis(redis_client)

    is_healthy, response = build_health_response(checks)
    status_code = 200 if is_healthy else 503

    return JSONResponse(content=response, status_code=status_code)


@router.get("/metrics", tags=["monitoring"])
async def metrics():
    """Return Prometheus metrics."""
    return get_metrics_text()


@router.get("/cache-status/{key}", tags=["hidden"])
async def cache_status(
    key: str,
    redis_client: AsyncRedis = Depends(get_redis_client),
):
    """
    Hidden route: Check cache status for a product key.
    Useful for cache inconsistency demos.
    """
    try:
        exists = await redis_client.exists(key)
        ttl = None
        
        if exists:
            ttl = await redis_client.ttl(key)
            if ttl == -1:
                ttl = None  # No expiration set

        return {
            "key": key,
            "exists": bool(exists),
            "ttl_seconds": ttl,
        }

    except Exception as e:
        logger.error(f"Cache status error: {e}")
        raise HTTPException(status_code=500, detail="Error checking cache status")
