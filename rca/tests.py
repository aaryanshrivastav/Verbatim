"""RCA pipeline unit tests."""

import pytest
import logging
from datetime import datetime, timedelta

from rca.models import Incident, AnomalyDetail, TraceMetrics, Candidate, FeatureVector
from rca.config import RCAConfig
from rca.B_candidate_extractor import CandidateExtractor
from rca.C_feature_builder import FeatureBuilder
from rca.E_root_cause_selector import RootCauseSelector
from rca.F_state_vector import StateVectorBuilder

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def config():
    """Fixture for RCAConfig."""
    return RCAConfig()


@pytest.fixture
def example_incident():
    """Fixture for example incident."""
    now = datetime.utcnow()
    return Incident(
        incident_id="inc-test",
        endpoint="/checkout",
        time_window_start=now - timedelta(seconds=10),
        time_window_end=now,
        anomalies=[
            AnomalyDetail("payment-service", 0.91, "latency_spike"),
            AnomalyDetail("checkout", 0.86, "latency_spike"),
            AnomalyDetail("frontend", 0.78, "latency_spike")
        ]
    )


@pytest.fixture
def example_trace_metrics():
    """Fixture for trace metrics."""
    return {
        "payment-service": TraceMetrics(
            service="payment-service",
            span_count=100,
            suspicious_count=45,
            trace_coverage=0.95,
            suspicious_span_ratio=0.45
        ),
        "checkout": TraceMetrics(
            service="checkout",
            span_count=80,
            suspicious_count=12,
            trace_coverage=0.98,
            suspicious_span_ratio=0.15
        ),
        "frontend": TraceMetrics(
            service="frontend",
            span_count=20,
            suspicious_count=2,
            trace_coverage=0.85,
            suspicious_span_ratio=0.10
        )
    }


def test_candidate_extractor(config, example_incident, example_trace_metrics):
    """Test candidate extraction."""
    extractor = CandidateExtractor(config)
    candidates = extractor.extract_candidates(example_incident, example_trace_metrics)
    
    assert len(candidates) > 0
    assert candidates[0].service == "payment-service"
    assert candidates[0].trace_metrics.suspicious_span_ratio > 0.2


def test_feature_builder(config):
    """Test feature building."""
    builder = FeatureBuilder(config)
    
    candidate = Candidate(
        service="payment-service",
        trace_metrics=TraceMetrics(
            service="payment-service",
            span_count=100,
            suspicious_count=45,
            trace_coverage=0.95,
            suspicious_span_ratio=0.45
        ),
        feature_vector=FeatureVector(
            service="payment-service",
            m=0.91,
            t=0.45,
            c=0.95,
            depth=0,
            is_db=0,
            is_edge=0
        )
    )
    
    candidates = builder.build_features([candidate])
    
    assert candidates[0].feature_vector.depth == 3  # payment service
    assert candidates[0].feature_vector.is_db == 0
    assert candidates[0].feature_vector.is_edge == 0


def test_feature_builder_database(config):
    """Test feature builder with database service."""
    builder = FeatureBuilder(config)
    
    candidate = Candidate(
        service="orders-db",
        trace_metrics=TraceMetrics(
            service="orders-db",
            span_count=50,
            suspicious_count=40,
            trace_coverage=0.8,
            suspicious_span_ratio=0.8
        ),
        feature_vector=FeatureVector(
            service="orders-db",
            m=0.85,
            t=0.8,
            c=0.8,
            depth=0,
            is_db=0,
            is_edge=0
        )
    )
    
    candidates = builder.build_features([candidate])
    
    assert candidates[0].feature_vector.is_db == 1
    assert candidates[0].feature_vector.depth == -1


def test_root_cause_selector(config):
    """Test root cause selection."""
    selector = RootCauseSelector(config)
    
    candidates = [
        Candidate(
            service="payment-service",
            trace_metrics=TraceMetrics("payment-service", 0, 0, 0.95, 0.45),
            feature_vector=FeatureVector("payment-service", 0.91, 0.45, 0.95, 3, 0, 0),
            probability=0.84
        ),
        Candidate(
            service="orders-db",
            trace_metrics=TraceMetrics("orders-db", 0, 0, 0.8, 0.8),
            feature_vector=FeatureVector("orders-db", 0.85, 0.8, 0.8, -1, 1, 0),
            probability=0.47
        ),
        Candidate(
            service="checkout",
            trace_metrics=TraceMetrics("checkout", 0, 0, 0.98, 0.15),
            feature_vector=FeatureVector("checkout", 0.86, 0.15, 0.98, 2, 0, 0),
            probability=0.30
        )
    ]
    
    root_cause, confidence, top_3 = selector.select_root_cause(candidates)
    
    assert root_cause.service == "payment-service"
    assert root_cause.probability == 0.84
    assert confidence.bucket.value == "high"  # 0.84 - 0.47 = 0.37 > 0.3
    assert len(top_3) == 3


def test_state_vector(config, example_incident):
    """Test state vector building."""
    builder = StateVectorBuilder(config)
    state_vector = builder.build_state_vector(example_incident)
    
    assert len(state_vector) == 6
    # payment-service severity 0.91 should be critical (>= 0.8)
    assert state_vector[4] == 2  # state_vector[4] is payment


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
