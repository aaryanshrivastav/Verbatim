"""Detection -> RCA adapter for native Component 3 outputs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from detection.models import Incident as DetectionIncident
from rca.config import RCAConfig
from rca.core import RCAPipeline
from rca.F_state_vector import StateVectorBuilder
from rca.models import AnomalyDetail, CandidatePrediction, Confidence, ConfidenceBucket, Evidence, Incident, RCAOutput

logger = logging.getLogger(__name__)


@dataclass
class DetectionRCAAdapterConfig:
    """Configuration for the native Detection -> RCA bridge."""

    jaeger_base_url: str = "http://localhost:16686"
    prometheus_base_url: str = "http://localhost:9090"
    loki_base_url: str = "http://localhost:3100"
    ml_model_path: str | Path = Path("models") / "ml_ranker_logistic_regression.pkl"
    fallback_on_error: bool = True


class DetectionRCAAdapter:
    """Converts Detection incidents into native RCA pipeline results."""

    def __init__(
        self,
        config: Optional[DetectionRCAAdapterConfig] = None,
        pipeline: Optional[RCAPipeline] = None,
    ) -> None:
        self.config = config or DetectionRCAAdapterConfig()
        self.rca_config = RCAConfig()
        self.rca_config.jaeger_base_url = self.config.jaeger_base_url
        self.rca_config.prometheus_base_url = self.config.prometheus_base_url
        self.rca_config.loki_base_url = self.config.loki_base_url
        self.rca_config.ml_model_path = str(self.config.ml_model_path)
        self.pipeline = pipeline or RCAPipeline(self.rca_config)
        self.state_builder = StateVectorBuilder(self.rca_config)

    def analyze(self, incident: DetectionIncident | Mapping[str, Any]) -> RCAOutput:
        """Analyze one Detection incident and return a native RCAOutput."""
        normalized = self._normalize_incident(incident)
        try:
            return self.pipeline.analyze(normalized)
        except Exception as exc:
            logger.error("Detection -> RCA analysis failed: %s", exc, exc_info=True)
            if not self.config.fallback_on_error:
                raise
            return self._fallback_output(normalized)

    def _normalize_incident(self, incident: DetectionIncident | Mapping[str, Any]) -> Incident:
        if isinstance(incident, DetectionIncident):
            anomalies = [
                AnomalyDetail(
                    service=anomaly.service,
                    severity=float(anomaly.severity),
                    anomaly_type=str(anomaly.anomaly_type),
                )
                for anomaly in incident.anomalies
            ]
            return Incident(
                incident_id=incident.incident_id,
                endpoint=incident.endpoint,
                time_window_start=incident.time_window_start,
                time_window_end=incident.time_window_end,
                anomalies=anomalies,
            )

        anomalies = [
            AnomalyDetail(
                service=str(anomaly["service"]),
                severity=float(anomaly["severity"]),
                anomaly_type=str(anomaly.get("anomaly_type", "unknown")),
            )
            for anomaly in incident.get("anomalies", [])
        ]
        return Incident(
            incident_id=str(incident["incident_id"]),
            endpoint=str(incident["endpoint"]),
            time_window_start=self._parse_datetime(incident["time_window_start"]),
            time_window_end=self._parse_datetime(incident["time_window_end"]),
            anomalies=anomalies,
        )

    def _fallback_output(self, incident: Incident) -> RCAOutput:
        anomalies = sorted(incident.anomalies, key=lambda anomaly: anomaly.severity, reverse=True)
        if not anomalies:
            raise ValueError("incident contains no anomalies")

        root = anomalies[0]
        second = anomalies[1].severity if len(anomalies) > 1 else 0.0
        confidence_value = max(0.0, min(1.0, root.severity - second))
        if confidence_value >= self.rca_config.confidence_high_threshold:
            bucket = ConfidenceBucket.HIGH
        elif confidence_value >= self.rca_config.confidence_medium_threshold:
            bucket = ConfidenceBucket.MEDIUM
        else:
            bucket = ConfidenceBucket.LOW

        return RCAOutput(
            incident_id=incident.incident_id,
            endpoint=incident.endpoint,
            root_cause=root.service,
            confidence=Confidence(value=confidence_value, bucket=bucket),
            top_candidates=[
                CandidatePrediction(service=anomaly.service, probability=float(anomaly.severity))
                for anomaly in anomalies[:3]
            ],
            affected_services=[anomaly.service for anomaly in incident.anomalies],
            state_vector=self.state_builder.build_state_vector(incident),
            original_severity=float(root.severity),
            time_window=[
                incident.time_window_start.isoformat(),
                incident.time_window_end.isoformat(),
            ],
            evidence=Evidence(),
        )

    @staticmethod
    def _parse_datetime(value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
