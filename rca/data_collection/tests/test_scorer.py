"""Tests for scorer module."""

import pytest
from rca.data_collection.scorer import AnomalyScorer


class TestZScore:
    """Tests for z-score computation."""
    
    @pytest.fixture
    def scorer(self):
        return AnomalyScorer(z_max=3.0, epsilon=1e-6)
    
    def test_z_score_at_mean(self, scorer):
        """Test z-score when value equals mean."""
        z = scorer.z_score(5.0, mean=5.0, std=1.0)
        assert abs(z) < 0.01
    
    def test_z_score_above_mean(self, scorer):
        """Test z-score when value is above mean."""
        z = scorer.z_score(10.0, mean=5.0, std=2.0)
        # (10 - 5) / 2 = 2.5
        assert abs(z - 2.5) < 0.01
    
    def test_z_score_below_mean(self, scorer):
        """Test z-score when value is below mean."""
        z = scorer.z_score(2.0, mean=5.0, std=2.0)
        # (2 - 5) / 2 = -1.5
        assert abs(z - (-1.5)) < 0.01
    
    def test_z_score_zero_std(self, scorer):
        """Test z-score with zero std (should use epsilon)."""
        z = scorer.z_score(5.0, mean=5.0, std=0.0)
        assert isinstance(z, float)


class TestNormalizedScore:
    """Tests for normalized score [0, 1]."""
    
    @pytest.fixture
    def scorer(self):
        return AnomalyScorer(z_max=3.0)
    
    def test_normalized_score_zero_z(self, scorer):
        """Test normalized score for z=0."""
        score = scorer.normalized_score(0.0)
        assert score == 0.0
    
    def test_normalized_score_at_z_max(self, scorer):
        """Test normalized score at z=Z_max."""
        score = scorer.normalized_score(3.0)
        assert abs(score - 1.0) < 0.01
    
    def test_normalized_score_halfway(self, scorer):
        """Test normalized score at z=Z_max/2."""
        score = scorer.normalized_score(1.5)
        assert abs(score - 0.5) < 0.01
    
    def test_normalized_score_beyond_z_max(self, scorer):
        """Test normalized score clips to 1.0 for large z."""
        score = scorer.normalized_score(100.0)
        assert abs(score - 1.0) < 0.01
    
    def test_normalized_score_negative_z(self, scorer):
        """Test normalized score handles negative z (uses absolute value)."""
        score = scorer.normalized_score(-3.0)
        assert abs(score - 1.0) < 0.01
    
    def test_normalized_score_in_range(self, scorer):
        """Test that all scores are in [0, 1]."""
        for z in [0, 0.5, 1.0, 1.5, 3.0, 10.0, -5.0]:
            score = scorer.normalized_score(z)
            assert 0.0 <= score <= 1.0


class TestSeverity:
    """Tests for combined severity computation."""
    
    @pytest.fixture
    def scorer(self):
        return AnomalyScorer()
    
    def test_severity_equal_scores(self, scorer):
        """Test severity with equal latency and error scores."""
        severity = scorer.compute_severity(0.8, 0.8, latency_weight=0.5, error_weight=0.5)
        assert abs(severity - 0.8) < 0.01
    
    def test_severity_latency_dominant(self, scorer):
        """Test severity with latency dominant (0.6 weight)."""
        severity = scorer.compute_severity(1.0, 0.0, latency_weight=0.6, error_weight=0.4)
        assert abs(severity - 0.6) < 0.01
    
    def test_severity_error_dominant(self, scorer):
        """Test severity with error dominant (0.4 weight)."""
        severity = scorer.compute_severity(0.0, 1.0, latency_weight=0.6, error_weight=0.4)
        assert abs(severity - 0.4) < 0.01
    
    def test_severity_mixed(self, scorer):
        """Test severity with mixed values."""
        severity = scorer.compute_severity(0.8, 0.6, latency_weight=0.6, error_weight=0.4)
        # 0.6 * 0.8 + 0.4 * 0.6 = 0.48 + 0.24 = 0.72
        assert abs(severity - 0.72) < 0.01
    
    def test_severity_clipped_to_1(self, scorer):
        """Test that severity never exceeds 1.0."""
        severity = scorer.compute_severity(2.0, 2.0)
        assert severity <= 1.0


class TestScoreStream:
    """Tests for full stream scoring."""
    
    @pytest.fixture
    def scorer(self):
        return AnomalyScorer(z_max=3.0)
    
    def test_score_stream_normal(self, scorer):
        """Test scoring when metrics are normal."""
        latency_score, error_score, severity = scorer.score_stream(
            current_latency=0.1,  # At baseline
            mean_latency=0.1,
            std_latency=0.01,
            current_error=0.01,  # At baseline
            mean_error=0.01,
            std_error=0.001,
        )
        
        # All scores should be low
        assert latency_score < 0.2
        assert error_score < 0.2
        assert severity < 0.2
    
    def test_score_stream_latency_spike(self, scorer):
        """Test scoring with latency spike."""
        latency_score, error_score, severity = scorer.score_stream(
            current_latency=1.0,  # 10x baseline
            mean_latency=0.1,
            std_latency=0.01,
            current_error=0.01,  # Normal
            mean_error=0.01,
            std_error=0.001,
        )
        
        # Latency should be high, error low
        assert latency_score > 0.5
        assert error_score < 0.2
    
    def test_score_stream_error_spike(self, scorer):
        """Test scoring with error rate spike."""
        latency_score, error_score, severity = scorer.score_stream(
            current_latency=0.1,  # Normal
            mean_latency=0.1,
            std_latency=0.01,
            current_error=0.2,  # 20x baseline
            mean_error=0.01,
            std_error=0.001,
        )
        
        # Error should be high, latency low
        assert latency_score < 0.2
        assert error_score > 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
