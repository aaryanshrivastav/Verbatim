"""Tests for detector module."""

import pytest
from datetime import datetime, timedelta
from rca.data_collection.config import DetectionConfig
from rca.data_collection.detector import AnomalyDetector
from rca.data_collection.models import AnomalyType


class TestAnomalyDetectorInit:
    """Tests for detector initialization."""
    
    def test_init_with_valid_config(self):
        """Test detector initialization with valid config."""
        config = DetectionConfig()
        config.warmup_seconds = 10
        detector = AnomalyDetector(config)
        
        assert detector.config == config
        assert detector.streams == {}
        assert detector.events == []
        assert detector.is_in_warmup()
    
    def test_init_with_invalid_config(self):
        """Test that invalid config raises error."""
        config = DetectionConfig()
        config.window_size = -1  # Invalid
        
        with pytest.raises(ValueError):
            AnomalyDetector(config)


class TestWarmup:
    """Tests for warm-up period logic."""
    
    def test_is_in_warmup_immediately_after_init(self):
        """Test that detector is in warmup immediately after init."""
        config = DetectionConfig()
        config.warmup_seconds = 100
        detector = AnomalyDetector(config)
        
        assert detector.is_in_warmup()
    
    def test_is_in_warmup_after_expiry(self):
        """Test that warmup expires after configured duration."""
        config = DetectionConfig()
        config.warmup_seconds = 1  # 1 second warmup
        detector = AnomalyDetector(config)
        
        # Fake the warmup end to past
        detector.warmup_until = datetime.utcnow() - timedelta(seconds=1)
        
        assert not detector.is_in_warmup()
    
    def test_get_warmup_remaining_seconds(self):
        """Test getting remaining warmup time."""
        config = DetectionConfig()
        config.warmup_seconds = 100
        detector = AnomalyDetector(config)
        
        remaining = detector.get_warmup_remaining_seconds()
        assert 0 < remaining <= 100


class TestEventCreation:
    """Tests for AnomalyEvent creation and classification."""
    
    def test_create_event_mixed_anomaly(self):
        """Test event creation with both anomalies."""
        config = DetectionConfig()
        detector = AnomalyDetector(config)
        
        # Skip warmup
        detector.warmup_until = datetime.utcnow() - timedelta(seconds=1)
        
        event = detector._create_event(
            service="payment",
            endpoint="/checkout",
            latency_anomaly=True,
            error_anomaly=True,
            severity=0.85,
            latency_score=0.8,
            error_score=0.75,
            timestamp=datetime.utcnow(),
        )
        
        assert event.service == "payment"
        assert event.endpoint == "/checkout"
        assert event.anomaly_type == AnomalyType.MIXED
        assert event.severity == 0.85
    
    def test_create_event_latency_only(self):
        """Test event creation with latency anomaly only."""
        config = DetectionConfig()
        detector = AnomalyDetector(config)
        
        event = detector._create_event(
            service="payment",
            endpoint="/checkout",
            latency_anomaly=True,
            error_anomaly=False,
            severity=0.65,
            latency_score=0.7,
            error_score=0.2,
            timestamp=datetime.utcnow(),
        )
        
        assert event.anomaly_type == AnomalyType.LATENCY_SPIKE
    
    def test_create_event_error_only(self):
        """Test event creation with error anomaly only."""
        config = DetectionConfig()
        detector = AnomalyDetector(config)
        
        event = detector._create_event(
            service="payment",
            endpoint="/checkout",
            latency_anomaly=False,
            error_anomaly=True,
            severity=0.65,
            latency_score=0.2,
            error_score=0.7,
            timestamp=datetime.utcnow(),
        )
        
        assert event.anomaly_type == AnomalyType.ERROR_SPIKE


class TestStreamManagement:
    """Tests for stream state management."""
    
    def test_ensure_stream_exists_creates_new(self):
        """Test that ensure_stream_exists creates new stream."""
        config = DetectionConfig()
        detector = AnomalyDetector(config)
        
        key = detector._ensure_stream_exists("payment", "/checkout")
        
        assert key in detector.streams
        assert detector.streams[key].key == key
    
    def test_ensure_stream_exists_reuses_existing(self):
        """Test that ensure_stream_exists reuses existing stream."""
        config = DetectionConfig()
        detector = AnomalyDetector(config)
        
        key1 = detector._ensure_stream_exists("payment", "/checkout")
        key2 = detector._ensure_stream_exists("payment", "/checkout")
        
        assert key1 == key2
        assert len(detector.streams) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
