"""Module B: Candidate Extractor.

Filters high-probability root cause candidates based on thresholds.
"""

import logging
from typing import List

from rca.models import Incident, TraceMetrics, Candidate, FeatureVector
from rca.config import RCAConfig

logger = logging.getLogger(__name__)


class CandidateExtractor:
    """Extracts candidate root cause services."""
    
    def __init__(self, config: RCAConfig):
        """Initialize extractor.
        
        Args:
            config: RCAConfig instance
        """
        self.config = config
    
    def extract_candidates(
        self,
        incident: Incident,
        trace_metrics: dict[str, TraceMetrics]
    ) -> List[Candidate]:
        """Extract candidate root cause services.
        
        A service is a candidate if:
        - appears_in_traces >= trace_coverage_threshold AND
        - (suspicious_span_ratio >= suspicious_ratio_threshold OR
             metrics_severity >= metrics_severity_threshold)
        
        Args:
            incident: Incident object
            trace_metrics: Dict from TraceGraphBuilder
            
        Returns:
            List of Candidate objects
        """
        candidates = []
        severity_by_service = {
            self.config.normalize_service_name(anomaly.service): float(anomaly.severity)
            for anomaly in incident.anomalies
        }
        
        for service, trace_metric in trace_metrics.items():
            # Get metrics severity from incident
            metrics_severity = severity_by_service.get(
                self.config.normalize_service_name(service),
                0.0,
            )
            
            # Check trace coverage threshold
            if trace_metric.appears_in_traces < self.config.trace_coverage_threshold:
                logger.debug(
                    f"Rejecting {service}: trace_coverage "
                    f"{trace_metric.appears_in_traces} < "
                    f"{self.config.trace_coverage_threshold}"
                )
                continue
            
            # Check suspicious ratio OR metrics severity
            has_suspicious_traces = (
                trace_metric.suspicious_span_ratio >= 
                self.config.suspicious_ratio_threshold
            )
            has_severe_metrics = (
                metrics_severity >= self.config.metrics_severity_threshold
            )
            
            if not (has_suspicious_traces or has_severe_metrics):
                logger.debug(
                    f"Rejecting {service}: no suspicious traces and metrics "
                    f"not severe ({metrics_severity} < "
                    f"{self.config.metrics_severity_threshold})"
                )
                continue
            
            # This is a candidate
            logger.info(f"Extracted candidate: {service}")
            
            # Build feature vector (will be completed by FeatureBuilder)
            feature_vector = FeatureVector(
                service=service,
                m=metrics_severity,
                t=trace_metric.suspicious_span_ratio,
                c=trace_metric.appears_in_traces,
                depth=0,  # Will be set by FeatureBuilder
                is_db=0,  # Will be set by FeatureBuilder
                is_edge=0  # Will be set by FeatureBuilder
            )
            
            candidate = Candidate(
                service=service,
                trace_metrics=trace_metric,
                feature_vector=feature_vector
            )
            candidates.append(candidate)
        
        return candidates
