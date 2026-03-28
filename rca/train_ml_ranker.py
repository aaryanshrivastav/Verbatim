"""Module D Training: ML Ranker for Root Cause Ranking.

This script trains a binary classifier that ranks services by root cause probability.

CORRECTIONS FOR COMPONENT 2 DATA FORMAT:
=========================================

This training script handles BOTH:
1. Component 2 incident format (NEW):
   - Structure: { incident: {...}, labels: [...], scenario_metadata: {...} }
   - Each line is one incident with multiple service labels
   - Auto-converts to flat training examples

2. Legacy flat format (for backwards compatibility):
   - Structure: { features: {...}, label: 0|1 }
   - Each line is one example

FEATURE VECTOR SPECIFICATION:
=============================

Format: [m, t, c, depth, is_db, is_edge]

Where:
  m      = metrics_severity ∈ [0,1] (normalized anomaly severity)
  t      = suspicious_span_ratio ∈ [0,1] (trace quality metric)
  c      = trace_coverage ∈ [0,1] (fraction of traces containing service)
  depth  = hop distance (-1=db, 1=frontend/gateway, 2=services)
  is_db  = 1 if database, 0 otherwise
  is_edge = 1 if frontend/gateway, 0 otherwise

This matches FeatureVector.to_array() from models.py.

TRAINING PIPELINE:
==================

Input: Component 2 incident JSONL (1500-2000 incidents, each with 3-4 service labels)
  - Total training examples: 4500-8000
  - Classes: ~1/4 root cause, ~3/4 non-root-cause (naturally imbalanced)

Model: LogisticRegression
  - Binary classification: P(root_cause | features) ∈ [0,1]
  - Trained with class_weight='balanced' to handle imbalance
  - Outputs probability scores

INFERENCE:
==========

At runtime (online detection):
  For each candidate service S in incident:
    fv = FeatureVector(m=..., t=..., c=..., depth=..., is_db=..., is_edge=...)
    features = fv.to_array()  # [m, t, c, depth, is_db, is_edge]
    p_s = model.predict_proba([features])[0][1]  # P(root_cause)
    
  Rank services by p_s (descending)

FALLBACK SCORING (if model unavailable):
=========================================

score = 0.5*m + 0.4*t + 0.1*c
Sets confidence to "low"

Usage:
    # Generate synthetic training data (Component 2 format)
    python rca/generate_synthetic_training_data.py --scenarios 500

    # Train model
    python rca/train_ml_ranker.py --input training_data/training_examples_synthetic.jsonl

    # Model saved to models/ml_ranker_logistic_regression.pkl
"""

import json
import logging
import argparse
import pickle
from pathlib import Path
from typing import List, Dict, Any, Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    roc_curve,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
)
log = logging.getLogger(__name__)


