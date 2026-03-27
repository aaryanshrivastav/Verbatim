"""Order/Cart service with inter-service calls and retry logic."""

import logging
import asyncio
import random
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx

import sys
sys.path.append("..")
from models import Order, OrderItem, User, Product

from shared.db import get_db_session
from shared.metrics import get_metrics_text
from shared.health import check_database, check_redis, check_upstream_service, build_health_response
from shared.redis_client import get_redis_client
from shared.config import (
    PAYMENT_SERVICE_URL,
    CATALOG_SERVICE_URL,
    ENABLE_RETRY_STORM,
    MAX_RETRIES,
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
    HTTP_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orders", tags=["orders"])


class OrderItemRequest(BaseModel):
    product_id: str
    quantity: int


class CreateOrderRequest(BaseModel):
    user_id: str
    items: List[OrderItemRequest]


class OrderItemResponse(BaseModel):
    id: str
    product_id: str
    quantity: int
    unit_price: str


class OrderResponse(BaseModel):
    id: str
    user_id: str
    total_amount: str
    status: str
    items: List[OrderItemResponse]


async def exponential_backoff(attempt: int) -> float:
    """Calculate exponential backoff with jitter."""
    backoff = min(
        INITIAL_BACKOFF_SECONDS * (2 ** attempt),
        MAX_BACKOFF_SECONDS,
    )
    jitter = random.uniform(0, backoff * 0.1)
    return backoff + jitter


async def call_payment_service(
    order_id: str, amount: Decimal
) -> bool:
    """
    Call payment service with retry logic (if enabled).
    Returns True if successful, False otherwise.
    """
    retries = 0
    max_attempts = MAX_RETRIES if ENABLE_RETRY_STORM else 1

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        while retries < max_attempts:
            try:
                response = await client.post(
                    f"{PAYMENT_SERVICE_URL}/charge",
                    json={
                        "order_id": order_id,
                        "amount": str(amount),
                        "currency": "USD",
                    },
                )

                if response.status_code == 200:
                    return True

                if response.status_code in (500, 504) and retries < max_attempts - 1:
                    backoff = await exponential_backoff(retries)
                    logger.warning(
                        f"Payment call failed with {response.status_code}, "
                        f"retrying in {backoff:.2f}s (attempt {retries + 1}/{max_attempts})"
                    )
                    await asyncio.sleep(backoff)
                    retries += 1
                    continue

                return False

            except httpx.TimeoutException:
                if retries < max_attempts - 1:
                    backoff = await exponential_backoff(retries)
                    logger.warning(
                        f"Payment call timeout, retrying in {backoff:.2f}s "
                        f"(attempt {retries + 1}/{max_attempts})"
                    )
                    await asyncio.sleep(backoff)
                    retries += 1
                    continue
                return False

            except Exception as e:
                logger.error(f"Payment call error: {e}")
                return False

    return False


@router.post("", response_model=OrderResponse, status_code=201)
async def create_order(
    request: CreateOrderRequest,
    db: AsyncSession = Depends(get_db_session),
) -> OrderResponse:
    """
    Create an order with items.
    Validates user, checks product stock, calls payment service.
    """
    try:
        # Validate user
        try:
            user_uuid = UUID(request.user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format")

        result = await db.execute(select(User).where(User.id == user_uuid))
        user = result.scalars().first()

        if not user:
            raise HTTPException(status_code=400, detail="User not found")

        # Validate and collect items
        order_items_data = []
        total_amount = Decimal("0")

        for item_req in request.items:
            try:
                product_uuid = UUID(item_req.product_id)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid product ID: {item_req.product_id}")

            result = await db.execute(select(Product).where(Product.id == product_uuid))
            product = result.scalars().first()

            if not product:
                raise HTTPException(status_code=400, detail=f"Product not found: {item_req.product_id}")

            if product.stock_quantity < item_req.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock for product {product.name}",
                )

            item_total = product.price * Decimal(item_req.quantity)
            total_amount += item_total

            order_items_data.append(
                {
                    "product_id": product_uuid,
                    "quantity": item_req.quantity,
                    "unit_price": product.price,
                    "product": product,
                }
            )

        # Create order
        order = Order(
            user_id=user_uuid,
            total_amount=total_amount,
            status="pending",
        )
        db.add(order)
        await db.flush()  # Get order.id without committing

        # Create order items
        order_items = []
        for item_data in order_items_data:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item_data["product_id"],
                quantity=item_data["quantity"],
                unit_price=item_data["unit_price"],
            )
            db.add(order_item)
            order_items.append(order_item)

        await db.flush()

        # Call payment service
        payment_success = await call_payment_service(str(order.id), total_amount)

        # Update order status based on payment
        if payment_success:
            order.status = "confirmed"
        else:
            order.status = "payment_failed"

        await db.commit()

        # Build response
        items_response = [
            OrderItemResponse(
                id=str(oi.id),
                product_id=str(oi.product_id),
                quantity=oi.quantity,
                unit_price=str(oi.unit_price),
            )
            for oi in order_items
        ]

        return OrderResponse(
            id=str(order.id),
            user_id=str(order.user_id),
            total_amount=str(order.total_amount),
            status=order.status,
            items=items_response,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create order error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Define specific routes BEFORE generic path parameter routes
@router.get("/health", tags=["monitoring"])
async def health_check(
    db: AsyncSession = Depends(get_db_session),
    redis_client = Depends(get_redis_client),
):
    """Health check endpoint for order service."""
    checks = {}

    # Check database
    checks["database"] = await check_database(db)

    # Check Redis
    checks["redis"] = await check_redis(redis_client)

    # Check payment service
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


@router.get("/retry-config", tags=["hidden"])
async def retry_config():
    """
    Hidden route: Return current retry configuration.
    Useful for retry-storm demo documentation.
    """
    return {
        "retry_enabled": ENABLE_RETRY_STORM,
        "max_retries": MAX_RETRIES,
        "initial_backoff_seconds": INITIAL_BACKOFF_SECONDS,
        "max_backoff_seconds": MAX_BACKOFF_SECONDS,
        "http_timeout_seconds": HTTP_TIMEOUT_SECONDS,
    }


# Generic path parameter route AFTER specific routes
@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> OrderResponse:
    """Get order details including items."""
    try:
        try:
            order_uuid = UUID(order_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid order ID format")

        result = await db.execute(select(Order).where(Order.id == order_uuid))
        order = result.scalars().first()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Fetch order items
        result = await db.execute(
            select(OrderItem).where(OrderItem.order_id == order_uuid)
        )
        order_items = result.scalars().all()

        items_response = [
            OrderItemResponse(
                id=str(oi.id),
                product_id=str(oi.product_id),
                quantity=oi.quantity,
                unit_price=str(oi.unit_price),
            )
            for oi in order_items
        ]

        return OrderResponse(
            id=str(order.id),
            user_id=str(order.user_id),
            total_amount=str(order.total_amount),
            status=order.status,
            items=items_response,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get order error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
