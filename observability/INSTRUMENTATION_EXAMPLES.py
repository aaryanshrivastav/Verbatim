"""
OpenTelemetry Integration Examples for Microservices

This file contains example patterns for instrumenting FastAPI routes with
OpenTelemetry for comprehensive observability.
"""

# ============================================================================
# EXAMPLE 1: Instrumenting a simple GET endpoint with metrics
# ============================================================================

"""
from fastapi import APIRouter, Depends
from shared.telemetry import tracer, meter
from shared.otel_metrics import get_metrics
import time

router = APIRouter(prefix="/products", tags=["catalog"])
metrics = get_metrics()

@router.get("/{product_id}")
async def get_product(product_id: str, db = Depends(get_db_session)):
    # Create a span for this endpoint
    with tracer.start_as_current_span("get_product") as span:
        span.set_attribute("product.id", product_id)
        
        start_time = time.time()
        try:
            # Simulate database query
            result = await db.execute(select(Product).where(Product.id == product_id))
            product = result.scalars().first()
            duration = time.time() - start_time
            
            # Record metrics
            metrics.record_request_count("GET", "/products/{product_id}", 200)
            metrics.record_request_duration("GET", "/products/{product_id}", duration)
            metrics.record_db_query_duration("select", duration)
            
            if product:
                span.set_attribute("product.found", True)
                return product
            else:
                span.set_attribute("product.found", False)
                metrics.record_request_count("GET", "/products/{product_id}", 404)
                return {"error": "Product not found"}
                
        except Exception as e:
            duration = time.time() - start_time
            span.record_exception(e)
            span.set_attribute("error", True)
            metrics.record_error("GET", "/products/{product_id}", type(e).__name__)
            metrics.record_db_query_error("select", type(e).__name__)
            raise
"""

# ============================================================================
# EXAMPLE 2: Instrumenting external HTTP calls with trace propagation
# ============================================================================

"""
import httpx
import time
from opentelemetry import trace

async def call_payment_service(order_id: str, amount: float):
    with tracer.start_as_current_span("call_payment_service") as span:
        span.set_attribute("service", "payment")
        span.set_attribute("order.id", order_id)
        span.set_attribute("amount", amount)
        
        start_time = time.time()
        
        try:
            # httpx automatically propagates trace context via headers
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://payment-service:8003/charge",
                    json={"order_id": order_id, "amount": str(amount)},
                    timeout=10.0,
                )
            
            duration = time.time() - start_time
            span.set_attribute("http.status_code", response.status_code)
            
            metrics.record_external_call_duration("payment", duration)
            
            if response.status_code != 200:
                metrics.record_external_call_error("payment", f"http_{response.status_code}")
            
            return response.status_code == 200
            
        except httpx.TimeoutException as e:
            duration = time.time() - start_time
            span.record_exception(e)
            span.set_attribute("error", True)
            span.set_attribute("error.type", "timeout")
            metrics.record_external_call_error("payment", "timeout")
            return False
            
        except Exception as e:
            duration = time.time() - start_time
            span.record_exception(e)
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(e).__name__)
            metrics.record_external_call_error("payment", type(e).__name__)
            raise
"""

# ============================================================================
# EXAMPLE 3: JSON logging with structured logs (NO trace_id in logs)
# ============================================================================

"""
import structlog
import json
from datetime import datetime

logger = structlog.get_logger()

# Simple structured log
def log_request_error(service: str, endpoint: str, error_msg: str, latency_ms: int):
    logger.error(
        "request_failed",
        event_type="http_error",
        service=service,
        endpoint=endpoint,
        error=error_msg,
        latency_ms=latency_ms,
        timestamp=datetime.utcnow().isoformat(),
    )

# Example log output (JSON):
# {
#   "timestamp": "2024-01-28T15:30:45.123456",
#   "service": "payment-service",
#   "level": "ERROR",
#   "message": "request_failed",
#   "event_type": "http_error",
#   "endpoint": "/charge",
#   "error": "Database connection timeout",
#   "latency_ms": 5000
# }

def log_external_dependency_failure(
    service: str,
    dependency: str,
    failure_mode: str,
    latency_ms: int,
    retry_attempt: int = 0,
):
    logger.warn(
        "external_call_failed",
        event_type="dependency_failure",
        service=service,
        dependency=dependency,
        failure_mode=failure_mode,
        latency_ms=latency_ms,
        retry_attempt=retry_attempt,
        timestamp=datetime.utcnow().isoformat(),
    )

# Example log output (JSON):
# {
#   "timestamp": "2024-01-28T15:30:45.654321",
#   "service": "order-service",
#   "level": "WARN",
#   "message": "external_call_failed",
#   "event_type": "dependency_failure",
#   "dependency": "payment-service",
#   "failure_mode": "timeout",
#   "latency_ms": 10000,
#   "retry_attempt": 1
# }
"""

