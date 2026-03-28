"""Main anomaly detection engine.

Orchestrates metric polling, stream state management, scoring,
triggering, and incident clustering.
"""

import logging
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from detection.config import DetectionConfig
from detection.models import (
    StreamKey, StreamState, AnomalyEvent, AnomalyType, Incident
)
from detection.ring_buffer import RingBuffer
from detection.rolling_stats import RollingStats
from detection.prometheus_client import PrometheusClient
from detection.derived_metrics import DerivedMetricsComputer
from detection.scorer import AnomalyScorer
from detection.incident_cluster import IncidentCluster

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Main anomaly detection engine.
    
    Attributes:
        config: DetectionConfig
        client: PrometheusClient
        computer: DerivedMetricsComputer
        scorer: AnomalyScorer
        clusterer: IncidentCluster
        streams: Dict mapping StreamKey -> StreamState
        warmup_until: Timestamp until which warmup is active
        events: List of recent anomaly events
        incidents: List of recent incidents
    """
    
    def __init__(self, config: DetectionConfig):
        """Initialize detector.
        
        Args:
            config: DetectionConfig instance
        """
        self.config = config
        self.client = PrometheusClient(config.prometheus_base_url)
        self.computer = DerivedMetricsComputer(self.client, config)
        self.scorer = AnomalyScorer(config.z_max)
        self.clusterer = IncidentCluster(config.cluster_window_seconds)
        
        # Stream state
        self.streams: Dict[StreamKey, StreamState] = {}
        
        # Warm-up tracking
        self.start_time = time.time()
        self.warmup_until = self.start_time + config.warmup_seconds
        
        # Event log
        self.events: List[AnomalyEvent] = []
        self.incidents: List[Incident] = []
        
        logger.info("AnomalyDetector initialized with config: "
                   f"prometheus={config.prometheus_base_url}, "
                   f"window_size={config.window_size}, "
                   f"warmup_seconds={config.warmup_seconds}")
    
    def is_in_warmup(self) -> bool:
        """Check if currently in warmup period."""
        return time.time() < self.warmup_until
    
    def get_warmup_remaining_seconds(self) -> int:
        """Get seconds remaining in warmup."""
        remaining = self.warmup_until - time.time()
        return max(0, int(remaining))
    
    def tick(self) -> tuple[List[AnomalyEvent], List[Incident]]:
        """Execute one detection cycle.
        
        1. Fetch derived metrics from Prometheus
        2. Update stream buffers
        3. Compute rolling stats
        4. Score streams
        5. Check triggers
        6. Emit events (if not in warmup)
        7. Cluster events into incidents
        
        Returns:
            Tuple of (new_events, new_incidents)
        """
        now = datetime.utcnow()
        new_events = []
        new_incidents = []
        
        # Fetch all metrics
        try:
            metrics = self.computer.refresh_all()
        except Exception as e:
            logger.error(f"Failed to fetch metrics: {e}")
            return [], []
        
        # Update streams and score
        for (service, endpoint), metric_values in metrics.items():
            p95_latency = metric_values["p95_latency"]
            error_rate = metric_values["error_rate"]
            
            # Update latency stream
            latency_key = StreamKey(service, endpoint, "p95_latency")
            latency_stream = self._get_or_create_stream(latency_key)
            latency_stream.buffer.push(p95_latency)
            
            # Update stats inline
            latency_stream.rolling_mean, latency_stream.rolling_std = (
                RollingStats(latency_stream.buffer).get_stats()
            )
            
            # Compute latency score
            latency_score = self.scorer.score_stream(latency_stream)
            
            # Update error stream
            error_key = StreamKey(service, endpoint, "error_rate")
            error_stream = self._get_or_create_stream(error_key)
            error_stream.buffer.push(error_rate)
            
            # Update stats inline
            error_stream.rolling_mean, error_stream.rolling_std = (
                RollingStats(error_stream.buffer).get_stats()
            )
            
            # Compute error score
            error_score = self.scorer.score_stream(error_stream)
            
            # Compute combined severity
            severity = self.scorer.compute_severity(
                latency_score,
                error_score,
                self.config.latency_weight,
                self.config.error_weight
            )
            
            # Check trigger conditions
            latency_anomaly = latency_score >= self.config.latency_threshold
            error_anomaly = error_score >= self.config.error_threshold
            is_severe = severity >= self.config.severity_threshold
            
            should_trigger = (latency_anomaly and error_anomaly) or is_severe
            
            # Emit event if triggered (and not in warmup, and not deduplicated)
            if should_trigger and not self.is_in_warmup():
                event = self._create_event(
                    service, endpoint, latency_anomaly, error_anomaly,
                    severity, latency_score, error_score, now
                )
                
                # Deduplication check
                if self._should_emit_event(event, latency_stream, error_stream):
                    new_events.append(event)
                    self.events.append(event)
                    
                    # Cluster event into incident
                    incident = self.clusterer.add_event(event)
                    if incident and incident not in self.incidents:
                        self.incidents.append(incident)
                        new_incidents.append(incident)
                    
                    logger.info(f"Emitted anomaly event: service={service}, "
                               f"endpoint={endpoint}, severity={severity:.2f}")
        
        # Close expired incidents
        closed = self.clusterer.close_old_incidents(now)
        for incident in closed:
            logger.info(f"Closed incident {incident.incident_id}")
        
        return new_events, new_incidents
    
    def _get_or_create_stream(self, key: StreamKey) -> StreamState:
        """Get or create stream state.
        
        Args:
            key: StreamKey identifier
            
        Returns:
            StreamState for this key
        """
        if key not in self.streams:
            buffer = RingBuffer(self.config.window_size)
            self.streams[key] = StreamState(
                key=key,
                buffer=buffer,
                rolling_mean=0.0,
                rolling_std=0.0,
                is_anomalous=False
            )
        return self.streams[key]
    
    def _create_event(
        self,
        service: str,
        endpoint: str,
        latency_anomaly: bool,
        error_anomaly: bool,
        severity: float,
        latency_score: float,
        error_score: float,
        timestamp: datetime
    ) -> AnomalyEvent:
        """Create an anomaly event.
        
        Args:
            service: Service name
            endpoint: Endpoint path
            latency_anomaly: True if latency triggered
            error_anomaly: True if error rate triggered
            severity: Combined severity score
            latency_score: Raw latency score
            error_score: Raw error score
            timestamp: Event timestamp
            
        Returns:
            AnomalyEvent object
        """
        # Determine anomaly type
        if latency_anomaly and error_anomaly:
            anomaly_type = AnomalyType.MIXED
        elif latency_anomaly:
            anomaly_type = AnomalyType.LATENCY_SPIKE
        elif error_anomaly:
            anomaly_type = AnomalyType.ERROR_SPIKE
        else:
            # Should not reach here, but handle gracefully
            anomaly_type = AnomalyType.MIXED
        
        return AnomalyEvent(
            service=service,
            endpoint=endpoint,
            anomaly_type=anomaly_type,
            severity=severity,
            timestamp=timestamp,
            latency_score=latency_score,
            error_score=error_score
        )
    
    def _should_emit_event(
        self,
        event: AnomalyEvent,
        latency_stream: StreamState,
        error_stream: StreamState
    ) -> bool:
        """Check if event should be emitted.
        
        Implements deduplication: suppress repeated events
        for unchanged anomaly state.
        
        Args:
            event: The event to check
            latency_stream: Latency stream state
            error_stream: Error rate stream state
            
        Returns:
            True if event should be emitted
        """
        now = time.time()
        
        # If either stream hasn't emitted recently, allow
        if latency_stream.last_anomaly_emitted_at is None:
            latency_stream.last_anomaly_emitted_at = now
            error_stream.last_anomaly_emitted_at = now
            return True
        
        # Check cooldown
        time_since_latency = now - (latency_stream.last_anomaly_emitted_at or 0)
        time_since_error = now - (error_stream.last_anomaly_emitted_at or 0)
        
        # Emit if cooldown expired
        if time_since_latency > self.config.dedup_cooldown_seconds:
            latency_stream.last_anomaly_emitted_at = now
            return True
        if time_since_error > self.config.dedup_cooldown_seconds:
            error_stream.last_anomaly_emitted_at = now
            return True
        
        return False
    
    def get_stream_state(self, service: str, endpoint: str) -> Optional[Dict]:
        """Get current state of streams for a service/endpoint.
        
        Args:
            service: Service name
            endpoint: Endpoint path
            
        Returns:
            Dict with stream states or None
        """
        latency_key = StreamKey(service, endpoint, "p95_latency")
        error_key = StreamKey(service, endpoint, "error_rate")
        
        latency_stream = self.streams.get(latency_key)
        error_stream = self.streams.get(error_key)
        
        if not latency_stream or not error_stream:
            return None
        
        return {
            "service": service,
            "endpoint": endpoint,
            "latency_mean": latency_stream.rolling_mean,
            "latency_std": latency_stream.rolling_std,
            "error_mean": error_stream.rolling_mean,
            "error_std": error_stream.rolling_std,
            "buffer_sizes": {
                "latency": len(latency_stream.buffer),
                "error": len(error_stream.buffer)
            }
        }
    
    def get_recent_events(self, limit: int = 100) -> List[AnomalyEvent]:
        """Get recent anomaly events.
        
        Args:
            limit: Maximum number of events to return
            
        Returns:
            List of recent events
        """
        return self.events[-limit:]
    
    def get_recent_incidents(self, limit: int = 50) -> List[Incident]:
        """Get recent incidents.
        
        Args:
            limit: Maximum number of incidents to return
            
        Returns:
            List of recent incidents
        """
        return self.incidents[-limit:]
