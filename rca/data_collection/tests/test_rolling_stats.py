"""Tests for rolling_stats module."""

import pytest
from rca.data_collection.ring_buffer import RingBuffer
from rca.data_collection.rolling_stats import RollingStats


class TestRollingStatsMean:
    """Tests for rolling mean computation."""
    
    def test_mean_empty_buffer(self):
        """Test mean with empty buffer."""
        buf = RingBuffer(10)
        stats = RollingStats(buf)
        assert stats.mean() == 0.0
    
    def test_mean_single_value(self):
        """Test mean with single value."""
        buf = RingBuffer(10)
        buf.push(5.0)
        stats = RollingStats(buf)
        assert stats.mean() == 5.0
    
    def test_mean_multiple_values(self):
        """Test mean with multiple values."""
        buf = RingBuffer(10)
        buf.push(1.0)
        buf.push(2.0)
        buf.push(3.0)
        
        stats = RollingStats(buf)
        assert abs(stats.mean() - 2.0) < 0.01
    
    def test_mean_after_overflow(self):
        """Test mean after buffer overflow."""
        buf = RingBuffer(3)
        buf.push(10.0)
        buf.push(20.0)
        buf.push(30.0)
        buf.push(40.0)  # Now [20, 30, 40]
        
        stats = RollingStats(buf)
        assert abs(stats.mean() - 30.0) < 0.01


class TestRollingStatsStd:
    """Tests for rolling standard deviation."""
    
    def test_std_empty_buffer(self):
        """Test std with empty buffer."""
        buf = RingBuffer(10)
        stats = RollingStats(buf, epsilon=1e-6)
        std = stats.std()
        assert std >= 1e-6
    
    def test_std_single_value(self):
        """Test std with single value."""
        buf = RingBuffer(10)
        buf.push(5.0)
        stats = RollingStats(buf)
        std = stats.std()
        assert std < 0.01
    
    def test_std_constant_values(self):
        """Test std when all values are identical."""
        buf = RingBuffer(10)
        for _ in range(5):
            buf.push(100.0)
        
        stats = RollingStats(buf)
        std = stats.std()
        assert std < 0.01
    
    def test_std_spread_values(self):
        """Test std with varied values."""
        buf = RingBuffer(10)
        buf.push(1.0)
        buf.push(2.0)
        buf.push(3.0)
        
        stats = RollingStats(buf)
        std = stats.std()
        # Std of [1,2,3] should be ~0.816
        assert abs(std - 0.816) < 0.1


class TestZScore:
    """Tests for z-score computation."""
    
    def test_z_score_at_mean(self):
        """Test z-score when value equals mean."""
        buf = RingBuffer(10)
        for _ in range(5):
            buf.push(5.0)
        
        stats = RollingStats(buf)
        z = stats.z_score(5.0, mean=5.0, std=1.0)
        assert abs(z) < 0.01
    
    def test_z_score_above_mean(self):
        """Test z-score when value is above mean."""
        z = RollingStats(RingBuffer(10)).z_score(10.0, mean=5.0, std=2.0)
        # Should be (10 - 5) / 2 = 2.5
        assert abs(z - 2.5) < 0.01
    
    def test_z_score_below_mean(self):
        """Test z-score when value is below mean."""
        z = RollingStats(RingBuffer(10)).z_score(2.0, mean=5.0, std=2.0)
        # Should be (2 - 5) / 2 = -1.5
        assert abs(z - (-1.5)) < 0.01
    
    def test_z_score_zero_std(self):
        """Test z-score with zero std (division guard)."""
        z = RollingStats(RingBuffer(10), epsilon=1e-6).z_score(5.0, mean=5.0, std=0.0)
        # Should handle gracefully
        assert isinstance(z, float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
