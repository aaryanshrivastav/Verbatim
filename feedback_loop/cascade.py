"""Cascade RCA-lite support for Component 6."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

from decision_engine.models import RCAOutput
from feedback_loop.models import FeedbackRequest
from feedback_loop.stores import SeverityProvider


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CascadeConfig:
    """Configuration for RCA-lite cascade emission."""

    state_slots: Sequence[str] = (
        "frontend",
        "gateway",
        "auth",
        "checkout",
        "payment",
        "db",
    )
    service_aliases: Dict[str, str] = field(
        default_factory=lambda: {
            "frontend": "frontend",
            "frontend-service": "frontend",
            "gateway-service": "gateway",
            "gateway": "gateway",
            "main-app": "gateway",
            "microservices-demo": "gateway",
            "auth-service": "auth",
            "auth": "auth",
            "checkout": "checkout",
            "checkoutservice": "checkout",
            "catalog-service": "checkout",
            "catalog": "checkout",
            "order-service": "checkout",
            "order": "checkout",
            "orderservice": "checkout",
            "payment-service": "payment",
            "payment": "payment",
            "paymentservice": "payment",
            "postgres": "db",
            "redis": "db",
            "orders-db": "db",
            "db": "db",
        }
    )
    secondary_threshold: float = 0.5
    confidence_value: float = 0.6


class CascadeBuilder:
    """Builds Decision-compatible RCA payloads for secondary cascades."""

    def __init__(self, config: Optional[CascadeConfig] = None) -> None:
        self.config = config or CascadeConfig()

    def build(self, request: FeedbackRequest, severity_provider: SeverityProvider) -> Optional[RCAOutput]:
        """Return a cascade RCA payload when a secondary service is still degraded."""
        root_service = request.execution_log.service
        candidates = []
        for service in request.affected_services:
            if service == root_service:
                continue
            severity = severity_provider.severity_for(service, request.endpoint)
            if severity >= self.config.secondary_threshold:
                candidates.append((service, severity))

        if not candidates:
            return None

        secondary_service, severity = max(candidates, key=lambda item: item[1])
        now = _utc_now()
        return RCAOutput.model_validate(
            {
                "incident_id": f"{request.execution_log.incident_id}-cascade",
                "endpoint": request.endpoint,
                "root_cause": secondary_service,
                "confidence": {
                    "value": self.config.confidence_value,
                    "bucket": "medium",
                },
                "top_candidates": [
                    {
                        "service": secondary_service,
                        "probability": self.config.confidence_value,
                    }
                ],
                "affected_services": [],
                "state_vector": severity_provider.state_vector(
                    self.config.state_slots,
                    self.config.service_aliases,
                ),
                "original_severity": severity,
                "time_window": [now.isoformat(), now.isoformat()],
                "incident_started_at": now,
            }
        )
