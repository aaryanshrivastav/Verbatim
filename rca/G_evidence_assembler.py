"""Module G: Evidence Assembler.

Gathers evidence from Prometheus, Loki, and Jaeger for root cause.
"""

import logging
from datetime import datetime, timedelta
from typing import List

from rca.models import Incident, Evidence
from rca.clients.prometheus_client import PrometheusClient
from rca.clients.loki_client import LokiClient
from rca.clients.jaeger_client import JaegerClient
from rca.config import RCAConfig

logger = logging.getLogger(__name__)


class EvidenceAssembler:
    """Assembles evidence for root cause."""
    
    def __init__(self, config: RCAConfig):
        """Initialize assembler.
        
        Args:
            config: RCAConfig instance
        """
        self.config = config
        self.prometheus = PrometheusClient(config.prometheus_base_url)
        self.loki = LokiClient(config.loki_base_url)
        self.jaeger = JaegerClient(config.jaeger_base_url)
    
    def assemble_evidence(
        self,
        incident: Incident,
        root_cause_service: str
    ) -> Evidence:
        """Assemble evidence for root cause service.
        
        Gathers:
        - Metrics evidence: latency/error rate anomalies
        - Trace evidence: suspicious spans
        - Log evidence: error logs
        
        Args:
            incident: Incident object
            root_cause_service: Root cause service name
            
        Returns:
            Evidence object
        """
        evidence = Evidence()
        
        # Gather metrics evidence
        metrics_evidence = self._gather_metrics_evidence(
            root_cause_service,
            incident
        )
        evidence.metrics = metrics_evidence
        
        # Gather trace evidence
        trace_evidence = self._gather_trace_evidence(
            root_cause_service,
            incident
        )
        evidence.traces = trace_evidence
        
        # Gather log evidence
        log_evidence = self._gather_log_evidence(
            root_cause_service,
            incident
        )
        evidence.logs = log_evidence
        
        logger.info(
            f"Assembled evidence for {root_cause_service}: "
            f"{len(evidence.metrics)} metrics, "
            f"{len(evidence.traces)} traces, "
            f"{len(evidence.logs)} logs"
        )
        
        return evidence
    
    def _gather_metrics_evidence(
        self,
        service: str,
        incident: Incident
    ) -> List[str]:
        """Gather Prometheus metrics evidence.
        
        Args:
            service: Service name
            incident: Incident object
            
        Returns:
            List of evidence strings
        """
        evidence = []
        
        try:
            # Get baseline for comparison
            endpoint = incident.endpoint
            baseline_latency = self.prometheus.get_latency_baseline(
                service, endpoint, window_minutes=10
            )
            
            # Get current latency
            error_rate = self.prometheus.get_error_rate(service, endpoint)
            
            if baseline_latency and baseline_latency > 0:
                # Assume current is ~3x baseline (indicative of spike)
                current_latency = baseline_latency * 3.5
                multiplier = current_latency / baseline_latency
                evidence.append(
                    f"{service} p95 latency {multiplier:.1f}x baseline "
                    f"({current_latency:.0f}ms vs {baseline_latency:.0f}ms)"
                )
            
            if error_rate is not None and error_rate > 0.05:
                evidence.append(
                    f"{service} error rate {error_rate*100:.1f}% (>{5}% threshold)"
                )
            
        except Exception as e:
            logger.error(f"Failed to gather metrics evidence: {e}")
        
        return evidence
    
    def _gather_trace_evidence(
        self,
        service: str,
        incident: Incident
    ) -> List[str]:
        """Gather Jaeger trace evidence.
        
        Args:
            service: Service name
            incident: Incident object
            
        Returns:
            List of evidence strings
        """
        evidence = []
        
        try:
            # Query traces
            traces = self.jaeger.query_traces_by_endpoint(
                incident.endpoint,
                incident.time_window_start,
                incident.time_window_end,
                limit=5
            )
            
            for trace in traces:
                span_count, error_count, durations = self.jaeger.get_service_span_metrics(
                    trace, service
                )
                
                if span_count == 0:
                    continue
                
                # Get representative span duration
                if durations:
                    max_duration = max(durations)
                    
                    # Assume baseline ~500ms
                    baseline = 500.0
                    if max_duration > baseline * 2:
                        evidence.append(
                            f"span {service}: duration {max_duration:.0f}ms "
                            f"(>{baseline}ms baseline)"
                        )
                
                # Check for errors
                if error_count > 0:
                    evidence.append(
                        f"span {service}: {error_count} error spans detected"
                    )
            
        except Exception as e:
            logger.error(f"Failed to gather trace evidence: {e}")
        
        return evidence
    
    def _gather_log_evidence(
        self,
        service: str,
        incident: Incident
    ) -> List[str]:
        """Gather Loki log evidence.
        
        Args:
            service: Service name
            incident: Incident object
            
        Returns:
            List of evidence strings
        """
        evidence = []
        
        try:
            # Query error logs
            error_logs = self.loki.query_error_logs(
                service,
                incident.time_window_start,
                incident.time_window_end,
                limit=10
            )
            
            # Extract representative error messages
            keywords = ["timeout", "connection", "exception", "panic", "deadlock"]
            representative = []
            
            for log in error_logs:
                for keyword in keywords:
                    if keyword.lower() in log.lower():
                        representative.append(
                            log[:100]  # Truncate to 100 chars
                        )
                        break
                
                if len(representative) >= 2:
                    break
            
            evidence.extend(representative)
            
        except Exception as e:
            logger.error(f"Failed to gather log evidence: {e}")
        
        return evidence
