"""Payment service with simulated external gateway."""

import logging
import random
import asyncio
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import sys
sys.path.append("..")
from models import Payment

from shared.db import get_db_session
from shared.config import PAYMENT_SUCCESS_RATE, PAYMENT_TIMEOUT_RATE
from shared.metrics import get_metrics_text
from shared.health import check_database, check_redis, build_health_response
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/charge", tags=["payment"])

# Payment simulation state (for demos)
_payment_simulation = {
    "always_timeout": False,
    "always_fail": False,
    "normal": True,
}


class ChargeRequest(BaseModel):
    order_id: str
    amount: Decimal
    currency: str = "USD"


class ChargeResponse(BaseModel):
    success: bool
    order_id: str
    transaction_id: Optional[str] = None
    status: str
    message: str


@router.post("", response_model=ChargeResponse)
async def charge(
    request: ChargeRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ChargeResponse:
    """
    Simulate payment processing with success/timeout/error scenarios.
    """
    try:
        # Validate order_id format
        try:
            order_uuid = UUID(request.order_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid order ID format")

        # Simulate payment outcomes (check simulation flags first)
        if _payment_simulation["always_timeout"]:
            await asyncio.sleep(2)
            raise HTTPException(
                status_code=504,
                detail="Payment gateway timeout",
            )
        
        if _payment_simulation["always_fail"]:
            raise HTTPException(
                status_code=500,
                detail="Payment gateway error",
            )

        # Normal probabilistic simulation
        if _payment_simulation["normal"]:
            outcome_rand = random.random()

            if outcome_rand < PAYMENT_TIMEOUT_RATE:
                # Simulate timeout
                await asyncio.sleep(2)
                raise HTTPException(
                    status_code=504,
                    detail="Payment gateway timeout",
                )

            elif outcome_rand < (PAYMENT_TIMEOUT_RATE + (1 - PAYMENT_SUCCESS_RATE - PAYMENT_TIMEOUT_RATE)):
                # Simulate error
                raise HTTPException(
                    status_code=500,
                    detail="Payment gateway error",
                )

        # Success path
        transaction_id = f"txn_{order_uuid.hex[:12]}"

        # Create or update payment record
        result = await db.execute(
            select(Payment).where(Payment.order_id == order_uuid)
        )
        payment = result.scalars().first()

        if payment:
            payment.status = "completed"
            payment.transaction_id = transaction_id
        else:
            payment = Payment(
                order_id=order_uuid,
                amount=request.amount,
                status="completed",
                payment_method="simulated",
                transaction_id=transaction_id,
            )
            db.add(payment)

        await db.commit()

        return ChargeResponse(
            success=True,
            order_id=request.order_id,
            transaction_id=transaction_id,
            status="completed",
            message="Payment processed successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Charge error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{order_id}", response_model=ChargeResponse)
async def get_payment_status(
    order_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> ChargeResponse:
    """Get payment status for an order."""
    try:
        try:
            order_uuid = UUID(order_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid order ID format")

        result = await db.execute(
            select(Payment).where(Payment.order_id == order_uuid)
        )
        payment = result.scalars().first()

        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        return ChargeResponse(
            success=payment.status == "completed",
            order_id=order_id,
            transaction_id=payment.transaction_id,
            status=payment.status,
            message=f"Payment status: {payment.status}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get payment status error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health", tags=["monitoring"])
async def health_check(
    db: AsyncSession = Depends(get_db_session),
    redis_client = Depends(get_redis_client),
):
    """Health check endpoint for payment service."""
    checks = {}

    # Check database
    checks["database"] = await check_database(db)

    # Check Redis
    checks["redis"] = await check_redis(redis_client)

    is_healthy, response = build_health_response(checks)
    status_code = 200 if is_healthy else 503

    return {"status_code": status_code, **response}


@router.get("/metrics", tags=["monitoring"])
async def metrics():
    """Return Prometheus metrics."""
    return get_metrics_text()


class SimulateFailureRequest(BaseModel):
    """Request to toggle failure simulation."""
    always_timeout: Optional[bool] = None
    always_fail: Optional[bool] = None
    normal: Optional[bool] = None


class SimulateFailureResponse(BaseModel):
    """Current simulation state."""
    state: dict


@router.post("/simulate-failure", tags=["hidden"], response_model=SimulateFailureResponse)
async def simulate_failure(request: SimulateFailureRequest):
    """
    Hidden route: Toggle payment failure simulation modes.
    Useful for testing retry logic and resilience.

    Examples:
    - {"always_timeout": true} - Always timeout
    - {"always_fail": true} - Always fail with 500
    - {"normal": true} - Return to random simulation
    """
    global _payment_simulation

    # Update simulation state based on request
    if request.always_timeout is not None:
        _payment_simulation["always_timeout"] = request.always_timeout
    if request.always_fail is not None:
        _payment_simulation["always_fail"] = request.always_fail
    if request.normal is not None:
        _payment_simulation["normal"] = request.normal

    return SimulateFailureResponse(state=_payment_simulation.copy())