# ============================================================================
# EXAMPLE 4: Monitoring cache operations
# ============================================================================

"""
async def get_product_from_cache_or_db(product_id: str):
    with tracer.start_as_current_span("get_product_cached") as span:
        # Try cache first
        cache_key = f"product:{product_id}"
        cached = await redis_client.get(cache_key)
        
        if cached:
            span.add_event("cache_hit")
            metrics.record_cache_hit()
            return json.loads(cached)
        
        span.add_event("cache_miss")
        metrics.record_cache_miss()
        
        # Fall back to database
        with tracer.start_as_current_span("db_query") as db_span:
            start_time = time.time()
            result = await db.execute(select(Product).where(Product.id == product_id))
            product = result.scalars().first()
            duration = time.time() - start_time
            
            metrics.record_db_query_duration("select", duration)
            
            if product:
                await redis_client.setex(cache_key, 3600, json.dumps(product.to_dict()))
            
            return product
"""

# ============================================================================
# EXAMPLE 5: AUTH SERVICE - Tracking authentication failures
# ============================================================================

"""
@router.post("/login")
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db_session)):
    with tracer.start_as_current_span("login") as span:
        span.set_attribute("username", request.username)
        
        # Query user
        result = await db.execute(select(User).where(User.username == request.username))
        user = result.scalars().first()
        
        if not user:
            metrics.record_auth_failure("user_not_found")
            logger.warn(
                "login_failed",
                event_type="auth_failure",
                reason="user_not_found",
                username=request.username,
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        if not verify_password(request.password, user.password):
            metrics.record_auth_failure("invalid_password")
            logger.warn(
                "login_failed",
                event_type="auth_failure",
                reason="invalid_password",
                username=request.username,
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Create token
        token = create_access_token(user)
        span.set_attribute("user.id", str(user.id))
        logger.info(
            "login_successful",
            event_type="auth_success",
            username=request.username,
            user_id=str(user.id),
        )
        return {"access_token": token}
"""

# ============================================================================
# EXAMPLE 6: PAYMENT SERVICE - Tracking payment processing
# ============================================================================

"""
@router.post("/charge")
async def process_payment(request: ChargeRequest):
    with tracer.start_as_current_span("process_payment") as span:
        span.set_attribute("order.id", request.order_id)
        span.set_attribute("amount", float(request.amount))
        
        start_time = time.time()
        
        try:
            if random.random() < PAYMENT_SUCCESS_RATE:
                duration = time.time() - start_time
                metrics.record_request_duration("POST", "/charge", duration)
                logger.info(
                    "payment_processed",
                    event_type="payment_success",
                    order_id=request.order_id,
                    amount=float(request.amount),
                    latency_ms=int(duration * 1000),
                )
                return {"status": "success", "order_id": request.order_id}
            else:
                # Simulate payment failure
                metrics.record_payment_failure("insufficient_funds")
                logger.warn(
                    "payment_failed",
                    event_type="payment_failure",
                    order_id=request.order_id,
                    amount=float(request.amount),
                    reason="insufficient_funds",
                )
                return {"status": "failed", "order_id": request.order_id}
                
        except Exception as e:
            duration = time.time() - start_time
            span.record_exception(e)
            metrics.record_error("POST", "/charge", type(e).__name__)
            logger.error(
                "payment_error",
                event_type="payment_error",
                order_id=request.order_id,
                error=str(e),
                latency_ms=int(duration * 1000),
            )
            raise HTTPException(status_code=500, detail="Payment processing error")
"""