class MLRankerTrainer:
    """Trains Module D (ML Ranker) classifier."""
    
    def __init__(
        self,
        output_dir: str = "models",
    ):
        """Initialize trainer.
        
        Args:
            output_dir: Directory to save model
        """
        self.model_type = "logistic_regression"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.model = None
        self.feature_names = None
    
    def load_training_data(self, input_file: str) -> Tuple[np.ndarray, np.ndarray, List[Dict]]:
        """Load training examples from JSONL file.
        
        Supports two formats:
        1. Component 2 incident format (new):
           - incident: { incident_id, endpoint, anomalies[] }
           - labels: [ { service, label, ...details } ]
        
        2. Legacy flat format:
           - features: { state_vector, max_latency, ... }
           - label: 0 or 1
        
        Args:
            input_file: Path to JSONL file with training examples
            
        Returns:
            (X, y, examples) where:
            - X: Feature matrix [N, D] where D=6 (m, t, c, depth, is_db, is_edge)
            - y: Label vector [N]
            - examples: Original example dicts for reference
        """
        log.info(f"Loading training data from {input_file}...")
        
        raw_examples = []
        with open(input_file, 'r') as f:
            for line in f:
                if line.strip():
                    example = json.loads(line)
                    raw_examples.append(example)
        
        log.info(f"Loaded {len(raw_examples)} raw records")
        
        # Detect format and convert
        if raw_examples and 'incident' in raw_examples[0]:
            # Component 2 incident format
            log.info("Detected Component 2 incident format")
            examples = self._convert_incidents_to_examples(raw_examples)
        else:
            # Legacy flat format
            log.info("Detected legacy flat format")
            examples = raw_examples
        
        # Extract features and labels
        X = []
        y = []
        
        for example in examples:
            # Build feature vector in standard ML format: [m, t, c, depth, is_db, is_edge]
            try:
                feature_vector = self._build_feature_vector(example)
                X.append(feature_vector)
                y.append(example['label'])
            except KeyError as e:
                log.warning(f"Skipping example with missing field: {e}")
                continue
        
        # Feature names match the 6-element feature vector
        self.feature_names = ['m', 't', 'c', 'depth', 'is_db', 'is_edge']
        
        X = np.array(X, dtype=np.float32)
        y = np.array(y, dtype=np.int32)
        
        log.info(f"Extracted {len(X)} training examples")
        log.info(f"Feature matrix shape: {X.shape}")
        log.info(f"Label distribution: {np.bincount(y) if len(y) > 0 else 'empty'}")
        if len(y) > 0:
            log.info(f"  Root cause (1): {(y == 1).sum()}")
            log.info(f"  Not root cause (0): {(y == 0).sum()}")
        
        return X, y, examples
    
    def _convert_incidents_to_examples(self, incidents: List[Dict]) -> List[Dict]:
        """Convert Component 2 incident format to flat training examples.
        
        Each incident contains:
        - incident: { anomalies: [{ service, severity, ... }] }
        - labels: [ { service, label, details: { ... } } ]
        
        Output: List of flat examples with service-level features and labels
        
        Feature Mapping (for synthetic training data):
        - m (metrics_severity): From anomaly.severity
        - t (suspicious_span_ratio): From anomaly.latency_score (proxy)
        - c (trace_coverage): From details.severity_ratio (proxy - in real data would come from traces)
        - depth: Inferred from service name (db=-1, gateway/frontend=1, others=2)
        - is_db: 1 if service contains 'db'
        - is_edge: 1 if service is frontend/gateway
        
        Args:
            incidents: List of incident dicts
            
        Returns:
            List of flat training examples
        """
        examples = []
        skipped = 0
        
        for incident in incidents:
            incident_data = incident.get('incident', {})
            labels_list = incident.get('labels', [])
            anomalies = incident_data.get('anomalies', [])
            
            # Map service to anomaly for severity lookup
            anomaly_by_service = {a['service']: a for a in anomalies}
            
            # Create one example per label (per service)
            for label_entry in labels_list:
                service = label_entry.get('service', '')
                label = label_entry.get('label', 0)
                details = label_entry.get('details', {})
                
                if not service:
                    skipped += 1
                    continue
                
                # Get anomaly data for this service
                anomaly = anomaly_by_service.get(service, {})
                
                # Infer depth from service name
                if 'db' in service.lower():
                    depth_val = -1
                elif 'frontend' in service.lower() or 'gateway' in service.lower():
                    depth_val = 1
                else:
                    depth_val = 2
                
                # Build example with required fields for _build_feature_vector
                example = {
                    'service': service,
                    'label': label,
                    'incident_id': incident_data.get('incident_id', ''),
                    # Feature vector components
                    'm': float(anomaly.get('severity', 0.0)),  # metrics_severity
                    't': float(anomaly.get('latency_score', 0.0)),  # suspicious_span_ratio proxy
                    'c': float(details.get('severity_ratio', 0.5)),  # trace_coverage proxy
                    'depth': int(depth_val),  # hop distance (inferred)
                    'is_db': 1 if 'db' in service.lower() else 0,
                    'is_edge': 1 if any(x in service.lower() for x in ['frontend', 'gateway']) else 0,
                }
                
                examples.append(example)
        
        log.info(f"Converted {len(incidents)} incidents into {len(examples)} training examples")
        if skipped > 0:
            log.warning(f"Skipped {skipped} label entries with missing service name")
        
        return examples
    
    def _build_feature_vector(self, example: Dict) -> List[float]:
        """Build feature vector from example.
        
        Feature vector: [m, t, c, depth, is_db, is_edge]
        
        Args:
            example: Example dict with m, t, c, depth, is_db, is_edge fields
            
        Returns:
            List of 6 floats
        """
        # Handle both direct fields and nested 'features' dict
        if 'features' in example:
            # Legacy flat format with nested features
            features_dict = example['features']
            state_vector = features_dict.get('state_vector', [0]*6)
            
            # Map state_vector to (m, t, c) approximation
            feature_vector = [
                float(state_vector[0]),  # m
                float(features_dict.get('max_error_rate', 0.0)),  # t (error_rate as proxy)
                float(features_dict.get('mean_latency', 50.0) / 400.0),  # c (normalized latency)
                0.0,  # depth (unknown)
                0.0,  # is_db
                0.0,  # is_edge
            ]
        else:
            # Component 2 format or direct fields
            feature_vector = [
                float(example.get('m', 0.5)),
                float(example.get('t', 0.5)),
                float(example.get('c', 0.5)),
                float(example.get('depth', 0)),
                float(example.get('is_db', 0)),
                float(example.get('is_edge', 0)),
            ]
        
        return feature_vector
    
    def train(
        self,
        input_file: str,
        test_split: float = 0.2,
        random_state: int = 42,
    ):
        """Train the ML Ranker model.
        
        Args:
            input_file: Path to training data JSONL
            test_split: Fraction of data for testing
            random_state: Random seed
        """
        # Load data
        X, y, examples = self.load_training_data(input_file)
        
        # Validate data
        if len(X) < 10:
            log.warning(f"Only {len(X)} training examples; recommend at least 50-100")
        
        if len(np.unique(y)) < 2:
            log.error("Training data has only one class; cannot train binary classifier")
            raise ValueError("Need both positive (root cause) and negative examples")
        
        # Split train/test with stratification
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y,
                test_size=test_split,
                random_state=random_state,
                stratify=y,
            )
        except ValueError:
            # Fallback: no stratification if classes too imbalanced
            log.warning("Stratification failed due to class imbalance; using random split")
            X_train, X_test, y_train, y_test = train_test_split(
                X, y,
                test_size=test_split,
                random_state=random_state,
                stratify=None,
            )
        
        log.info(f"Train set: {X_train.shape[0]} examples ({(y_train==1).sum()} root causes)")
        log.info(f"Test set: {X_test.shape[0]} examples ({(y_test==1).sum()} root causes)")
        
        # Validate feature vector dimensions
        if X_train.shape[1] != 6:
            log.error(f"Expected 6 features, got {X_train.shape[1]}")
            raise ValueError(f"Feature vector should have 6 dimensions [m, t, c, depth, is_db, is_edge], got {X_train.shape[1]}")
        
        # Train model (LogisticRegression)
        log.info(f"Training LogisticRegression model...")
        self.model = LogisticRegression(
            class_weight='balanced',
            max_iter=1000,
            random_state=random_state,
        )
        
        self.model.fit(X_train, y_train)
        
        # Evaluate
        self._evaluate(X_train, y_train, X_test, y_test)
        
        # Save model
        model_file = self.output_dir / f"ml_ranker_{self.model_type}.pkl"
        with open(model_file, 'wb') as f:
            pickle.dump(self.model, f)
        
        log.info(f"✓ Model saved to {model_file}")
        
        return self.model
    
    def _evaluate(self, X_train, y_train, X_test, y_test):
        """Evaluate model on train and test sets."""
        
        # Predictions
        y_train_pred = self.model.predict(X_train)
        y_test_pred = self.model.predict(X_test)
        
        # Probabilities
        y_train_proba = self.model.predict_proba(X_train)[:, 1]
        y_test_proba = self.model.predict_proba(X_test)[:, 1]
        
        # Metrics
        train_auc = roc_auc_score(y_train, y_train_proba)
        test_auc = roc_auc_score(y_test, y_test_proba)
        
        log.info("=" * 70)
        log.info("MODEL EVALUATION")
        log.info("=" * 70)
        log.info(f"\nAUC Scores:")
        log.info(f"  Train AUC: {train_auc:.4f}")
        log.info(f"  Test AUC: {test_auc:.4f}")
        
        log.info(f"\nTest Set Classification Report:")
        log.info(classification_report(y_test, y_test_pred, target_names=['not_root_cause', 'root_cause']))
        
        log.info(f"\nConfusion Matrix (Test):")
        cm = confusion_matrix(y_test, y_test_pred)
        log.info(f"  True Negatives: {cm[0, 0]}")
        log.info(f"  False Positives: {cm[0, 1]}")
        log.info(f"  False Negatives: {cm[1, 0]}")
        log.info(f"  True Positives: {cm[1, 1]}")
        
        # Feature importance (Logistic Regression coefficients)
        log.info(f"\nFeature Importance (Logistic Regression coefficients):")
        feature_importance = list(zip(self.feature_names, self.model.coef_[0]))
        feature_importance.sort(key=lambda x: abs(x[1]), reverse=True)
        for fname, importance in feature_importance[:5]:
            log.info(f"  {fname}: {importance:.4f}")
        
        return train_auc, test_auc


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Train ML Ranker (Module D)")
    parser.add_argument(
        "--input",
        default="training_data/training_examples_synthetic.jsonl",
        help="Input training data file",
    )
    parser.add_argument(
        "--output-dir",
        default="models",
        help="Output directory for model",
    )
    parser.add_argument(
        "--test-split",
        type=float,
        default=0.2,
        help="Test set fraction",
    )
    
    args = parser.parse_args()
    
    trainer = MLRankerTrainer(
        output_dir=args.output_dir,
    )
    
    trainer.train(
        input_file=args.input,
        test_split=args.test_split,
    )
    
    log.info("=" * 70)
    log.info("ML RANKER TRAINING COMPLETE")
    log.info("=" * 70)
    log.info(f"Output: {args.output_dir}/ml_ranker_logistic_regression.pkl")
    log.info("")
    log.info("To use in production:")
    log.info("  model = pickle.load(open('models/ml_ranker_logistic_regression.pkl', 'rb'))")
    log.info("  features = build_features_for_service(s)")
    log.info("  p_s = model.predict_proba([features])[0][1]")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
