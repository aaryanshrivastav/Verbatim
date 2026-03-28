"""Tests for ring_buffer module."""

import pytest
from rca.data_collection.ring_buffer import RingBuffer


class TestRingBufferInit:
    """Tests for buffer initialization."""
    
    def test_init_valid_size(self):
        """Test buffer creation with valid size."""
        buf = RingBuffer(10)
        assert len(buf) == 0
        assert not buf.is_full()
    
    def test_init_invalid_size_zero(self):
        """Test that size=0 raises ValueError."""
        with pytest.raises(ValueError):
            RingBuffer(0)
    
    def test_init_invalid_size_negative(self):
        """Test that negative size raises ValueError."""
        with pytest.raises(ValueError):
            RingBuffer(-5)


class TestRingBufferOperations:
    """Tests for buffer push and get operations."""
    
    def test_single_push(self):
        """Test pushing a single value."""
        buf = RingBuffer(5)
        buf.push(1.5)
        
        assert len(buf) == 1
        assert buf.get_all() == [1.5]
        assert not buf.is_full()
    
    def test_fill_buffer(self):
        """Test filling buffer to capacity."""
        buf = RingBuffer(3)
        buf.push(1.0)
        buf.push(2.0)
        buf.push(3.0)
        
        assert len(buf) == 3
        assert buf.is_full()
        assert buf.get_all() == [1.0, 2.0, 3.0]
    
    def test_overflow_single(self):
        """Test buffer wrapping with single overflow."""
        buf = RingBuffer(3)
        buf.push(1.0)
        buf.push(2.0)
        buf.push(3.0)
        buf.push(4.0)  # Overwrite 1.0
        
        assert len(buf) == 3
        assert buf.is_full()
        assert buf.get_all() == [2.0, 3.0, 4.0]
    
    def test_overflow_multiple(self):
        """Test buffer wrapping with multiple overflows."""
        buf = RingBuffer(2)
        
        for i in range(10):
            buf.push(float(i))
        
        # Should contain last 2 values
        assert len(buf) == 2
        assert buf.get_all() == [8.0, 9.0]


class TestRingBufferMean:
    """Tests for mean computation."""
    
    def test_mean_empty(self):
        """Test mean of empty buffer."""
        buf = RingBuffer(5)
        assert buf.mean() == 0.0
    
    def test_mean_single(self):
        """Test mean with single value."""
        buf = RingBuffer(5)
        buf.push(7.5)
        assert buf.mean() == 7.5
    
    def test_mean_multiple(self):
        """Test mean with multiple values."""
        buf = RingBuffer(10)
        buf.push(1.0)
        buf.push(2.0)
        buf.push(3.0)
        
        assert abs(buf.mean() - 2.0) < 0.01
    
    def test_mean_after_overflow(self):
        """Test mean after buffer overflow."""
        buf = RingBuffer(3)
        buf.push(10.0)
        buf.push(20.0)
        buf.push(30.0)
        buf.push(40.0)  # Now [20, 30, 40]
        
        assert abs(buf.mean() - 30.0) < 0.01


class TestRingBufferStd:
    """Tests for standard deviation computation."""
    
    def test_std_empty(self):
        """Test std of empty buffer."""
        buf = RingBuffer(5)
        std = buf.std()
        assert std >= 1e-6  # Should be epsilon
    
    def test_std_single(self):
        """Test std with single value."""
        buf = RingBuffer(5)
        buf.push(5.0)
        std = buf.std()
        assert std < 0.01  # Should be epsilon
    
    def test_std_constant_values(self):
        """Test std when all values are the same."""
        buf = RingBuffer(10)
        for _ in range(5):
            buf.push(5.0)
        
        std = buf.std()
        assert std < 0.01  # Std should be near epsilon
    
    def test_std_spread_values(self):
        """Test std with spread values."""
        buf = RingBuffer(10)
        buf.push(1.0)
        buf.push(2.0)
        buf.push(3.0)
        
        std = buf.std()
        assert std > 0.5  # Should have measurable std


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
