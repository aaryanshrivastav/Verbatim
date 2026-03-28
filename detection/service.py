"""Service interface for anomaly detection.

Exposes detector via HTTP API endpoints.
"""

import logging
import json
from datetime import datetime
from typing import Dict, List

from detection.config import DetectionConfig
from detection.detector import AnomalyDetector
from detection.models import AnomalyEvent, Incident

logger = logging.getLogger(__name__)


class DetectionService:
    """Service wrapper around AnomalyDetector.
    
    Attributes:
        config: DetectionConfig
        detector: AnomalyDetector instance
    """
    
    def __init__(self, config: DetectionConfig):
        """Initialize service.
        
        Args:
            config: DetectionConfig
        """
        self.config = config
        self.detector = AnomalyDetector(config)
    
    def tick(self) -> Dict:
        """Execute one detection cycle.
        
        Returns:
            Dict with results:
                {
                    "events": [event dicts],
                    "incidents": [incident dicts],
                    "warmup_remaining_seconds": int,
                    "timestamp": ISO string
                }
        """
        events, incidents = self.detector.tick()
        
        return {
            "events": [self._serialize_event(e) for e in events],
            "incidents": [self._serialize_incident(i) for i in incidents],
            "warmup_remaining_seconds": self.detector.get_warmup_remaining_seconds(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "in_warmup": self.detector.is_in_warmup()
        }
    
    def get_recent_events(self, limit: int = 100) -> List[Dict]:
        """Get recent anomaly events.
        
        Args:
            limit: Maximum number of events
            
        Returns:
            List of event dicts
        """
        events = self.detector.get_recent_events(limit)
        return [self._serialize_event(e) for e in events]
    
    def get_recent_incidents(self, limit: int = 50) -> List[Dict]:
        """Get recent incidents.
        
        Args:
            limit: Maximum number of incidents
            
        Returns:
            List of incident dicts
        """
        incidents = self.detector.get_recent_incidents(limit)
        return [self._serialize_incident(i) for i in incidents]
    
    def get_stream_state(self, service: str, endpoint: str) -> Dict:
        """Get stream state for a service.
        
        Args:
            service: Service name
            endpoint: Endpoint path
            
        Returns:
            State dict or error dict
        """
        state = self.detector.get_stream_state(service, endpoint)
        if not state:
            return {"error": f"No stream state for {service}/{endpoint}"}
        return state
    
    def get_status(self) -> Dict:
        """Get overall service status.
        
        Returns:
            Status dict
        """
        return {
            "status": "ok",
            "config": {
                "prometheus_url": self.config.prometheus_base_url,
                "latency_threshold": self.config.latency_threshold,
                "error_threshold": self.config.error_threshold,
                "severity_threshold": self.config.severity_threshold,
                "window_size": self.config.window_size,
                "warmup_seconds": self.config.warmup_seconds,
                "cluster_window_seconds": self.config.cluster_window_seconds,
                "poll_interval_seconds": self.config.poll_interval_seconds,
            },
            "warmup_remaining_seconds": self.detector.get_warmup_remaining_seconds(),
            "active_streams": len(self.detector.streams),
            "recent_events": len(self.detector.events),
            "recent_incidents": len(self.detector.incidents),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    @staticmethod
    def _serialize_event(event: AnomalyEvent) -> Dict:
        """Serialize an AnomalyEvent to dict.
        
        Args:
            event: AnomalyEvent instance
            
        Returns:
            Dict representation
        """
        return {
            "service": event.service,
            "endpoint": event.endpoint,
            "anomaly_type": event.anomaly_type,
            "severity": round(event.severity, 3),
            "timestamp": event.timestamp.isoformat() + "Z",
            "latency_score": round(event.latency_score, 3) if event.latency_score is not None else None,
            "error_score": round(event.error_score, 3) if event.error_score is not None else None
        }
    
    @staticmethod
    def _serialize_incident(incident: Incident) -> Dict:
        """Serialize an Incident to dict.
        
        Args:
            incident: Incident instance
            
        Returns:
            Dict representation
        """
        anomalies = [
            {
                "service": a.service,
                "severity": round(a.severity, 3),
                "anomaly_type": a.anomaly_type,
                "detected_at": a.detected_at.isoformat() + "Z"
            }
            for a in incident.anomalies
        ]
        
        return {
            "incident_id": incident.incident_id,
            "endpoint": incident.endpoint,
            "time_window_start": incident.time_window_start.isoformat() + "Z",
            "time_window_end": incident.time_window_end.isoformat() + "Z",
            "max_severity": round(incident.max_severity, 3),
            "affected_services": incident.affected_services,
            "anomaly_count": len(incident.anomalies),
            "anomalies": anomalies
        }
