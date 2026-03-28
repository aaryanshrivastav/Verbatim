"""Main anomaly detector orchestrator.

Per tick: fetch metrics, score, check triggers, emit events.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

from .config import DetectionConfig
from .models import (
    StreamKey,
    AnomalyEvent,
    AnomalyType,
    StreamState,
)
from .ring_buffer import RingBuffer
from .rolling_stats import RollingStats
from .prometheus_client import PrometheusClient
from .derived_metrics import DerivedMetricsAggregator
from .scorer import AnomalyScorer


log = logging.getLogger(__name__)


class AnomalyDetector:
    """Main anomaly detection engine."""
    
    def __init__(self, config: DetectionConfig):
        """Initialize detector.
        
        Args:
            config: DetectionConfig instance.
        """
        config.validate()
        self.config = config
        
        self.prometheus_client = PrometheusClient(config.prometheus_base_url)
        self.metrics_aggregator = DerivedMetricsAggregator(self.prometheus_client)
        self.scorer = AnomalyScorer(z_max=config.z_max)
        
        # Per-stream state: service/endpoint → buffers and stats
        self.streams: Dict[StreamKey, StreamState] = {}
        
        # Emitted events (for testing/inspection)
        self.events: List[AnomalyEvent] = []
        
        # Warm-up end time
        self.warmup_until = datetime.utcnow() + timedelta(seconds=config.warmup_seconds)
        
        log.info(f"AnomalyDetector initialized (warmup until {self.warmup_until})")
    
    def is_in_warmup(self) -> bool:
        """Check if detector is still in warm-up period."""
        return datetime.utcnow() < self.warmup_until
    
    def get_warmup_remaining_seconds(self) -> int:
        """Get remaining warm-up time in seconds."""
        remaining = (self.warmup_until - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))
    
    def _ensure_stream_exists(self, service: str, endpoint: str) -> StreamKey:
        """Ensure a StreamState exists for the given service/endpoint.
        
        Creates it if it doesn't exist.
        
        Args:
            service: Service name.
            endpoint: Endpoint path.
            
        Returns:
            StreamKey for this service/endpoint.
        """
        key_latency = StreamKey(service, endpoint, "latency")
        key_error = StreamKey(service, endpoint, "error")
        
        if key_latency not in self.streams:
            self.streams[key_latency] = StreamState(
                key=key_latency,
                buffer_latency=RingBuffer(self.config.window_size),
                buffer_error=RingBuffer(self.config.window_size),
            )
            log.debug(f"Created stream state for {service} / {endpoint}")
        
        return key_latency
    
    def tick(self) -> List[AnomalyEvent]:
        """Execute one detection cycle.
        
        Returns:
            List of AnomalyEvent objects emitted in this tick.
        """
        tick_events = []
        now = datetime.utcnow()
        
        # Fetch derived metrics for all services/endpoints
        derived_metrics_list = self.metrics_aggregator.compute_for_all_services()
        
        for metrics in derived_metrics_list:
            key = self._ensure_stream_exists(metrics.service, metrics.endpoint)
            stream = self.streams[key]
            
            # Update buffers with new values
            stream.buffer_latency.push(metrics.p95_latency)
            stream.buffer_error.push(metrics.error_rate)
            
            # Compute rolling stats
            stats_latency = RollingStats(stream.buffer_latency)
            stats_error = RollingStats(stream.buffer_error)
            
            stream.mean_latency = stats_latency.mean()
            stream.std_latency = stats_latency.std()
            stream.mean_error = stats_error.mean()
            stream.std_error = stats_error.std()
            
            # Skip scoring and triggering during warm-up
            if self.is_in_warmup():
                log.debug(
                    f"Warmup period: {self.get_warmup_remaining_seconds()}s remaining"
                )
                continue
            
            # Score current values
            latency_score, error_score, severity = self.scorer.score_stream(
                current_latency=metrics.p95_latency,
                mean_latency=stream.mean_latency,
                std_latency=stream.std_latency,
                current_error=metrics.error_rate,
                mean_error=stream.mean_error,
                std_error=stream.std_error,
            )
            
            # Check trigger conditions
            latency_anomaly = latency_score >= self.config.latency_threshold
            error_anomaly = error_score >= self.config.error_threshold
            severity_severe = severity >= self.config.severity_threshold
            
            should_emit = (latency_anomaly and error_anomaly) or severity_severe
            
            # Apply deduplication cooldown
            if should_emit and stream.should_emit_duplicate_check(now):
                event = self._create_event(
                    service=metrics.service,
                    endpoint=metrics.endpoint,
                    latency_anomaly=latency_anomaly,
                    error_anomaly=error_anomaly,
                    severity=severity,
                    latency_score=latency_score,
                    error_score=error_score,
                    timestamp=now,
                )
                
                tick_events.append(event)
                self.events.append(event)
                stream.last_event_time = now
                
                log.warning(
                    f"ANOMALY: {metrics.service} / {metrics.endpoint} "
                    f"severity={severity:.2f} type={event.anomaly_type.value}"
                )
        
        return tick_events
    
    def _create_event(
        self,
        service: str,
        endpoint: str,
        latency_anomaly: bool,
        error_anomaly: bool,
        severity: float,
        latency_score: float,
        error_score: float,
        timestamp: datetime,
    ) -> AnomalyEvent:
        """Create an AnomalyEvent with appropriate type classification.
        
        Args:
            service: Service name.
            endpoint: Endpoint path.
            latency_anomaly: Whether latency is anomalous.
            error_anomaly: Whether error rate is anomalous.
            severity: Combined severity score.
            latency_score: Normalized latency score.
            error_score: Normalized error score.
            timestamp: Event timestamp.
            
        Returns:
            AnomalyEvent with classified anomaly type.
        """
        if latency_anomaly and error_anomaly:
            anomaly_type = AnomalyType.MIXED
        elif latency_anomaly:
            anomaly_type = AnomalyType.LATENCY_SPIKE
        elif error_anomaly:
            anomaly_type = AnomalyType.ERROR_SPIKE
        else:
            # Fallback for severity-only trigger
            anomaly_type = AnomalyType.MIXED
        
        return AnomalyEvent(
            service=service,
            endpoint=endpoint,
            anomaly_type=anomaly_type,
            severity=severity,
            timestamp=timestamp,
            latency_score=latency_score,
            error_score=error_score,
        )
