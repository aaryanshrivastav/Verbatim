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
    compose_project: str = "verbatim",
) -> ServiceCatalog:
    """Build a default catalog from the current repository compose layout.

    Since container_name was removed from the 5 app services to enable
    ``docker compose up --scale``, dynamic names use the Compose convention:
    ``<project>-<service>-<replica>``, e.g. ``verbatim-catalog-1``.
    """
    scalable_set: Set[str] = set(scalable_services or [
        "auth", "catalog", "order", "payment", "gateway",
    ])

    def _cname(service: str) -> str:
        """Return the Compose auto-generated container name for replica 1."""
        return f"{compose_project}-{service}-1"

    targets = {
        "postgres": ServiceTarget("postgres", "postgres", "postgres", False, True),
        "redis": ServiceTarget("redis", "redis", "redis", False, True),
        "auth": ServiceTarget("auth", _cname("auth"), "auth", True, False),
        "catalog": ServiceTarget("catalog", _cname("catalog"), "catalog", True, False),
        "order": ServiceTarget("order", _cname("order"), "order", True, False),
        "payment": ServiceTarget("payment", _cname("payment"), "payment", True, False),
        "gateway": ServiceTarget("gateway", _cname("gateway"), "gateway", True, False),
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
        "checkout": "order",
        "checkoutservice": "order",
        "payment-service": "payment",
        "paymentservice": "payment",
        "gateway-service": "gateway",
        "main-app": "main",
        "microservices-demo": "main",
        "orderservice": "order",
        "cartservice": "redis",
        "redis-cart": "redis",
        "orders-db": "postgres",
    }
    return ServiceCatalog(targets=targets, aliases=aliases)
