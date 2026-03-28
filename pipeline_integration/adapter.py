"""Incident-to-RCA adapter with full RCA pipeline integration.

Converts Detection incidents through the full RCA Modules A-G pipeline,
with fallback to conservative adapter if needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from decision_engine.models import RCAOutput
from detection.models import Incident
from pipeline_integration.rca_integration import RCAIntegration, RCAPipelineConfig

logger = logging.getLogger(__name__)


@dataclass
class IncidentAdapterConfig:
    """Configuration for RCA adapter with pipeline options."""

    use_full_rca: bool = True  # Use full RCA pipeline if True, else fallback adapter
    fallback_on_error: bool = True  # Fall back to simple adapter on RCA errors
    rca_config: Optional[RCAPipelineConfig] = None
    
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
    """Converts Detection incidents into Decision-compatible RCA payloads.

    Can use either:
    - Full RCA pipeline (Modules A-G) for comprehensive analysis
    - Fallback adapter for simple rule-based analysis when RCA is unavailable
    """

    def __init__(self, config: IncidentAdapterConfig | None = None) -> None:
        self.config = config or IncidentAdapterConfig()
        self.rca_integration: Optional[RCAIntegration] = None
        
        # Initialize RCA integration if enabled
        if self.config.use_full_rca:
            try:
                rca_config = self.config.rca_config or RCAPipelineConfig(
                    fallback_on_error=self.config.fallback_on_error
                )
                self.rca_integration = RCAIntegration(rca_config)
                logger.info("RCA integration initialized successfully")
            except Exception as e:
                if self.config.fallback_on_error:
                    logger.warning(f"Failed to initialize RCA integration: {e}. Using fallback adapter.")
                    self.rca_integration = None
                else:
                    raise

    def adapt(self, incident: Incident | Mapping[str, Any]) -> RCAOutput:
        """Return a Decision-compatible RCA payload from a Detection incident.
        
        Uses full RCA pipeline (Modules A-G) if available, otherwise falls back
        to simple fallback adapter.
        
        Args:
            incident: Detection incident (model or dict)
            
        Returns:
            RCAOutput compatible with Decision Engine
        """
        # Try full RCA pipeline first
        if self.rca_integration:
            try:
                return self.rca_integration.analyze(incident)
            except Exception as e:
                if self.config.fallback_on_error:
                    logger.warning(f"RCA analysis failed: {e}. Falling back to simple adapter.")
                else:
                    raise
        
        # Fall back to simple adapter
        logger.debug("Using fallback adapter for incident analysis")
        return self._adapt_fallback(incident)
    
    def _adapt_fallback(self, incident: Incident | Mapping[str, Any]) -> RCAOutput:
        """Fallback adapter: simple rule-based RCA when full pipeline unavailable.
        
        Picks the highest-severity anomaly as the provisional root cause and
        projects per-service severities into the fixed 6-slot state vector expected
        by the Decision Engine.
        
        Args:
            incident: Detection incident (model or dict)
            
        Returns:
            RCAOutput with fallback/conservative values
        """
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
                "detected_at": self._parse_datetime(anomaly.get("detected_at", self._parse_datetime("2026-03-28T10:00:00Z"))),
            }
            for anomaly in incident.get("anomalies", [])
        ]
        
        # Extract affected services from anomalies if not provided
        affected_services = incident.get("affected_services")
        if not affected_services:
            affected_services = list(set(anom["service"] for anom in anomalies))
        
        return {
            "incident_id": incident["incident_id"],
            "endpoint": incident["endpoint"],
            "time_window_start": self._parse_datetime(incident["time_window_start"]),
            "time_window_end": self._parse_datetime(incident["time_window_end"]),
            "affected_services": affected_services,
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
