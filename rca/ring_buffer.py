"""Ring buffer for tracking baseline metrics per service/endpoint."""

from collections import deque
from typing import List, Tuple


class RingBuffer:
    """Fixed-size circular buffer for baseline tracking.
    
    Stores recent (service, metric_type, duration) observations.
    Computes rolling mean/std for anomaly detection.
    """
    
    def __init__(self, max_size: int = 100):
        """Initialize ring buffer.
        
        Args:
            max_size: Maximum number of entries
        """
        self.max_size = max_size
        self.buffer: deque = deque(maxlen=max_size)
    
    def push(self, value: float):
        """Add value to buffer.
        
        Args:
            value: Metric value (e.g., span duration in ms)
        """
        self.buffer.append(value)
    
    def get_all(self) -> List[float]:
        """Get all values in buffer.
        
        Returns:
            List of values in insertion order
        """
        return list(self.buffer)
    
    def is_full(self) -> bool:
        """Check if buffer is at capacity."""
        return len(self.buffer) == self.max_size
    
    def mean(self) -> float:
        """Compute rolling mean."""
        if len(self.buffer) == 0:
            return 0.0
        return sum(self.buffer) / len(self.buffer)
    
    def std(self, epsilon: float = 1e-6) -> float:
        """Compute rolling standard deviation."""
        if len(self.buffer) < 2:
            return 0.0
        m = self.mean()
        variance = sum((x - m) ** 2 for x in self.buffer) / len(self.buffer)
        return (variance ** 0.5) + epsilon
    
    def percentile(self, p: float) -> float:
        """Compute percentile (e.g., p=0.95 for p95).
        
        Args:
            p: Percentile in [0, 1]
            
        Returns:
            Percentile value
        """
        if len(self.buffer) == 0:
            return 0.0
        sorted_vals = sorted(self.buffer)
        idx = int(len(sorted_vals) * p)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]
