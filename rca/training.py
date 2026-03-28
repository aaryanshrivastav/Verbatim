"""ML Model Training Example.

Sketch of how to train the RCA ranker model offline.
Not meant to be run as part of the main pipeline.
"""

import pickle
import logging
from typing import List, Tuple
import numpy as np

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
except ImportError:
    print("scikit-learn not installed; install with: pip install scikit-learn")

logger = logging.getLogger(__name__)


class TrainingDataGenerator:
    """Generates synthetic training data for RCA model.
    
    In production, this would come from:
    - Replaying historical incidents
    - Running chaos experiments (k6, gremlin, etc.)
    - Labeling outcomes: which service was actually the root cause
    """
    
    @staticmethod
    def generate_synthetic_dataset() -> Tuple[np.ndarray, np.ndarray]:
        """Generate synthetic training data.
        
        Each row: [m, t, c, depth, is_db, is_edge]
        Label: 1 if root cause, 0 otherwise
        
        This is a minimal example; real training would have 100s-1000s of examples.
        
        Returns:
            Tuple of (X, y) where X is features array, y is labels
        """
        # Synthetic examples (service, features, label)
        examples = [
            # Root causes (label=1)
            {"features": [0.91, 0.85, 0.9, 3, 0, 0], "label": 1},  # payment-service high metrics, high trace issues
            {"features": [0.88, 0.80, 0.85, 3, 0, 0], "label": 1},  # similar
            {"features": [0.92, 0.9, 0.95, -1, 1, 0], "label": 1},  # orders-db, database is root
            {"features": [0.85, 0.88, 0.98, -1, 1, 0], "label": 1},  # database again
            
            # Not root causes (label=0)
            {"features": [0.65, 0.2, 0.95, 2, 0, 0], "label": 0},  # checkout: low trace ratio means not root
            {"features": [0.70, 0.15, 0.9, 0, 0, 1], "label": 0},  # frontend: edge service rarely root
            {"features": [0.60, 0.1, 0.8, 1, 0, 1], "label": 0},  # gateway: also edge
            {"features": [0.55, 0.3, 0.7, 2, 0, 0], "label": 0},  # low metrics, ok traces
        ]
        
        X = np.array([ex["features"] for ex in examples], dtype=np.float32)
        y = np.array([ex["label"] for ex in examples], dtype=np.int32)
        
        return X, y
    
    @staticmethod
    def load_production_dataset() -> Tuple[np.ndarray, np.ndarray]:
        """Load production training data.
        
        In real deployment, this would:
        1. Query a data warehouse/database for historical incidents
        2. Extract features for each (incident, service) pair
        3. Load ground-truth labels (which service was actually root cause)
        
        For this sketch, we use synthetic data.
        
        Returns:
            Tuple of (X, y)
        """
        return TrainingDataGenerator.generate_synthetic_dataset()


def train_rca_model(output_path: str = "rca/models/rca_model.pkl"):
    """Train and save RCA ranker model.
    
    This is an offline task, not part of the online pipeline.
    
    Args:
        output_path: Where to save pickled model
    """
    logger.info("Starting RCA model training...")
    
    # Generate or load training data
    X, y = TrainingDataGenerator.load_production_dataset()
    
    logger.info(f"Training data: {X.shape[0]} examples, {X.shape[1]} features")
    
    # Standardize features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Train LogisticRegression (simple, interpretable)
    model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(X_scaled, y)
    
    # Evaluate
    train_accuracy = model.score(X_scaled, y)
    logger.info(f"Training accuracy: {train_accuracy:.2%}")
    
    # Alternative: RandomForestClassifier
    # model = RandomForestClassifier(n_estimators=50, random_state=42)
    # model.fit(X, y)
    
    # Save model
    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "wb") as f:
        pickle.dump(model, f)
    
    logger.info(f"Model saved to {output_path}")
    
    return model


if __name__ == "__main__":
    # Example: train model from command line
    # python -m rca.training
    logging.basicConfig(level=logging.INFO)
    train_rca_model()
