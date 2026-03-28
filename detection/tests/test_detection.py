"""Unit tests for ring buffer."""

import pytest
from detection.ring_buffer import RingBuffer


class TestRingBuffer:
    """Tests for RingBuffer implementation."""
    
    def test_init_invalid_size(self):
        """Test that size must be positive."""
        with pytest.raises(ValueError):
            RingBuffer(0)
        with pytest.raises(ValueError):
            RingBuffer(-1)
    
    def test_single_value(self):
        """Test pushing and retrieving single value."""
        buf = RingBuffer(5)
        buf.push(1.0)
        assert len(buf) == 1
        assert buf.get_all() == [1.0]
    
    def test_fill_buffer(self):
        """Test filling buffer to capacity."""
        buf = RingBuffer(3)
        buf.push(1.0)
        buf.push(2.0)
        buf.push(3.0)
        
        assert len(buf) == 3
        assert buf.is_full()
        assert buf.get_all() == [1.0, 2.0, 3.0]
    
    def test_overflow_behavior(self):
        """Test that buffer wraps and overwrites oldest."""
        buf = RingBuffer(3)
        buf.push(1.0)
        buf.push(2.0)
        buf.push(3.0)
        buf.push(4.0)  # Should overwrite 1.0
        
        assert len(buf) == 3
        assert buf.get_all() == [2.0, 3.0, 4.0]
    
    def test_continuous_overflow(self):
        """Test continuous overwrites."""
        buf = RingBuffer(2)
        vals = [10, 20, 30, 40, 50]
        
        for v in vals:
            buf.push(float(v))
        
        # Should have [40, 50]
        assert buf.get_all() == [40.0, 50.0]
    
    def test_empty_buffer(self):
        """Test that empty buffer returns empty list."""
        buf = RingBuffer(5)
        assert len(buf) == 0
        assert buf.get_all() == []


class TestRollingStats:
    """Tests for rolling statistics."""
    
    def test_mean_single_value(self):
        """Test mean with single value."""
        from detection.rolling_stats import RollingStats
        
        buf = RingBuffer(5)
        buf.push(10.0)
        stats = RollingStats(buf)
        
        assert stats.mean() == 10.0
        assert stats.std() == 0.0
    
    def test_mean_multiple_values(self):
        """Test mean computation."""
        from detection.rolling_stats import RollingStats
        
        buf = RingBuffer(5)
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            buf.push(v)
        
        stats = RollingStats(buf)
        assert stats.mean() == 3.0
    
    def test_std_multiple_values(self):
        """Test std dev computation."""
        from detection.rolling_stats import RollingStats
        
        buf = RingBuffer(5)
        # Known set: [1, 2, 3, 4, 5]
        # Mean = 3, Variance = 2.5 (using n-1)
        # Std = sqrt(2.5) ≈ 1.581
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            buf.push(v)
        
        stats = RollingStats(buf)
        std = stats.std()
        assert abs(std - 1.581) < 0.01
    
    def test_empty_buffer_stats(self):
        """Test stats on empty buffer."""
        from detection.rolling_stats import RollingStats
        
        buf = RingBuffer(5)
        stats = RollingStats(buf)
        
        assert stats.mean() == 0.0
        assert stats.std() == 0.0


class TestScorer:
    """Tests for anomaly scoring."""
    
    def test_z_score_calculation(self):
        """Test z-score formula."""
        from detection.scorer import AnomalyScorer
        
        scorer = AnomalyScorer(z_max=3.0)
        
        # Standard case: value=5, mean=0, std=1
        # z = (5 - 0) / (1 + 1e-6) = 5
        z = scorer.z_score(5.0, 0.0, 1.0)
        assert abs(z - 5.0) < 0.01
    
    def test_z_score_zero_std(self):
        """Test z-score with zero std."""
        from detection.scorer import AnomalyScorer
        
        scorer = AnomalyScorer()
        z = scorer.z_score(5.0, 0.0, 0.0, epsilon=1e-6)
        
        # With epsilon: z = 5 / 1e-6 = 5e6
        assert z > 1e6
    
    def test_normalized_score(self):
        """Test normalization to [0, 1]."""
        from detection.scorer import AnomalyScorer
        
        scorer = AnomalyScorer(z_max=3.0)
        
        assert scorer.normalized_score(0.0) == 0.0
        assert scorer.normalized_score(3.0) == 1.0
        assert scorer.normalized_score(-3.0) == 1.0
        assert scorer.normalized_score(6.0) == 1.0  # Clipped to 1.0
    
    def test_severity_calculation(self):
        """Test severity combination."""
        from detection.scorer import AnomalyScorer
        
        scorer = AnomalyScorer()
        
        # Both zero: severity = 0
        assert scorer.compute_severity(0.0, 0.0) == 0.0
        
        # Latency only: 0.6 * 1.0 = 0.6
        assert scorer.compute_severity(1.0, 0.0) == 0.6
        
        # Error only: 0.4 * 1.0 = 0.4
        assert scorer.compute_severity(0.0, 1.0) == 0.4
        
        # Both max: 0.6 * 1.0 + 0.4 * 1.0 = 1.0
        assert scorer.compute_severity(1.0, 1.0) == 1.0


class TestDetector:
    """Tests for main detector logic."""
    
    def test_warmup_period(self):
        """Test that detector is in warmup initially."""
        from detection.config import DetectionConfig
        from detection.detector import AnomalyDetector
        
        config = DetectionConfig(warmup_seconds=10)
        detector = AnomalyDetector(config)
        
        assert detector.is_in_warmup()
        assert detector.get_warmup_remaining_seconds() > 0
        assert detector.get_warmup_remaining_seconds() <= 10


class TestIncidentClustering:
    """Tests for incident clustering."""
    
    def test_single_event_creates_incident(self):
        """Test that first event creates incident."""
        from detection.incident_cluster import IncidentCluster
        from detection.models import AnomalyEvent, AnomalyType
        from datetime import datetime
        
        clusterer = IncidentCluster(cluster_window_seconds=10)
        
        event = AnomalyEvent(
            service="payment",
            endpoint="/checkout",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=0.8,
            timestamp=datetime.utcnow()
        )
        
        incident = clusterer.add_event(event)
        
        assert incident is not None
        assert incident.endpoint == "/checkout"
        assert len(incident.anomalies) == 1
    
    def test_same_endpoint_joins_incident(self):
        """Test that events on same endpoint join incident."""
        from detection.incident_cluster import IncidentCluster
        from detection.models import AnomalyEvent, AnomalyType
        from datetime import datetime
        
        clusterer = IncidentCluster(cluster_window_seconds=10)
        
        # First event
        event1 = AnomalyEvent(
            service="payment",
            endpoint="/checkout",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=0.8,
            timestamp=datetime.utcnow()
        )
        incident1 = clusterer.add_event(event1)
        
        # Second event on same endpoint
        event2 = AnomalyEvent(
            service="catalog",
            endpoint="/checkout",
            anomaly_type=AnomalyType.ERROR_SPIKE,
            severity=0.7,
            timestamp=datetime.utcnow()
        )
        incident2 = clusterer.add_event(event2)
        
        # Should be same incident
        assert incident1.incident_id == incident2.incident_id
        assert len(incident2.anomalies) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
