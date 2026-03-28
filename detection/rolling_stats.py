"""Rolling statistics for online mean and standard deviation.

Computes mean and std from buffer values efficiently.
Used to normalize metric streams for anomaly scoring.
"""

from typing import Tuple
from detection.ring_buffer import RingBuffer


class RollingStats:
    """Maintains rolling mean and std over a buffer.
    
    Recomputes mean/std from buffer whenever asked (simple, correct).
    For production with millions of streams, could implement
    Welford's online algorithm, but this is accurate and clear.
    
    Attributes:
        buffer: Ring buffer storing metric values
    """
    
    def __init__(self, buffer: RingBuffer):
        """Initialize with a buffer.
        
        Args:
            buffer: RingBuffer instance to compute stats from
        """
        self.buffer = buffer
    
    def mean(self) -> float:
        """Compute mean of buffer values.
        
        Returns:
            Mean, or 0.0 if buffer is empty
        """
        values = self.buffer.get_all()
        if not values:
            return 0.0
        return sum(values) / len(values)
    
    def std(self) -> float:
        """Compute sample standard deviation.
        
        Returns:
            Std Dev, or 0.0 if buffer has < 2 values
        """
        values = self.buffer.get_all()
        if len(values) < 2:
            return 0.0
        
        mean_val = self.mean()
        variance = sum((x - mean_val) ** 2 for x in values) / (len(values) - 1)
        
        # Avoid negative variance due to floating point errors
        if variance < 0:
            return 0.0
        return variance ** 0.5
    
    def get_stats(self) -> Tuple[float, float]:
        """Get both mean and std in one call.
        
        Returns:
            Tuple of (mean, std)
        """
        return self.mean(), self.std()
