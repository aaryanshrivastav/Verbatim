"""Online rolling statistics computation.

Maintains mean and standard deviation for rolling windows.
"""

from .ring_buffer import RingBuffer


class RollingStats:
    """Compute rolling mean and std from a ring buffer."""
    
    def __init__(self, buffer: RingBuffer, epsilon: float = 1e-6):
        """Initialize rolling stats from buffer.
        
        Args:
            buffer: RingBuffer instance containing metric values.
            epsilon: Small value to avoid division by zero.
        """
        self.buffer = buffer
        self.epsilon = epsilon
    
    def mean(self) -> float:
        """Compute mean of all values in buffer."""
        if self.buffer.count == 0:
            return 0.0
        
        values = self.buffer.get_all()
        return sum(values) / len(values)
    
    def std(self) -> float:
        """Compute standard deviation of all values in buffer."""
        if self.buffer.count == 0:
            return self.epsilon
        
        if self.buffer.count == 1:
            return self.epsilon
        
        values = self.buffer.get_all()
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        
        import math
        return max(self.epsilon, math.sqrt(variance))
    
    def z_score(self, value: float, mean: float, std: float) -> float:
        """Compute z-score for a value.
        
        z = (x - mean) / (std + epsilon)
        """
        return (value - mean) / (std + self.epsilon)
