"""Module D: ML Ranker.

Loads pretrained model and scores candidates.
"""

import logging
import os
import pickle
from typing import List, Optional
import numpy as np

from rca.models import Candidate
from rca.config import RCAConfig

logger = logging.getLogger(__name__)


class MLRanker:
    """ML-based candidate ranking."""
    
    def __init__(self, config: RCAConfig):
        """Initialize ranker.
        
        Loads pretrained model if available.
        
        Args:
            config: RCAConfig instance
        """
        self.config = config
        self.model = self._load_model()
        self.has_model = self.model is not None
    
    def _load_model(self):
        """Load pretrained model from pickle file.
        
        Returns:
            Loaded model or None if not found/failed
        """
        model_path = self.config.ml_model_path
        
        if not os.path.exists(model_path):
            logger.warning(f"Model not found at {model_path}, using fallback scoring")
            return None
        
        try:
            with open(model_path, "rb") as f:
                model = pickle.load(f)
            logger.info(f"Loaded ML model from {model_path}")
            return model
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return None
    
    def rank_candidates(self, candidates: List[Candidate]) -> List[Candidate]:
        """Score candidates using ML model or fallback.
        
        Args:
            candidates: List of Candidate objects from FeatureBuilder
            
        Returns:
            Candidates with .probability set
        """
        if self.has_model:
            return self._rank_with_model(candidates)
        else:
            return self._rank_with_fallback(candidates)
    
    def _rank_with_model(self, candidates: List[Candidate]) -> List[Candidate]:
        """Rank candidates using pretrained ML model.
        
        Args:
            candidates: List of candidates
            
        Returns:
            Candidates with probabilities set
        """
        for candidate in candidates:
            try:
                # Get feature vector as numpy array
                features = np.array([candidate.feature_vector.to_array()])
                
                # Predict probability (assuming binary classifier)
                if hasattr(self.model, 'predict_proba'):
                    proba = self.model.predict_proba(features)[0]
                    # proba is [prob_negative, prob_positive]
                    candidate.probability = float(proba[1])
                else:
                    # Fallback: decision function
                    score = self.model.predict(features)[0]
                    candidate.probability = float(score)
                
                logger.debug(
                    f"ML ranked {candidate.service}: p={candidate.probability:.3f}"
                )
            except Exception as e:
                logger.error(f"ML ranking failed for {candidate.service}: {e}")
                # Fall back to heuristic
                candidate.probability = self._compute_fallback_score(candidate)
        
        return candidates
    
    def _rank_with_fallback(self, candidates: List[Candidate]) -> List[Candidate]:
        """Rank candidates using heuristic fallback.
        
        score = 0.5*m + 0.4*t + 0.1*c
        
        Args:
            candidates: List of candidates
            
        Returns:
            Candidates with fallback_score set
        """
        for candidate in candidates:
            candidate.probability = self._compute_fallback_score(candidate)
            candidate.fallback_score = candidate.probability
            logger.debug(
                f"Fallback scored {candidate.service}: "
                f"p={candidate.probability:.3f}"
            )
        
        return candidates
    
    @staticmethod
    def _compute_fallback_score(candidate: Candidate) -> float:
        """Compute fallback heuristic score.
        
        score = 0.5*m + 0.4*t + 0.1*c
        
        Args:
            candidate: Candidate object
            
        Returns:
            Score in [0, 1]
        """
        fv = candidate.feature_vector
        score = (
            0.5 * fv.m +
            0.4 * fv.t +
            0.1 * fv.c
        )
        return min(1.0, max(0.0, score))
