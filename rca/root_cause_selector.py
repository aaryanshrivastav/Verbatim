"""Module E: Root Cause Selection + Confidence.

Selects top candidate and computes confidence.
"""

import logging
from typing import List, Tuple

from rca.models import Candidate, ConfidenceBucket, Confidence
from rca.config import RCAConfig

logger = logging.getLogger(__name__)


class RootCauseSelector:
    """Selects root cause and confidence."""
    
    def __init__(self, config: RCAConfig):
        """Initialize selector.
        
        Args:
            config: RCAConfig instance
        """
        self.config = config
    
    def select_root_cause(
        self,
        candidates: List[Candidate]
    ) -> Tuple[Optional[Candidate], Confidence, List[Candidate]]:
        """Select root cause candidate and compute confidence.
        
        Args:
            candidates: List of ranked candidates from MLRanker
            
        Returns:
            Tuple of (root_cause, confidence, top_3_candidates)
        """
        if not candidates:
            logger.warning("No candidates available")
            return None, Confidence(value=0.0, bucket=ConfidenceBucket.LOW), []
        
        # Sort by probability (descending)
        sorted_candidates = sorted(
            candidates,
            key=lambda c: c.probability or 0.0,
            reverse=True
        )
        
        root_cause = sorted_candidates[0]
        p1 = root_cause.probability or 0.0
        p2 = sorted_candidates[1].probability or 0.0 if len(sorted_candidates) > 1 else 0.0
        
        # Compute confidence
        conf_raw = max(0.0, p1 - p2)
        
        if conf_raw >= self.config.confidence_high_threshold:
            bucket = ConfidenceBucket.HIGH
        elif conf_raw >= self.config.confidence_medium_threshold:
            bucket = ConfidenceBucket.MEDIUM
        else:
            bucket = ConfidenceBucket.LOW
        
        confidence = Confidence(value=conf_raw, bucket=bucket)
        
        logger.info(
            f"Selected root cause: {root_cause.service} "
            f"(p1={p1:.3f}, p2={p2:.3f}, conf={conf_raw:.3f}, bucket={bucket})"
        )
        
        # Return top 3 candidates
        top_3 = sorted_candidates[:3]
        
        return root_cause, confidence, top_3
