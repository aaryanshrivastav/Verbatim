"""Anomaly scoring engine using z-score normalization.

Computes z-scores, normalized scores, and combined severity.
Uses ring buffers and rolling statistics from stream state.
"""

import logging
from typing import Optional

from detection.models import StreamState
from detection.rolling_stats import RollingStats

logger = logging.getLogger(__name__)


class AnomalyScorer:
    """Computes anomaly scores for metric streams.
    
    Attributes:
        z_max: Z-score clipping value (typically 3.0)
    """
    
    def __init__(self, z_max: float = 3.0):
        """Initialize scorer.
        
        Args:
            z_max: Z-score clipping for normalization
        """
        self.z_max = z_max
    
    def z_score(self, value: float, mean: float, std: float, epsilon: float = 1e-6) -> float:
        """Compute standardized z-score.
        
        z = (x - mu) / (sigma + epsilon)
        
        Args:
            value: The observation
            mean: Rolling mean
            std: Rolling standard deviation
            epsilon: Small constant to avoid division by zero
            
        Returns:
            Z-score (may be negative or very large)
        """
        denominator = std + epsilon
        if denominator == 0:
            return 0.0
        return (value - mean) / denominator
    
    def normalized_score(self, z: float) -> float:
        """Normalize z-score to [0, 1] range.
        
        score = min(1.0, abs(z) / Z_max)
        
        Args:
            z: Raw z-score
            
        Returns:
            Normalized score in [0, 1]
        """
        return min(1.0, abs(z) / max(self.z_max, 1e-6))
    
    def score_stream(self, stream: StreamState) -> float:
        """Compute anomaly score for a stream.
        
        Uses current value in buffer (last pushed).
        Computes z-score, then normalizes.
        
        Args:
            stream: StreamState with buffer and rolling stats
            
        Returns:
            Anomaly score in [0, 1]
        """
        if len(stream.buffer) == 0:
            return 0.0
        
        current_value = stream.buffer.get_all()[-1]
        z = self.z_score(current_value, stream.rolling_mean, stream.rolling_std)
        score = self.normalized_score(z)
        
        return score
    
    def compute_severity(
        self,
        latency_score: float,
        error_score: float,
        latency_weight: float = 0.6,
        error_weight: float = 0.4
    ) -> float:
        """Combine latency and error scores into severity.
        
        severity = clip[0,1](latency_weight * latency_score + error_weight * error_score)
        
        Args:
            latency_score: Anomaly score for latency [0, 1]
            error_score: Anomaly score for error rate [0, 1]
            latency_weight: Weight for latency (typically 0.6)
            error_weight: Weight for error (typically 0.4)
            
        Returns:
            Combined severity in [0, 1]
        """
        combined = latency_weight * latency_score + error_weight * error_score
        return min(1.0, max(0.0, combined))  # Clip to [0, 1]
