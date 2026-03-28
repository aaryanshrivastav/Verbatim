"""RCA pipeline integration for Decision Engine.

Wraps the full RCA Modules A-G (rca.core.RCAPipeline) to produce
Decision-compatible RCAOutput payloads.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from decision_engine.models import RCAOutput as DecisionRCAOutput
from decision_engine.models import RCACandidate, RCAConfidence
from detection.models import Incident as DetectionIncident

try:
    from rca.core import RCAPipeline as RCACore
    from rca.config import RCAConfig
    from rca.models import Incident as RCAIncident
    from rca.models import AnomalyDetail
except ImportError as e:
    RCACore = None
    RCAConfig = None
    RCAIncident = None
    AnomalyDetail = None
    import_error = e


logger = logging.getLogger(__name__)


@dataclass
class RCAPipelineConfig:
    """Configuration for RCA pipeline integration."""

    jaeger_host: str = "localhost"
    jaeger_port: int = 6831
    prometheus_url: str = "http://localhost:9090"
    loki_url: str = "http://localhost:3100"
    ml_ranker_model_path: str | Path = Path("models/ml_ranker_logistic_regression.pkl")
    otel_collector_host: str = "localhost"
    otel_collector_port: int = 4317
    timeout_seconds: int = 30
    fallback_on_error: bool = True


class RCAIntegration:
    """Orchestrates RCA Modules A-G for pipeline integration.

    This class wraps rca.core.RCAPipeline and converts between Detection
    incident format and Decision-compatible RCAOutput format.
    """

    def __init__(self, config: Optional[RCAPipelineConfig] = None) -> None:
        """Initialize RCA integration.

        Args:
            config: RCAPipelineConfig with pipeline settings, or None for defaults

        Raises:
            ImportError: If RCA modules are not available
            RuntimeError: If RCA pipeline fails to initialize
        """
        self.config = config or RCAPipelineConfig()
        self.pipeline: Optional[RCACore] = None
        self._initialize_pipeline()

    def _initialize_pipeline(self) -> None:
        """Initialize the core RCA pipeline.

        Raises:
            RuntimeError: If RCA pipeline fails to initialize
        """
        if RCACore is None:
            raise ImportError("RCA modules not available. Install rca package first.")

        try:
            # RCAConfig uses environment variables for configuration
            # Set environment variables from our config before initializing
            import os
            
            os.environ.setdefault("JAEGER_BASE_URL", f"http://{self.config.jaeger_host}:{self.config.jaeger_port}")
            os.environ.setdefault("PROMETHEUS_BASE_URL", self.config.prometheus_url)
            os.environ.setdefault("LOKI_BASE_URL", self.config.loki_url)
            os.environ.setdefault("RCA_ML_MODEL_PATH", str(self.config.ml_ranker_model_path))
            
            # Initialize RCA config and pipeline
            rca_config = RCAConfig()
            self.pipeline = RCACore(rca_config)
            logger.info("RCA pipeline initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize RCA pipeline: {e}")
            raise RuntimeError(f"RCA pipeline initialization failed: {e}") from e

    def analyze(
        self, incident: DetectionIncident | Mapping[str, Any]
    ) -> DecisionRCAOutput:
        """Run RCA analysis on a Detection incident.

        Converts Detection incident → RCA Incident → Full RCA Pipeline
        → Decision-compatible RCAOutput.

        Args:
            incident: Detection incident (model or dict)

        Returns:
            RCAOutput compatible with Decision Engine

        Raises:
            ValueError: If incident is malformed
            RuntimeError: If analysis fails (unless fallback_on_error is True)
        """
        if self.pipeline is None:
            raise RuntimeError("RCA pipeline not initialized")

        try:
            # Convert Detection incident to RCA incident format
            rca_incident = self._normalize_incident(incident)

            # Run full RCA pipeline (A-G)
            logger.debug(f"Running RCA analysis for incident {rca_incident.incident_id}")
            rca_output = self.pipeline.analyze(rca_incident)

            # Convert RCA output to Decision-compatible format
            decision_output = self._convert_output(rca_output)

            logger.info(
                f"RCA analysis succeeded: incident={rca_incident.incident_id}, "
                f"root_cause={decision_output.root_cause}, "
                f"confidence={decision_output.confidence.bucket}"
            )
            return decision_output

        except Exception as e:
            logger.error(f"RCA analysis failed: {e}", exc_info=True)
            if self.config.fallback_on_error:
                logger.warning("Falling back to default RCA due to error")
                return self._create_default_output(incident)
            raise RuntimeError(f"RCA analysis failed: {e}") from e

    def _normalize_incident(
        self, incident: DetectionIncident | Mapping[str, Any]
    ) -> RCAIncident:
        """Convert Detection incident to RCA incident format.

        Args:
            incident: Detection incident or dict

        Returns:
            RCAIncident compatible with RCA pipeline
        """
        if isinstance(incident, DetectionIncident):
            anomalies = [
                AnomalyDetail(
                    service=anomaly.service,
                    severity=anomaly.severity,
                    anomaly_type=str(anomaly.anomaly_type),
                )
                for anomaly in incident.anomalies
            ]
            return RCAIncident(
                incident_id=incident.incident_id,
                endpoint=incident.endpoint,
                time_window_start=incident.time_window_start,
                time_window_end=incident.time_window_end,
                anomalies=anomalies,
            )

        # Handle dict format
        start_dt = self._parse_datetime(incident.get("time_window_start"))
        end_dt = self._parse_datetime(incident.get("time_window_end"))

        anomalies = [
            AnomalyDetail(
                service=anom["service"],
                severity=float(anom["severity"]),
                anomaly_type=anom.get("anomaly_type", "unknown"),
            )
            for anom in incident.get("anomalies", [])
        ]

        return RCAIncident(
            incident_id=incident["incident_id"],
            endpoint=incident.get("endpoint", "unknown"),
            time_window_start=start_dt,
            time_window_end=end_dt,
            anomalies=anomalies,
        )

    @staticmethod
    def _convert_output(rca_output: Any) -> DecisionRCAOutput:
        """Convert RCA pipeline output to Decision-compatible RCAOutput.

        Args:
            rca_output: Output from rca.core.RCAPipeline.analyze()

        Returns:
            DecisionRCAOutput validated for Decision Engine
        """
        # Convert top candidates
        top_candidates = [
            RCACandidate(service=c.service, probability=float(c.probability))
            for c in rca_output.top_candidates
        ]

        # Build confidence
        confidence = RCAConfidence(
            value=float(rca_output.confidence.value),
            bucket=rca_output.confidence.bucket.value
            if hasattr(rca_output.confidence.bucket, "value")
            else str(rca_output.confidence.bucket),
        )

        # Parse time window
        time_window = rca_output.time_window if rca_output.time_window else []

        # Create Decision-compatible output
        return DecisionRCAOutput(
            incident_id=rca_output.incident_id,
            endpoint=rca_output.endpoint,
            root_cause=rca_output.root_cause,
            confidence=confidence,
            top_candidates=top_candidates,
            affected_services=list(rca_output.affected_services),
            state_vector=list(rca_output.state_vector),
            original_severity=float(rca_output.original_severity),
            time_window=time_window,
            incident_started_at=None,  # Will be set in pipeline
        )

    @staticmethod
    def _create_default_output(incident: DetectionIncident | Mapping[str, Any]) -> DecisionRCAOutput:
        """Create default RCA output when analysis fails.

        Args:
            incident: Detection incident or dict

        Returns:
            Default RCAOutput with highest-severity anomaly as root cause
        """
        if isinstance(incident, DetectionIncident):
            incident_id = incident.incident_id
            endpoint = incident.endpoint
            anomalies = incident.anomalies
            start_time = incident.time_window_start
            end_time = incident.time_window_end
        else:
            incident_id = incident["incident_id"]
            endpoint = incident.get("endpoint", "unknown")
            anomalies = incident.get("anomalies", [])
            start_time = RCAIntegration._parse_datetime(incident.get("time_window_start"))
            end_time = RCAIntegration._parse_datetime(incident.get("time_window_end"))

        # Pick highest-severity anomaly as root cause
        if not anomalies:
            root_cause = "unknown"
            root_severity = 0.0
        else:
            if isinstance(anomalies[0], dict):
                max_anom = max(anomalies, key=lambda a: a.get("severity", 0))
                root_cause = max_anom["service"]
                root_severity = max_anom.get("severity", 0.5)
            else:
                max_anom = max(anomalies, key=lambda a: a.severity)
                root_cause = max_anom.service
                root_severity = max_anom.severity

        # Conservative confidence based on severity
        conf_value = min(0.6, max(0.3, root_severity))  # [0.3, 0.6]
        conf_bucket = "low" if conf_value < 0.4 else ("medium" if conf_value < 0.5 else "high")

        # Build state vector (6 slots: gateway, auth, catalog, order, payment, db)
        state_vector = [0] * 6

        # Affected services
        affected = [a["service"] if isinstance(a, dict) else a.service for a in anomalies]

        return DecisionRCAOutput(
            incident_id=incident_id,
            endpoint=endpoint,
            root_cause=root_cause,
            confidence=RCAConfidence(value=conf_value, bucket=conf_bucket),
            top_candidates=[RCACandidate(service=root_cause, probability=conf_value)],
            affected_services=affected,
            state_vector=state_vector,
            original_severity=float(root_severity),
            time_window=[start_time.isoformat(), end_time.isoformat()],
            incident_started_at=start_time,
        )

    @staticmethod
    def _parse_datetime(value: datetime | str | None) -> datetime:
        """Parse datetime from various formats.

        Args:
            value: datetime, ISO string, or None

        Returns:
            Parsed datetime with UTC timezone
        """
        if value is None:
            return datetime.now(timezone.utc)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if isinstance(value, str):
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        raise ValueError(f"Cannot parse datetime: {value}")
