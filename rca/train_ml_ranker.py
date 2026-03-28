"""Train Module D (ML Ranker) on generated training examples.

Uses training examples (with state vectors from Module C)
to train a machine learning model for ranking root cause candidates.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from rca.ml_ranker import MLRanker, train_model, evaluate_model


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


class MLRankerTrainer:
    """Train ML Ranker on incident dataset."""
    
    def __init__(
        self,
        training_examples_file: str = "training_data/training_examples.jsonl",
        model_output_dir: str = "models",
    ):
        """Initialize trainer.
        
        Args:
            training_examples_file: Path to training examples JSONL (from generate_training_data.py).
            model_output_dir: Directory to save trained models.
        """
        self.training_examples_file = Path(training_examples_file)
        self.model_output_dir = Path(model_output_dir)
        self.model_output_dir.mkdir(parents=True, exist_ok=True)
        
        self.model_path = self.model_output_dir / "ml_ranker_model.pkl"
        self.metrics_path = self.model_output_dir / "training_metrics.json"
        
        log.info(f"Trainer initialized")
        log.info(f"Input: {self.training_examples_file}")
        log.info(f"Model output: {self.model_path}")
    
    def load_training_examples(self) -> List[Dict[str, Any]]:
        """Load training examples from JSONL file.
        
        Returns:
            List of training examples.
            
        Raises:
            FileNotFoundError: If file not found.
            ValueError: If file is empty or invalid.
        """
        if not self.training_examples_file.exists():
            raise FileNotFoundError(f"Training file not found: {self.training_examples_file}")
        
        examples = []
        
        with open(self.training_examples_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                
                try:
                    example = json.loads(line)
                    examples.append(example)
                except json.JSONDecodeError as e:
                    log.warning(f"  Line {line_num}: Invalid JSON, skipping")
        
        if not examples:
            raise ValueError("No valid training examples found")
        
        log.info(f"✓ Loaded {len(examples)} training examples")
        
        # Log sample
        if examples:
            sample = examples[0]
            log.debug(f"  Sample: incident={sample.get('incident_id')}, "
                     f"state_vector_dims={len(sample.get('state_vector', []))}")
        
        return examples
    
    def prepare_training_data(self, examples: List[Dict[str, Any]]) -> tuple:
        """Prepare X (features) and y (labels) for training.
        
        Args:
            examples: List of training examples.
            
        Returns:
            Tuple of (X, y) ready for ML model training.
        """
        import numpy as np
        
        X = []  # State vectors
        y = []  # Labels (root cause ranks)
        
        for example in examples:
            state_vector = example.get('state_vector', [])
            
            if not state_vector or not isinstance(state_vector, (list, tuple)):
                log.warning(f"  Skipping {example.get('incident_id')}: invalid state vector")
                continue
            
            X.append(state_vector)
            
            # Extract labels (if available from expert annotation)
            # Format: [root_cause_candidate_1_rank, root_cause_candidate_2_rank, ...]
            # For now, use placeholder (uniform distribution)
            labels = example.get('labels', {})
            if labels:
                # Use provided labels
                y.append(labels)
            else:
                # Placeholder: equal weight to all anomalies
                # Will be refined with expert annotation
                y.append(None)
        
        X = np.array(X, dtype=np.float32)
        
        log.info(f"Training data shape: X={X.shape}")
        log.info(f"  - {len(X)} examples")
        log.info(f"  - {X.shape[1]} state vector dimensions")
        
        return X, y
    
    def train(
        self,
        examples: List[Dict[str, Any]],
        test_split: float = 0.2,
        **kwargs
    ) -> Dict[str, Any]:
        """Train ML Ranker model.
        
        Args:
            examples: List of training examples (with state vectors).
            test_split: Fraction for test set.
            **kwargs: Additional arguments for trainer.
            
        Returns:
            Training metrics dict.
        """
        log.info("Preparing training data...")
        X, y = self.prepare_training_data(examples)
        
        if len(X) == 0:
            raise ValueError("No valid training data prepared")
        
        log.info(f"Training ML Ranker model...")
        
        # Train model using Module D
        ranker = MLRanker()
        
        metrics = train_model(
            ranker,
            X=X,
            y=y,
            test_split=test_split,
            **kwargs
        )
        
        # Save trained model
        log.info(f"Saving model to {self.model_path}...")
        ranker.save(str(self.model_path))
        
        return metrics
    
    def run(self, test_split: float = 0.2) -> bool:
        """Execute full training pipeline.
        
        Args:
            test_split: Fraction for test set.
            
        Returns:
            True if training succeeded, False otherwise.
        """
        try:
            # Load training examples
            log.info("Loading training examples...")
            examples = self.load_training_examples()
            
            # Train model
            log.info("Training model...")
            metrics = self.train(examples, test_split=test_split)
            
            # Save metrics
            log.info(f"Saving metrics to {self.metrics_path}...")
            with open(self.metrics_path, 'w') as f:
                json.dump(metrics, f, indent=2)
            
            # Summary
            log.info("=" * 70)
            log.info("MODULE D (ML RANKER) TRAINING COMPLETE")
            log.info(f"  Training examples: {len(examples)}")
            log.info(f"  Model saved: {self.model_path}")
            log.info(f"  Metrics saved: {self.metrics_path}")
            
            if metrics:
                log.info("  Training metrics:")
                for key, value in metrics.items():
                    if isinstance(value, float):
                        log.info(f"    - {key}: {value:.4f}")
                    else:
                        log.info(f"    - {key}: {value}")
            
            log.info("=" * 70)
            
            return True
        
        except Exception as e:
            log.error(f"Training failed: {e}", exc_info=True)
            return False


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Train ML Ranker (Module D) on generated training examples"
    )
    parser.add_argument(
        "--training-file",
        default="training_data/training_examples.jsonl",
        help="Path to training examples JSONL file"
    )
    parser.add_argument(
        "--model-dir",
        default="models",
        help="Directory to save trained model"
    )
    parser.add_argument(
        "--test-split",
        type=float,
        default=0.2,
        help="Fraction of data to use for testing (default: 0.2)"
    )
    
    args = parser.parse_args()
    
    # Create trainer
    trainer = MLRankerTrainer(
        training_examples_file=args.training_file,
        model_output_dir=args.model_dir,
    )
    
    # Run training
    success = trainer.run(test_split=args.test_split)
    
    if success:
        log.info("✓ Model ready for inference on new incidents")
    else:
        log.error("✗ Training failed")


if __name__ == "__main__":
    main()
