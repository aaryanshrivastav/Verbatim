"""Incident clustering: group anomalies by endpoint and time window."""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging
import uuid

from .models import AnomalyEvent, Incident


log = logging.getLogger(__name__)


class IncidentCluster:
    """Groups anomaly events into incidents by endpoint and time window."""
    
    def __init__(self, cluster_window_seconds: int = 10):
        """Initialize incident clusterer.
        
        Args:
            cluster_window_seconds: Time window for grouping anomalies (seconds).
        """
        self.cluster_window_seconds = cluster_window_seconds
        
        # Active incidents: (endpoint, time_window_start) → Incident
        self.incidents: Dict[tuple, Incident] = {}
    
    def add_event(self, event: AnomalyEvent) -> Optional[Incident]:
        """Add an anomaly event to the appropriate incident.
        
        If an incident already exists for this endpoint within the time window,
        add event to it. Otherwise, create a new incident.
        
        Args:
            event: AnomalyEvent to cluster.
            
        Returns:
            The Incident object that received the event.
        """
        now = event.timestamp
        
        # Find or create incident for this endpoint
        best_incident = None
        best_distance = float("inf")
        
        for (endpoint, window_start), incident in list(self.incidents.items()):
            if incident.endpoint != event.endpoint:
                continue
            
            # Check if event is within the window
            window_end = window_start + timedelta(seconds=self.cluster_window_seconds)
            
            if window_start <= now <= window_end:
                # Event fits in this window, use it
                best_incident = incident
                break
            
            # Track closest window for potential expansion
            distance_to_window = min(
                abs((now - window_start).total_seconds()),
                abs((now - window_end).total_seconds()),
            )
            if distance_to_window < best_distance:
                best_distance = distance_to_window
                best_incident = incident
        
        if best_incident is None:
            # Create new incident
            incident = Incident(
                incident_id=f"inc-{uuid.uuid4().hex[:8]}",
                endpoint=event.endpoint,
                time_window_start=now,
                time_window_end=now + timedelta(seconds=self.cluster_window_seconds),
            )
            key = (event.endpoint, now)
            self.incidents[key] = incident
            best_incident = incident
            log.info(f"Created new incident: {incident.incident_id} for {event.endpoint}")
        
        # Add event to incident
        best_incident.add_anomaly(event)
        log.debug(
            f"Added anomaly to incident {best_incident.incident_id}: "
            f"{event.service} / {event.endpoint} severity={event.severity:.2f}"
        )
        
        return best_incident
    
    def get_active_incidents(self, now: Optional[datetime] = None) -> List[Incident]:
        """Return all currently active incidents.
        
        Args:
            now: Current time (defaults to utcnow).
            
        Returns:
            List of Incident objects.
        """
        if now is None:
            now = datetime.utcnow()
        
        active = []
        for incident in self.incidents.values():
            # Include incidents whose window hasn't expired
            if incident.time_window_end >= now:
                active.append(incident)
        
        return active
    
    def close_old_incidents(self, now: Optional[datetime] = None) -> List[Incident]:
        """Close incidents that have expired.
        
        Args:
            now: Current time (defaults to utcnow).
            
        Returns:
            List of closed Incident objects.
        """
        if now is None:
            now = datetime.utcnow()
        
        closed = []
        to_remove = []
        
        for key, incident in self.incidents.items():
            if incident.time_window_end < now:
                closed.append(incident)
                to_remove.append(key)
        
        for key in to_remove:
            del self.incidents[key]
            log.info(f"Closed incident: {self.incidents[key].incident_id}")
        
        return closed
