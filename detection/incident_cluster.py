"""Incident clustering: groups anomalies by endpoint and time window.

Groups related anomaly events into incidents for RCA handoff.
Does NOT diagnose; only clusters anomalies.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import uuid

from detection.models import AnomalyEvent, Incident, IncidentAnomaly

logger = logging.getLogger(__name__)


class IncidentCluster:
    """Clusters anomalies into incidents.
    
    Attributes:
        cluster_window_seconds: Time window for clustering (typically 10 seconds)
        incidents: Dict mapping incident_id -> Incident object
    """
    
    def __init__(self, cluster_window_seconds: int = 10):
        """Initialize clustering engine.
        
        Args:
            cluster_window_seconds: Time window for grouping anomalies
        """
        self.cluster_window_seconds = cluster_window_seconds
        self.incidents: Dict[str, Incident] = {}
        self.endpoint_buckets: Dict[str, List[AnomalyEvent]] = {}
    
    def add_event(self, event: AnomalyEvent) -> Optional[Incident]:
        """Process a new anomaly event and cluster it.
        
        Logic:
        - Find incidents with same endpoint within cluster_window
        - If found, join the incident
        - If not found, create new incident
        
        Args:
            event: Anomaly event to cluster
            
        Returns:
            The incident this event was added to, or None
        """
        endpoint = event.endpoint
        timestamp = event.timestamp
        
        # Find existing incident for this endpoint within time window
        existing_incident = self._find_incident_for_event(endpoint, timestamp)
        
        if existing_incident:
            # Add event to existing incident
            incident_anomaly = IncidentAnomaly(
                service=event.service,
                severity=event.severity,
                anomaly_type=event.anomaly_type,
                detected_at=event.timestamp
            )
            existing_incident.anomalies.append(incident_anomaly)
            logger.info(f"Added service {event.service} to incident {existing_incident.incident_id}")
            return existing_incident
        else:
            # Create new incident
            new_incident = self._create_incident(endpoint, event, timestamp)
            self.incidents[new_incident.incident_id] = new_incident
            logger.info(f"Created new incident {new_incident.incident_id} for endpoint {endpoint}")
            return new_incident
    
    def _find_incident_for_event(
        self,
        endpoint: str,
        timestamp: datetime
    ) -> Optional[Incident]:
        """Find an open incident for this endpoint within cluster window.
        
        Args:
            endpoint: The endpoint to search for
            timestamp: Anomaly timestamp
            
        Returns:
            Incident if found, None otherwise
        """
        cutoff = timestamp - timedelta(seconds=self.cluster_window_seconds)
        
        for incident in self.incidents.values():
            # Match endpoint
            if incident.endpoint != endpoint:
                continue
            
            # Check if timestamp is within cluster window
            if incident.time_window_start <= timestamp <= incident.time_window_end:
                return incident
            
            # Or if we're still within the window from the incident's start
            if incident.time_window_start <= timestamp:
                if timestamp <= incident.time_window_end:
                    return incident
        
        return None
    
    def _create_incident(
        self,
        endpoint: str,
        event: AnomalyEvent,
        timestamp: datetime
    ) -> Incident:
        """Create a new incident.
        
        Args:
            endpoint: The endpoint
            event: The triggering anomaly event
            timestamp: Timestamp of the event
            
        Returns:
            New Incident object
        """
        incident_id = f"inc-{uuid.uuid4().hex[:8]}"
        
        # Time window: [now, now + cluster_window]
        time_window_start = timestamp
        time_window_end = timestamp + timedelta(seconds=self.cluster_window_seconds)
        
        incident_anomaly = IncidentAnomaly(
            service=event.service,
            severity=event.severity,
            anomaly_type=event.anomaly_type,
            detected_at=event.timestamp
        )
        
        incident = Incident(
            incident_id=incident_id,
            endpoint=endpoint,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            anomalies=[incident_anomaly]
        )
        
        return incident
    
    def get_open_incidents(self) -> List[Incident]:
        """Return all currently open incidents.
        
        Returns:
            List of Incident objects
        """
        return list(self.incidents.values())
    
    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Get incident by ID.
        
        Args:
            incident_id: The incident identifier
            
        Returns:
            Incident if found, None otherwise
        """
        return self.incidents.get(incident_id)
    
    def close_old_incidents(self, now: datetime) -> List[Incident]:
        """Close incidents that have passed their time window.
        
        Args:
            now: Current timestamp
            
        Returns:
            List of closed incidents
        """
        closed = []
        to_remove = []
        
        for incident_id, incident in self.incidents.items():
            if now > incident.time_window_end:
                closed.append(incident)
                to_remove.append(incident_id)
        
        for incident_id in to_remove:
            del self.incidents[incident_id]
        
        return closed
