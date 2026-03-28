"""Provider abstractions for baselines and service severity snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Mapping, Optional, Protocol, Sequence

from feedback_loop.models import BaselineRecord


def _severity_to_state(severity: float) -> int:
    if severity >= 0.8:
        return 2
    if severity >= 0.3:
        return 1
    return 0


class BaselineProvider(Protocol):
    """Provides recovery baselines for one service/endpoint."""

    def get_baseline(self, service: str, endpoint: Optional[str] = None) -> BaselineRecord:
        """Return a baseline record for the requested service."""


class SeverityProvider(Protocol):
    """Provides current severities and derived RL state vectors."""

    def severity_for(self, service: str, endpoint: Optional[str] = None) -> float:
        """Return current severity for the service."""

    def state_vector(
        self,
        slots: Sequence[str],
        aliases: Mapping[str, str],
    ) -> list[int]:
        """Return the discrete post-remediation state vector."""


class DictBaselineProvider:
    """Baseline provider backed by an in-memory mapping."""

    def __init__(
        self,
        records: Optional[Mapping[object, Mapping[str, object]]] = None,
        default_error_rate: float = 0.05,
        default_p95_latency_ms: float = 500.0,
    ) -> None:
        self.records = dict(records or {})
        self.default_error_rate = default_error_rate
        self.default_p95_latency_ms = default_p95_latency_ms

    def get_baseline(self, service: str, endpoint: Optional[str] = None) -> BaselineRecord:
        keys = []
        if endpoint is not None:
            keys.append((service, endpoint))
            keys.append(f"{service}|{endpoint}")
        keys.append(service)

        for key in keys:
            payload = self.records.get(key)
            if payload is None:
                continue
            return BaselineRecord(
                service=service,
                endpoint=endpoint,
                error_rate_baseline=float(payload.get("error_rate_baseline", self.default_error_rate)),
                p95_latency_baseline_ms=float(payload.get("p95_latency_baseline_ms", self.default_p95_latency_ms)),
                source=str(payload.get("source", "dict")),
                used_default=bool(payload.get("used_default", False)),
            )

        return BaselineRecord(
            service=service,
            endpoint=endpoint,
            error_rate_baseline=self.default_error_rate,
            p95_latency_baseline_ms=self.default_p95_latency_ms,
            source="default",
            used_default=True,
        )


class FileBaselineProvider(DictBaselineProvider):
    """Baseline provider backed by a JSON file."""

    def __init__(
        self,
        path: str | Path,
        default_error_rate: float = 0.05,
        default_p95_latency_ms: float = 500.0,
    ) -> None:
        self.path = Path(path)
        records = self._load_records()
        super().__init__(records, default_error_rate, default_p95_latency_ms)

    def _load_records(self) -> Dict[object, Mapping[str, object]]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        records: Dict[object, Mapping[str, object]] = {}
        if isinstance(payload, dict):
            for key, value in payload.items():
                if "|" in key:
                    service, endpoint = key.split("|", 1)
                    records[(service, endpoint)] = value
                else:
                    records[key] = value
        return records


class DictSeverityProvider:
    """Severity provider backed by an in-memory mapping."""

    def __init__(self, severities: Optional[Mapping[object, float]] = None) -> None:
        self.severities = dict(severities or {})

    def severity_for(self, service: str, endpoint: Optional[str] = None) -> float:
        if endpoint is not None and (service, endpoint) in self.severities:
            return float(self.severities[(service, endpoint)])
        if service in self.severities:
            return float(self.severities[service])
        return 0.0

    def state_vector(
        self,
        slots: Sequence[str],
        aliases: Mapping[str, str],
    ) -> list[int]:
        max_per_slot = {slot: 0.0 for slot in slots}
        for key, severity in self.severities.items():
            service = key[0] if isinstance(key, tuple) else key
            slot = aliases.get(str(service))
            if slot is None or slot not in max_per_slot:
                continue
            max_per_slot[slot] = max(max_per_slot[slot], float(severity))
        return [_severity_to_state(max_per_slot[slot]) for slot in slots]


class FileSeverityProvider(DictSeverityProvider):
    """Severity provider backed by a JSON file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        severities = self._load_severities()
        super().__init__(severities)

    def _load_severities(self) -> Dict[object, float]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        severities: Dict[object, float] = {}
        if isinstance(payload, dict):
            for key, value in payload.items():
                if "|" in key:
                    service, endpoint = key.split("|", 1)
                    severities[(service, endpoint)] = float(value)
                else:
                    severities[key] = float(value)
        return severities
