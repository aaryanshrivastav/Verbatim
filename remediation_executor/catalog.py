"""Service-to-runtime mapping for the Remediation Executor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Set


@dataclass(frozen=True)
class ServiceTarget:
    """Resolved runtime information for a service."""

    canonical_name: str
    container_name: str
    compose_service_name: str
    scalable: bool = False
    is_db: bool = False


class ServiceCatalog:
    """Maps incoming service names to container and compose identifiers."""

    def __init__(
        self,
        targets: Dict[str, ServiceTarget],
        aliases: Optional[Dict[str, str]] = None,
    ) -> None:
        self.targets = targets
        self.aliases = aliases or {}

    def resolve(self, service_name: str) -> ServiceTarget:
        """Resolve a service alias into a concrete runtime target."""
        canonical_name = self.aliases.get(service_name, service_name)
        if canonical_name not in self.targets:
            raise KeyError(f"unknown service mapping: {service_name}")
        return self.targets[canonical_name]


def build_default_catalog(
    compose_file: str | Path = "docker-compose.yml",
    scalable_services: Optional[Iterable[str]] = None,
) -> ServiceCatalog:
    """Build a default catalog from the current repository compose layout."""
    scalable_set: Set[str] = set(scalable_services or [])
    targets = {
        "postgres": ServiceTarget("postgres", "postgres", "postgres", False, True),
        "redis": ServiceTarget("redis", "redis", "redis", False, True),
        "auth": ServiceTarget("auth", "auth-service", "auth", "auth" in scalable_set, False),
        "catalog": ServiceTarget("catalog", "catalog-service", "catalog", "catalog" in scalable_set, False),
        "order": ServiceTarget("order", "order-service", "order", "order" in scalable_set, False),
        "payment": ServiceTarget("payment", "payment-service", "payment", "payment" in scalable_set, False),
        "gateway": ServiceTarget("gateway", "gateway-service", "gateway", "gateway" in scalable_set, False),
        "main": ServiceTarget("main", "main-app", "main", "main" in scalable_set, False),
        "otel-collector": ServiceTarget("otel-collector", "otel-collector", "otel-collector", False, False),
        "prometheus": ServiceTarget("prometheus", "prometheus", "prometheus", False, False),
        "jaeger": ServiceTarget("jaeger", "jaeger", "jaeger", False, False),
        "loki": ServiceTarget("loki", "loki", "loki", False, False),
        "promtail": ServiceTarget("promtail", "promtail", "promtail", False, False),
        "grafana": ServiceTarget("grafana", "grafana", "grafana", False, False),
    }
    aliases = {
        "auth-service": "auth",
        "catalog-service": "catalog",
        "order-service": "order",
        "payment-service": "payment",
        "gateway-service": "gateway",
        "main-app": "main",
        "microservices-demo": "main",
        "paymentservice": "payment",
        "checkoutservice": "order",
        "orderservice": "order",
        "cartservice": "redis",
        "redis-cart": "redis",
        "orders-db": "postgres",
    }
    return ServiceCatalog(targets=targets, aliases=aliases)
