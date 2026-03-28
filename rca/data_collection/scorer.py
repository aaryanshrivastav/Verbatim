"""Anomaly scoring using z-score normalization.

Computes normalized anomaly scores and combined severity.
"""

import math


class AnomalyScorer:
    """Computes z-scores and severity scores from metric values."""
    
    def __init__(self, z_max: float = 3.0, epsilon: float = 1e-6):
        """Initialize scorer.
        
        Args:
            z_max: Maximum z-score (clipping value for normalization).
            epsilon: Small value to avoid division by zero.
        """
        self.z_max = z_max
        self.epsilon = epsilon
    
    def z_score(self, value: float, mean: float, std: float) -> float:
        """Compute z-score for a value.
        
        z = (x - mean) / (std + epsilon)
        
        Args:
            value: Observed value.
            mean: Baseline mean.
            std: Baseline standard deviation.
            
        Returns:
            Z-score (can be negative, positive, or very large).
        """
        return (value - mean) / (std + self.epsilon)
    
    def normalized_score(self, z: float) -> float:
        """Normalize z-score to [0, 1] range.
        
        score = min(1.0, |z| / z_max)
        
        Args:
            z: Z-score value.
            
        Returns:
            Normalized score in [0, 1].
        """
        abs_z = abs(z)
        score = min(1.0, abs_z / self.z_max)
        return max(0.0, min(1.0, score))  # Ensure clipping
    
    def compute_severity(
        self,
        latency_score: float,
        error_score: float,
        latency_weight: float = 0.6,
        error_weight: float = 0.4,
    ) -> float:
        """Compute combined severity from latency and error scores.
        
        severity = clip[0,1](latency_weight * latency_score + error_weight * error_score)
        
        Args:
            latency_score: Normalized latency anomaly score [0, 1].
            error_score: Normalized error anomaly score [0, 1].
            latency_weight: Weight for latency (default 0.6).
            error_weight: Weight for error (default 0.4).
            
        Returns:
            Combined severity in [0, 1].
        """
        combined = latency_weight * latency_score + error_weight * error_score
        return max(0.0, min(1.0, combined))
    
    def score_stream(
        self,
        current_latency: float,
        mean_latency: float,
        std_latency: float,
        current_error: float,
        mean_error: float,
        std_error: float,
    ) -> tuple:
        """Score a stream (latency + error) at current tick.
        
        Args:
            current_latency: Current p95 latency value.
            mean_latency: Baseline mean latency.
            std_latency: Baseline std latency.
            current_error: Current error rate value.
            mean_error: Baseline mean error rate.
            std_error: Baseline std error rate.
            
        Returns:
            Tuple of (latency_score, error_score, severity).
        """
        z_latency = self.z_score(current_latency, mean_latency, std_latency)
        z_error = self.z_score(current_error, mean_error, std_error)
        
        latency_score = self.normalized_score(z_latency)
        error_score = self.normalized_score(z_error)
        
        severity = self.compute_severity(latency_score, error_score)
        
        return latency_score, error_score, severity
