"""Ring buffer implementation for rolling window statistics.

Maintains a fixed-size circular buffer for the last N values.
Provides efficient push/pop without frequent allocations.
"""

from typing import List, Optional


class RingBuffer:
    """Fixed-size circular buffer for streaming values.
    
    Maintains exactly `size` most recent values. When full,
    pushing a new value overwrites the oldest.
    
    Attributes:
        size: Maximum capacity
        values: Internal storage (may contain stale data beyond tail)
        head: Index of next write position
        count: Number of valid values currently stored
    """
    
    def __init__(self, size: int):
        """Initialize buffer.
        
        Args:
            size: Fixed capacity
            
        Raises:
            ValueError: if size <= 0
        """
        if size <= 0:
            raise ValueError("Buffer size must be > 0")
        self.size = size
        self.values: List[float] = [0.0] * size
        self.head = 0  # Next write position
        self.count = 0  # Number of valid values
    
    def push(self, value: float) -> None:
        """Add a value to the buffer.
        
        If buffer is full, overwrites oldest value.
        
        Args:
            value: The value to append
        """
        self.values[self.head] = value
        self.head = (self.head + 1) % self.size
        if self.count < self.size:
            self.count += 1
    
    def is_full(self) -> bool:
        """Return True if buffer has reached capacity."""
        return self.count == self.size
    
    def get_all(self) -> List[float]:
        """Return all valid values in chronological order.
        
        Returns:
            List of values from oldest to newest
        """
        if self.count == 0:
            return []
        if self.count < self.size:
            return self.values[:self.count]
        # Buffer is full; reconstruct circular order
        return self.values[self.head:] + self.values[:self.head]
    
    def __len__(self) -> int:
        """Return number of valid values in buffer."""
        return self.count
    
    def __repr__(self) -> str:
        return f"RingBuffer(size={self.size}, count={self.count}, head={self.head})"
