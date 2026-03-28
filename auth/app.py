"""Authentication service."""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Assume models are imported from the models.py we created earlier
import sys
sys.path.append("..")
from models import User, Session as SessionModel, ENABLE_SESSIONS

from shared.db import get_db_session
from shared.metrics import get_metrics_text
from shared.otel_metrics import try_get_metrics
from shared.health import check_database, check_redis, build_health_response
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class ValidateRequest(BaseModel):
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: str


class ValidateResponse(BaseModel):
    valid: bool
    user_id: Optional[str] = None
    message: str


def hash_password(password: str) -> str:
    """Simple password hashing (in production, use bcrypt or argon2)."""
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash."""
    return hash_password(password) == hashed


def generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)


@router.post("/validate", response_model=ValidateResponse, status_code=200)
async def validate_auth(
    request: ValidateRequest, db: AsyncSession = Depends(get_db_session)
) -> ValidateResponse:
    """
    Validate authentication via token or username/password.
    Returns 200 with valid=true/false.
    """
    try:
        if request.token:
            # Validate token against sessions table
            if not ENABLE_SESSIONS:
                return ValidateResponse(valid=False, message="Sessions not enabled")

            result = await db.execute(
                select(SessionModel).where(SessionModel.token == request.token)
            )
            session = result.scalars().first()

            if not session:
                metrics = try_get_metrics()
                if metrics is not None:
                    metrics.record_auth_failure("token_not_found")
                return ValidateResponse(valid=False, message="Token not found")
                
            if session.expires_at < datetime.utcnow():
                metrics = try_get_metrics()
                if metrics is not None:
                    metrics.record_auth_failure("token_expired")
                return ValidateResponse(valid=False, message="Token expired")

            return ValidateResponse(valid=True, user_id=str(session.user_id), message="Token valid")

        elif request.username and request.password:
            # Validate username/password
            result = await db.execute(select(User).where(User.username == request.username))
            user = result.scalars().first()

            if not user:
                metrics = try_get_metrics()
                if metrics is not None:
                    metrics.record_auth_failure("invalid_username")
                return ValidateResponse(valid=False, message="Invalid credentials")

            if verify_password(request.password, user.password):
                return ValidateResponse(valid=True, user_id=str(user.id), message="Credentials valid")

            metrics = try_get_metrics()
            if metrics is not None:
                metrics.record_auth_failure("invalid_password")
            return ValidateResponse(valid=False, message="Invalid credentials")

        else:
            return ValidateResponse(valid=False, message="No token or credentials provided")

    except Exception as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/login", response_model=AuthResponse, status_code=200)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db_session)) -> AuthResponse:
    """
    Login with username and password.
    Returns a token for authenticated requests.
    """
    try:
        result = await db.execute(select(User).where(User.username == request.username))
        user = result.scalars().first()

        if not user:
            metrics = try_get_metrics()
            if metrics is not None:
                metrics.record_auth_failure("user_not_found")
            raise HTTPException(status_code=401, detail="User not found")

        # Verify password
        if not verify_password(request.password, user.password):
            metrics = try_get_metrics()
            if metrics is not None:
                metrics.record_auth_failure("invalid_password")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Create session if enabled
        token = generate_token()
        if ENABLE_SESSIONS:
            expires_at = datetime.utcnow() + timedelta(hours=24)
            session = SessionModel(
                user_id=user.id,
                token=token,
                expires_at=expires_at,
            )
            db.add(session)
            await db.commit()
        else:
            # Even if sessions disabled, still return a token
            pass

        return AuthResponse(token=token, user_id=str(user.id))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health", tags=["monitoring"])
async def health_check(
    db: AsyncSession = Depends(get_db_session),
    redis_client = Depends(get_redis_client),
):
    """Health check endpoint for auth service."""
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
