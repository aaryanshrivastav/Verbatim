"""Temporary incident-to-RCA adapter until the full RCA component lands."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from decision_engine.models import RCAOutput
from detection.models import Incident


@dataclass
class IncidentAdapterConfig:
    """Configuration for deriving a Decision-compatible RCA payload."""

    state_slots: Sequence[str] = (
        "gateway",
        "auth",
        "catalog",
        "order",
        "payment",
        "db",
    )
    service_aliases: Dict[str, str] = field(
        default_factory=lambda: {
            "gateway-service": "gateway",
            "gateway": "gateway",
            "auth-service": "auth",
            "auth": "auth",
            "catalog-service": "catalog",
            "catalog": "catalog",
            "order-service": "order",
            "order": "order",
            "checkoutservice": "order",
            "payment-service": "payment",
            "payment": "payment",
            "postgres": "db",
            "redis": "db",
            "orders-db": "db",
            "db": "db",
        }
    )


class DetectionIncidentAdapter:
    """Converts Detection incidents into a conservative RCA-compatible payload.

    This is intentionally a compatibility shim, not a real RCA implementation.
    It picks the highest-severity anomaly as the provisional root cause and
    projects per-service severities into the fixed 6-slot state vector expected
    by the Decision Engine.
    """

    def __init__(self, config: IncidentAdapterConfig | None = None) -> None:
        self.config = config or IncidentAdapterConfig()

    def adapt(self, incident: Incident | Mapping[str, Any]) -> RCAOutput:
        """Return a Decision-compatible RCA payload from a Detection incident."""
        normalized = self._normalize_incident(incident)
        anomalies = sorted(
            normalized["anomalies"],
            key=lambda anomaly: anomaly["severity"],
            reverse=True,
        )
        if not anomalies:
            raise ValueError("incident contains no anomalies")

        root = anomalies[0]
        confidence_value = self._estimate_confidence(anomalies)
        return RCAOutput.model_validate(
            {
                "incident_id": normalized["incident_id"],
                "endpoint": normalized["endpoint"],
                "root_cause": root["service"],
                "confidence": {
                    "value": confidence_value,
                    "bucket": self._bucket(confidence_value),
                },
                "affected_services": normalized["affected_services"],
                "state_vector": self._build_state_vector(anomalies),
                "original_severity": root["severity"],
                "time_window": [
                    normalized["time_window_start"].isoformat(),
                    normalized["time_window_end"].isoformat(),
                ],
                "incident_started_at": normalized["time_window_start"],
            }
        )

    def _normalize_incident(self, incident: Incident | Mapping[str, Any]) -> Dict[str, Any]:
        """Normalize model or dict inputs into one internal structure."""
        if isinstance(incident, Incident):
            anomalies = [
                {
                    "service": anomaly.service,
                    "severity": anomaly.severity,
                    "anomaly_type": str(anomaly.anomaly_type),
                    "detected_at": anomaly.detected_at,
                }
                for anomaly in incident.anomalies
            ]
            return {
                "incident_id": incident.incident_id,
                "endpoint": incident.endpoint,
                "time_window_start": incident.time_window_start,
                "time_window_end": incident.time_window_end,
                "affected_services": incident.affected_services,
                "anomalies": anomalies,
            }

        anomalies = [
            {
                "service": anomaly["service"],
                "severity": float(anomaly["severity"]),
                "anomaly_type": str(anomaly["anomaly_type"]),
                "detected_at": self._parse_datetime(anomaly["detected_at"]),
            }
            for anomaly in incident.get("anomalies", [])
        ]
        return {
            "incident_id": incident["incident_id"],
            "endpoint": incident["endpoint"],
            "time_window_start": self._parse_datetime(incident["time_window_start"]),
            "time_window_end": self._parse_datetime(incident["time_window_end"]),
            "affected_services": list(incident.get("affected_services", [])),
            "anomalies": anomalies,
        }

    def _build_state_vector(self, anomalies: Iterable[Dict[str, Any]]) -> List[int]:
        """Project service severities into the 6 fixed RL slots."""
        max_per_slot = {slot: 0.0 for slot in self.config.state_slots}
        for anomaly in anomalies:
            slot = self.config.service_aliases.get(anomaly["service"])
            if slot is None or slot not in max_per_slot:
                continue
            max_per_slot[slot] = max(max_per_slot[slot], float(anomaly["severity"]))
        return [self._severity_to_state(max_per_slot[slot]) for slot in self.config.state_slots]

    @staticmethod
    def _severity_to_state(severity: float) -> int:
        """Map severity into the discrete RL state encoding."""
        if severity >= 0.8:
            return 2
        if severity >= 0.3:
            return 1
        return 0

    @staticmethod
    def _estimate_confidence(anomalies: Sequence[Dict[str, Any]]) -> float:
        """Estimate conservative confidence from severity separation.

        Because real RCA is not implemented yet, we keep this intentionally
        conservative and tie it to the gap between the strongest and second
        strongest anomaly.
        """
        top = float(anomalies[0]["severity"])
        second = float(anomalies[1]["severity"]) if len(anomalies) > 1 else 0.0
        gap = max(0.0, top - second)
        return min(0.85, max(0.4, 0.45 + gap))

    @staticmethod
    def _bucket(confidence_value: float) -> str:
        """Bucket confidence using the same thresholds as the Decision Engine."""
        if confidence_value >= 0.7:
            return "high"
        if confidence_value >= 0.4:
            return "medium"
        return "low"

    @staticmethod
    def _parse_datetime(value: datetime | str) -> datetime:
        """Parse either a datetime or an ISO string with optional trailing Z."""
        if isinstance(value, datetime):
            return value
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
