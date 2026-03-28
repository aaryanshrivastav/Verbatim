"""Tests for incident_cluster module."""

import pytest
from datetime import datetime, timedelta
from rca.data_collection.incident_cluster import IncidentCluster
from rca.data_collection.models import AnomalyEvent, AnomalyType


class TestIncidentClusterInit:
    """Tests for incident cluster initialization."""
    
    def test_init_default_window(self):
        """Test initialization with default window."""
        clusterer = IncidentCluster()
        assert clusterer.cluster_window_seconds == 10
        assert clusterer.incidents == {}
    
    def test_init_custom_window(self):
        """Test initialization with custom window."""
        clusterer = IncidentCluster(cluster_window_seconds=30)
        assert clusterer.cluster_window_seconds == 30


class TestAddEvent:
    """Tests for adding events to clusters."""
    
    def test_add_single_event(self):
        """Test adding a single event creates new incident."""
        clusterer = IncidentCluster()
        now = datetime.utcnow()
        
        event = AnomalyEvent(
            service="payment",
            endpoint="/checkout",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=0.85,
            timestamp=now,
            latency_score=0.8,
            error_score=0.5,
        )
        
        incident = clusterer.add_event(event)
        
        assert incident is not None
        assert incident.endpoint == "/checkout"
        assert len(incident.anomalies) == 1
    
    def test_add_same_service_same_window(self):
        """Test adding same service twice in same window."""
        clusterer = IncidentCluster(cluster_window_seconds=10)
        now = datetime.utcnow()
        
        event1 = AnomalyEvent(
            service="payment",
            endpoint="/checkout",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=0.85,
            timestamp=now,
            latency_score=0.8,
            error_score=0.5,
        )
        
        event2 = AnomalyEvent(
            service="payment",
            endpoint="/checkout",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=0.88,
            timestamp=now + timedelta(seconds=2),
            latency_score=0.85,
            error_score=0.5,
        )
        
        incident1 = clusterer.add_event(event1)
        incident2 = clusterer.add_event(event2)
        
        # Should be same incident
        assert incident1.incident_id == incident2.incident_id
        assert len(incident2.anomalies) >= 1
    
    def test_add_different_services_same_endpoint(self):
        """Test adding different services to same endpoint."""
        clusterer = IncidentCluster(cluster_window_seconds=10)
        now = datetime.utcnow()
        
        event1 = AnomalyEvent(
            service="payment",
            endpoint="/checkout",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=0.85,
            timestamp=now,
            latency_score=0.8,
            error_score=0.5,
        )
        
        event2 = AnomalyEvent(
            service="order-service",
            endpoint="/checkout",
            anomaly_type=AnomalyType.ERROR_SPIKE,
            severity=0.80,
            timestamp=now + timedelta(seconds=1),
            latency_score=0.3,
            error_score=0.75,
        )
        
        incident1 = clusterer.add_event(event1)
        incident2 = clusterer.add_event(event2)
        
        # Should both be in same incident (same endpoint, same window)
        assert incident1.incident_id == incident2.incident_id
    
    def test_add_different_endpoints(self):
        """Test adding different endpoints creates different incidents."""
        clusterer = IncidentCluster()
        now = datetime.utcnow()
        
        event1 = AnomalyEvent(
            service="payment",
            endpoint="/checkout",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=0.85,
            timestamp=now,
            latency_score=0.8,
            error_score=0.5,
        )
        
        event2 = AnomalyEvent(
            service="payment",
            endpoint="/orders",
            anomaly_type=AnomalyType.ERROR_SPIKE,
            severity=0.80,
            timestamp=now + timedelta(seconds=1),
            latency_score=0.3,
            error_score=0.75,
        )
        
        incident1 = clusterer.add_event(event1)
        incident2 = clusterer.add_event(event2)
        
        # Different endpoints → different incidents
        assert incident1.incident_id != incident2.incident_id
        assert incident1.endpoint == "/checkout"
        assert incident2.endpoint == "/orders"
    
    def test_add_outside_time_window(self):
        """Test event outside cluster window creates new incident."""
        clusterer = IncidentCluster(cluster_window_seconds=10)
        now = datetime.utcnow()
        
        event1 = AnomalyEvent(
            service="payment",
            endpoint="/checkout",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=0.85,
            timestamp=now,
            latency_score=0.8,
            error_score=0.5,
        )
        
        # Event 15 seconds later (outside 10-second window)
        event2 = AnomalyEvent(
            service="payment",
            endpoint="/checkout",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=0.82,
            timestamp=now + timedelta(seconds=15),
            latency_score=0.78,
            error_score=0.45,
        )
        
        incident1 = clusterer.add_event(event1)
        incident2 = clusterer.add_event(event2)
        
        # Should be different incidents
        assert incident1.incident_id != incident2.incident_id


class TestActiveIncidents:
    """Tests for querying active incidents."""
    
    def test_get_active_incidents_empty(self):
        """Test getting active incidents when none exist."""
        clusterer = IncidentCluster()
        active = clusterer.get_active_incidents()
        
        assert active == []
    
    def test_get_active_incidents(self):
        """Test getting active incidents."""
        clusterer = IncidentCluster(cluster_window_seconds=10)
        now = datetime.utcnow()
        
        event = AnomalyEvent(
            service="payment",
            endpoint="/checkout",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=0.85,
            timestamp=now,
            latency_score=0.8,
            error_score=0.5,
        )
        
        clusterer.add_event(event)
        active = clusterer.get_active_incidents(now)
        
        assert len(active) == 1
    
    def test_get_active_incidents_expired(self):
        """Test that expired incidents are not returned."""
        clusterer = IncidentCluster(cluster_window_seconds=10)
        now = datetime.utcnow()
        
        event = AnomalyEvent(
            service="payment",
            endpoint="/checkout",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=0.85,
            timestamp=now - timedelta(seconds=20),  # Old
            latency_score=0.8,
            error_score=0.5,
        )
        
        clusterer.add_event(event)
        
        # Query far in the future
        future = now + timedelta(seconds=100)
        active = clusterer.get_active_incidents(future)
        
        # Incident should have expired
        assert len(active) == 0


class TestCloseOldIncidents:
    """Tests for closing expired incidents."""
    
    def test_close_old_incidents_none(self):
        """Test closing when no incidents are expired."""
        clusterer = IncidentCluster(cluster_window_seconds=10)
        now = datetime.utcnow()
        
        event = AnomalyEvent(
            service="payment",
            endpoint="/checkout",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=0.85,
            timestamp=now,
            latency_score=0.8,
            error_score=0.5,
        )
        
        clusterer.add_event(event)
        closed = clusterer.close_old_incidents(now)
        
        # Incident is still within window
        assert len(closed) == 0
    
    def test_close_old_incidents_some(self):
        """Test closing expired incidents."""
        clusterer = IncidentCluster(cluster_window_seconds=10)
        now = datetime.utcnow()
        
        event = AnomalyEvent(
            service="payment",
            endpoint="/checkout",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=0.85,
            timestamp=now - timedelta(seconds=20),
            latency_score=0.8,
            error_score=0.5,
        )
        
        clusterer.add_event(event)
        
        # Close from far future
        future = now + timedelta(seconds=100)
        closed = clusterer.close_old_incidents(future)
        
        # Incident should have been closed
        assert len(closed) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
