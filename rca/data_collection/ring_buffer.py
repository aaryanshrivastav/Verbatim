"""Fixed-size circular ring buffer for rolling metric windows.

Provides O(1) push and O(N) read operations.
"""

from typing import List


class RingBuffer:
    """Fixed-size circular buffer for maintaining metric windows."""
    
    def __init__(self, size: int):
        """Initialize ring buffer.
        
        Args:
            size: Maximum number of values to store.
            
        Raises:
            ValueError: If size <= 0.
        """
        if size <= 0:
            raise ValueError("Buffer size must be positive")
        
        self.size = size
        self.buffer = [0.0] * size
        self.head = 0  # Index of next write position
        self.count = 0  # Number of values currently in buffer
    
    def push(self, value: float):
        """Add a value to the buffer (O(1)).
        
        If buffer is full, oldest value is overwritten.
        """
        self.buffer[self.head] = value
        self.head = (self.head + 1) % self.size
        
        if self.count < self.size:
            self.count += 1
    
    def get_all(self) -> List[float]:
        """Return all values in order (oldest to newest) (O(N))."""
        if self.count == 0:
            return []
        
        if self.count < self.size:
            # Buffer not yet full, just return first 'count' elements
            return self.buffer[:self.count]
        
        # Buffer full: reconstruct in chronological order
        # Values from head to end, then 0 to head-1
        result = []
        for i in range(self.size):
            result.append(self.buffer[(self.head + i) % self.size])
        return result
    
    def is_full(self) -> bool:
        """Check if buffer has reached capacity."""
        return self.count == self.size
    
    def __len__(self) -> int:
        """Return current number of values in buffer."""
        return self.count
    
    def mean(self) -> float:
        """Compute mean of buffer values (O(N))."""
        if self.count == 0:
            return 0.0
        return sum(self.buffer[:self.count]) / self.count
    
    def std(self, epsilon: float = 1e-6) -> float:
        """Compute standard deviation of buffer values (O(N)).
        
        Args:
            epsilon: Small value to avoid division by zero.
        """
        if self.count == 0:
            return epsilon
        
        if self.count == 1:
            return epsilon
        
        values = self.get_all()
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        
        import math
        return max(epsilon, math.sqrt(variance))
