"""Module C: Feature Builder.

Builds feature vectors for ML ranking.
"""

import logging
from typing import List

from rca.models import Candidate, FeatureVector
from rca.config import RCAConfig

logger = logging.getLogger(__name__)


class FeatureBuilder:
    """Builds feature vectors for candidates."""
    
    def __init__(self, config: RCAConfig):
        """Initialize builder.
        
        Args:
            config: RCAConfig instance
        """
        self.config = config
    
    def build_features(self, candidates: List[Candidate]) -> List[Candidate]:
        """Build/complete feature vectors for candidates.
        
        Updates each candidate's feature_vector with:
        - depth (hop distance from entrypoint)
        - is_db (1 if database service)
        - is_edge (1 if frontend/gateway)
        
        Args:
            candidates: List of Candidate objects from CandidateExtractor
            
        Returns:
            Updated candidates list
        """
        for candidate in candidates:
            service = candidate.service
            
            # Compute service properties
            depth = self.config.get_service_depth(service)
            is_db = 1 if self.config.is_database(service) else 0
            is_edge = 1 if self.config.is_edge(service) else 0
            
            # Update feature vector
            candidate.feature_vector.depth = depth
            candidate.feature_vector.is_db = is_db
            candidate.feature_vector.is_edge = is_edge
            
            logger.debug(
                f"Feature vector for {service}: "
                f"[m={candidate.feature_vector.m:.2f}, "
                f"t={candidate.feature_vector.t:.2f}, "
                f"c={candidate.feature_vector.c:.2f}, "
                f"depth={depth}, is_db={is_db}, is_edge={is_edge}]"
            )
        
        return candidates
    
    def get_feature_depth(self, service: str) -> int:
        """Compute depth (hop distance) for service."""
        return self.config.get_service_depth(service)
