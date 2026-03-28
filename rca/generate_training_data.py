"""Generate training examples for ML Ranker by processing incidents through RCA modules.

Pipeline:
  Incidents (from collect_dataset.py)
    ↓
  Module A: Trace Graph Builder (build_from_incident)
    ↓
  Module B: Feature Builder (extract_from_graph)
    ↓
  Module C: State Vector (vectorize)
    ↓
  Training Examples (for Module D: ML Ranker)
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from rca.trace_graph_builder import build_from_incident
from rca.feature_builder import extract_features
from rca.state_vector import build_state_vector


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


class TrainingDataGenerator:
    """Generates training examples by running incidents through Modules A→B→C."""
    
    def __init__(
        self,
        incidents_file: str = "training_data/incidents.jsonl",
        output_dir: str = "training_data",
    ):
        """Initialize generator.
        
        Args:
            incidents_file: Path to incidents JSONL (from collect_dataset.py).
            output_dir: Directory to save training examples.
        """
        self.incidents_file = Path(incidents_file)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.training_examples_file = self.output_dir / "training_examples.jsonl"
        self.failed_file = self.output_dir / "failed_incidents.jsonl"
        
        log.info(f"Generator initialized")
        log.info(f"Input: {self.incidents_file}")
        log.info(f"Output: {self.training_examples_file}")
    
    def verify_input_file(self) -> bool:
        """Verify incidents file exists and is readable.
        
        Returns:
            True if file exists and has incidents, False otherwise.
        """
        if not self.incidents_file.exists():
            log.error(f"Incidents file not found: {self.incidents_file}")
            return False
        
        count = 0
        with open(self.incidents_file, 'r') as f:
            for line in f:
                if line.strip():
                    count += 1
        
        if count == 0:
            log.error("Incidents file is empty")
            return False
        
        log.info(f"✓ Incidents file verified ({count} incidents)")
        return True
    
    def process_incident(self, incident_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Process single incident through Modules A → B → C.
        
        Args:
            incident_dict: Incident data (from JSONL).
            
        Returns:
            Training example dict, or None if processing failed.
            
        Raises:
            Exception: If any module fails.
        """
        incident_id = incident_dict.get('incident_id', 'unknown')
        endpoint = incident_dict.get('endpoint', 'unknown')
        
        # ============================================================
        # MODULE A: Trace Graph Builder
        # ============================================================
        # Build trace graph from incident
        # (queries Jaeger for traces related to the endpoint during the incident window)
        
        trace_graph = build_from_incident(
            incident_id=incident_id,
            endpoint=endpoint,
            time_window_start=incident_dict['time_window']['start'],
            time_window_end=incident_dict['time_window']['end'],
        )
        
        if not trace_graph:
            raise ValueError(f"Failed to build trace graph for {incident_id}")
        
        log.debug(f"  ✓ Module A: Built trace graph ({len(trace_graph.nodes)} nodes, {len(trace_graph.edges)} edges)")
        
        # ============================================================
        # MODULE B: Feature Builder
        # ============================================================
        # Extract features from trace graph (latency, error rates, etc.)
        
        features = extract_features(
            trace_graph=trace_graph,
            incident_data=incident_dict,
        )
        
        if not features:
            raise ValueError(f"Failed to extract features from {incident_id}")
        
        log.debug(f"  ✓ Module B: Extracted {len(features)} features")
        
        # ============================================================
        # MODULE C: State Vector
        # ============================================================
        # Convert features into state vector (dense representation)
        
        state_vector = build_state_vector(
            trace_graph=trace_graph,
            features=features,
        )
        
        if not state_vector:
            raise ValueError(f"Failed to build state vector for {incident_id}")
        
        log.debug(f"  ✓ Module C: Built state vector ({len(state_vector)} dimensions)")
        
        # ============================================================
        # Combine into training example
        # ============================================================
        
        training_example = {
            # Metadata
            'incident_id': incident_id,
            'endpoint': endpoint,
            'timestamp': incident_dict['time_window']['start'],
            
            # Original incident data
            'severity': incident_dict.get('severity', 0.0),
            'anomalies': incident_dict.get('anomalies', []),
            
            # Run through Modules A, B, C
            'trace_graph': trace_graph.to_dict() if hasattr(trace_graph, 'to_dict') else str(trace_graph),
            'features': features,
            'state_vector': state_vector,
            
            # For ranking (e.g., which root cause is most likely)
            # Will be populated with labels during expert review
            'labels': {},
        }
        
        return training_example
    
    def generate(self, skip_errors: bool = True) -> int:
        """Generate training examples from incident dataset.
        
        Args:
            skip_errors: If True, continue on processing errors.
            
        Returns:
            Number of training examples generated.
        """
        # Verify input file
        if not self.verify_input_file():
            return 0
        
        training_examples = []
        failed_incidents = []
        
        log.info(f"Processing incidents...")
        
        with open(self.incidents_file, 'r') as f_in:
            for line_num, line in enumerate(f_in, 1):
                incident_dict = json.loads(line)
                incident_id = incident_dict.get('incident_id', f'incident-{line_num}')
                
                try:
                    log.info(f"[{line_num}] Processing {incident_id}...")
                    
                    # Process through Modules A → B → C
                    training_example = self.process_incident(incident_dict)
                    training_examples.append(training_example)
                    
                    log.info(f"  ✓ Generated training example for {incident_id}")
                
                except Exception as e:
                    log.error(f"  ✗ Failed to process {incident_id}: {e}")
                    
                    failed_incidents.append({
                        'incident_id': incident_id,
                        'error': str(e),
                        'incident_data': incident_dict,
                    })
                    
                    if not skip_errors:
                        raise
        
        # Save training examples
        log.info(f"Saving {len(training_examples)} training examples...")
        
        with open(self.training_examples_file, 'w') as f:
            for example in training_examples:
                f.write(json.dumps(example) + '\n')
        
        log.info(f"✓ Training examples saved to {self.training_examples_file}")
        
        # Save failed incidents for review
        if failed_incidents:
            log.warning(f"Saving {len(failed_incidents)} failed incidents...")
            
            with open(self.failed_file, 'w') as f:
                for failed in failed_incidents:
                    f.write(json.dumps(failed) + '\n')
            
            log.warning(f"Failed incidents saved to {self.failed_file}")
        
        # Summary
        log.info("=" * 70)
        log.info("TRAINING DATA GENERATION COMPLETE")
        log.info(f"  Input incidents: {len(training_examples) + len(failed_incidents)}")
        log.info(f"  Successfully processed: {len(training_examples)}")
        log.info(f"  Failed: {len(failed_incidents)}")
        log.info(f"  Output file: {self.training_examples_file}")
        log.info("=" * 70)
        
        return len(training_examples)


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate training examples for ML Ranker from incidents"
    )
    parser.add_argument(
        "--incidents-file",
        default="training_data/incidents.jsonl",
        help="Path to incidents JSONL file"
    )
    parser.add_argument(
        "--output-dir",
        default="training_data",
        help="Output directory for training examples"
    )
    parser.add_argument(
        "--skip-errors",
        action="store_true",
        default=True,
        help="Continue if individual incidents fail to process"
    )
    
    args = parser.parse_args()
    
    # Create generator
    generator = TrainingDataGenerator(
        incidents_file=args.incidents_file,
        output_dir=args.output_dir,
    )
    
    # Generate training data
    count = generator.generate(skip_errors=args.skip_errors)
    
    if count > 0:
        log.info("✓ Training data ready for Module D (ML Ranker training)")
    else:
        log.error("✗ No training examples generated")


if __name__ == "__main__":
    main()
