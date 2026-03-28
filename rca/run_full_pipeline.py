"""End-to-end pipeline: Collect incidents → Generate training data → Train ML Ranker.

Full workflow:
  1. collect_dataset.py: Detection (via Prometheus) → Incidents
  2. generate_training_data.py: Incidents → Modules A/B/C → Training Examples
  3. train_ml_ranker.py: Training Examples → Trained Model (Module D)
"""

import sys
import logging
import argparse
from pathlib import Path

from rca.collect_dataset import IncidentDatasetCollector
from rca.generate_training_data import TrainingDataGenerator
from rca.train_ml_ranker import MLRankerTrainer


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


class FullPipeline:
    """End-to-end pipeline orchestrator."""
    
    def __init__(
        self,
        output_dir: str = "training_data",
        prometheus_url: str = "http://localhost:9090",
    ):
        """Initialize pipeline.
        
        Args:
            output_dir: Output directory for all generated files.
            prometheus_url: Prometheus URL for metrics collection.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.prometheus_url = prometheus_url
    
    def stage_1_collect_incidents(self, duration_seconds: int = 300) -> int:
        """Stage 1: Collect incidents from detection module.
        
        Args:
            duration_seconds: Duration to run detection.
            
        Returns:
            Number of incidents collected.
        """
        log.info("=" * 70)
        log.info("STAGE 1: COLLECT INCIDENTS (Detection Module)")
        log.info("=" * 70)
        
        collector = IncidentDatasetCollector(output_dir=str(self.output_dir))
        collector.config.prometheus_base_url = self.prometheus_url
        
        count = collector.collect(duration_seconds=duration_seconds)
        
        if count == 0:
            log.error("Stage 1 failed: No incidents collected")
            return 0
        
        log.info(f"✓ Stage 1 complete: {count} incidents collected")
        return count
    
    def stage_2_generate_training_data(self) -> int:
        """Stage 2: Generate training data from incidents via Modules A/B/C.
        
        Returns:
            Number of training examples generated.
        """
        log.info("=" * 70)
        log.info("STAGE 2: GENERATE TRAINING DATA (Modules A → B → C)")
        log.info("=" * 70)
        
        generator = TrainingDataGenerator(
            incidents_file=str(self.output_dir / "incidents.jsonl"),
            output_dir=str(self.output_dir),
        )
        
        count = generator.generate(skip_errors=True)
        
        if count == 0:
            log.error("Stage 2 failed: No training examples generated")
            return 0
        
        log.info(f"✓ Stage 2 complete: {count} training examples generated")
        return count
    
    def stage_3_train_ml_ranker(self, test_split: float = 0.2) -> bool:
        """Stage 3: Train ML Ranker on training data.
        
        Args:
            test_split: Fraction of data for testing.
            
        Returns:
            True if training succeeded.
        """
        log.info("=" * 70)
        log.info("STAGE 3: TRAIN ML RANKER (Module D)")
        log.info("=" * 70)
        
        trainer = MLRankerTrainer(
            training_examples_file=str(self.output_dir / "training_examples.jsonl"),
            model_output_dir="models",
        )
        
        success = trainer.run(test_split=test_split)
        
        if not success:
            log.error("Stage 3 failed: Model training unsuccessful")
            return False
        
        log.info("✓ Stage 3 complete: ML Ranker trained")
        return True
    
    def run(
        self,
        collection_duration: int = 300,
        test_split: float = 0.2,
    ) -> bool:
        """Run full pipeline.
        
        Args:
            collection_duration: Duration for incident collection (seconds).
            test_split: Fraction for model testing.
            
        Returns:
            True if all stages succeeded.
        """
        log.info("")
        log.info("#" * 70)
        log.info("# FULL PIPELINE: Detection → Training Data → Model Training")
        log.info("#" * 70)
        log.info("")
        
        try:
            # Stage 1: Collect
            incident_count = self.stage_1_collect_incidents(duration_seconds=collection_duration)
            if incident_count == 0:
                log.error("Pipeline failed at Stage 1")
                return False
            
            log.info("")
            
            # Stage 2: Generate training data
            example_count = self.stage_2_generate_training_data()
            if example_count == 0:
                log.error("Pipeline failed at Stage 2")
                return False
            
            log.info("")
            
            # Stage 3: Train model
            if not self.stage_3_train_ml_ranker(test_split=test_split):
                log.error("Pipeline failed at Stage 3")
                return False
            
            # Success
            log.info("")
            log.info("#" * 70)
            log.info("# PIPELINE COMPLETE ✓")
            log.info("#" * 70)
            log.info(f"  Incidents collected: {incident_count}")
            log.info(f"  Training examples: {example_count}")
            log.info(f"  Model saved: models/ml_ranker_model.pkl")
            log.info("#" * 70)
            log.info("")
            
            return True
        
        except Exception as e:
            log.error(f"Pipeline failed: {e}", exc_info=True)
            return False


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Full pipeline: Collect incidents → Generate training data → Train ML Ranker"
    )
    parser.add_argument(
        "--prometheus-url",
        default="http://localhost:9090",
        help="Prometheus URL"
    )
    parser.add_argument(
        "--output-dir",
        default="training_data",
        help="Output directory for datasets and models"
    )
    parser.add_argument(
        "--collection-duration",
        type=int,
        default=300,
        help="Duration to collect incidents (seconds, default: 5 min)"
    )
    parser.add_argument(
        "--test-split",
        type=float,
        default=0.2,
        help="Test set fraction (default: 0.2)"
    )
    parser.add_argument(
        "--stage",
        choices=["all", "1", "2", "3"],
        default="all",
        help="Which stage(s) to run (default: all)"
    )
    
    args = parser.parse_args()
    
    # Create pipeline
    pipeline = FullPipeline(
        output_dir=args.output_dir,
        prometheus_url=args.prometheus_url,
    )
    
    # Run selected stage(s)
    success = False
    
    if args.stage in ["all", "1"]:
        incident_count = pipeline.stage_1_collect_incidents(duration_seconds=args.collection_duration)
        if incident_count == 0:
            sys.exit(1)
    
    if args.stage in ["all", "2"]:
        example_count = pipeline.stage_2_generate_training_data()
        if example_count == 0:
            sys.exit(1)
    
    if args.stage in ["all", "3"]:
        success = pipeline.stage_3_train_ml_ranker(test_split=args.test_split)
    
    if not success and args.stage != "1" and args.stage != "2":
        sys.exit(1)


if __name__ == "__main__":
    main()
