"""Generate comprehensive synthetic training dataset for Module D (ML Ranker).

This script:
1. Generates diverse failure scenarios (500+ examples covering 7 failure types)
2. Converts each scenario to Component 2 incident format with events
3. Labels each service in incident with root cause information
4. Saves to JSONL format (one incident per line) for ML training

Output Format (Component 2 Compatible):
========================================

Each JSONL line contains:
{
  "incident": {
    "incident_id": "inc-xxx",
    "endpoint": "/api/endpoint",
    "time_window_start": "2026-03-28T11:14:55Z",
    "time_window_end": "2026-03-28T11:15:05Z",
    "anomalies": [
      {
        "service": "db",
        "endpoint": "/api/endpoint",
        "anomaly_type": "latency_spike",
        "severity": 0.45,
        "detected_at": "2026-03-28T11:15:01Z",
        "latency_score": 0.88,
        "error_score": 0.12
      },
      ... more anomalies
    ]
  },
  "labels": [
    {
      "service": "db",
      "endpoint": "/api/endpoint",
      "label": 1,  // 1 = root cause, 0 = not root cause
      "confidence": 0.98,
      "method": "temporal_primacy_and_dependency",
      "reasoning": "Service db is the identified root cause...",
      "details": { ... timing, severity, dependency info ... }
    },
    ... more labels (one per service)
  ],
  "scenario_metadata": {
    "scenario_id": "...",
    "failure_type": "db_failure",
    "failure_shape": "slow_ramp",
    "root_cause_service": "db"
  }
}

Usage:
    python rca/generate_synthetic_training_data.py --output-dir training_data --scenarios 500
"""

import json
import logging
import argparse
from pathlib import Path
from typing import List

from rca.data_collection.synthetic_scenario_generator import (
    generate_diverse_scenarios,
    FailureType,
    FailureShape,
)
from rca.data_collection.root_cause_labeler import RootCauseLabelGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
)
log = logging.getLogger(__name__)


class SyntheticTrainingDataGenerator:
    """Generates complete training dataset from synthetic failure scenarios."""
    
    def __init__(self, output_dir: str = "training_data"):
        """Initialize generator.
        
        Args:
            output_dir: Directory to save generated data
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.labeler = RootCauseLabelGenerator()
    
    def generate(self, num_scenarios: int = 500, edge_case_multiplier: float = 2.0, 
                 normal_case_multiplier: float = 2.0) -> int:
        """Generate complete synthetic training dataset in Component 2 incident format.
        
        Each line in output JSONL is a complete incident with:
        - incident: Contains incident_id, endpoint, time_window, anomalies[]
        - labels: Array of service labels with confidence and reasoning
        - scenario_metadata: Original failure type/shape for reference
        
        Args:
            num_scenarios: Target number of failure scenarios to generate
            edge_case_multiplier: Multiplier for edge case generation (2.0 = double)
            normal_case_multiplier: Multiplier for normal case generation (2.0 = double)
            
        Returns:
            Total number of incidents (scenarios) generated
        """
        log.info(f"Generating {num_scenarios}+ failure scenarios...")
        log.info(f"  Edge case multiplier: {edge_case_multiplier}x")
        log.info(f"  Normal case multiplier: {normal_case_multiplier}x")
        
        # Generate scenarios with increased intensity and multipliers
        num_per_type = max(3, num_scenarios // 100)
        scenarios = generate_diverse_scenarios(
            num_per_type=num_per_type,
            include_combinations=True,
            include_edge_cases=True,
            edge_case_multiplier=edge_case_multiplier,
            include_normal_cases=True,
            normal_case_multiplier=normal_case_multiplier,
        )
        
        log.info(f"Generated {len(scenarios)} scenarios")
        log.info(f"  Breakdown by type:")
        type_counts = {}
        for s in scenarios:
            t = s.failure_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        for t, count in sorted(type_counts.items()):
            log.info(f"    {t}: {count}")
        
        # Convert scenarios to incidents with labels
        log.info(f"Converting scenarios to Component 2 incident format with labels...")
        incidents = []
        total_labels = 0
        
        for scenario in scenarios:
            incident_example = self.labeler.generate_incident_training_example(scenario)
            incidents.append(incident_example)
            total_labels += len(incident_example['labels'])
        
        log.info(f"Generated {len(incidents)} incidents with {total_labels} service labels")
        
        # Save to JSONL
        output_file = self.output_dir / "training_examples_synthetic.jsonl"
        log.info(f"Saving to {output_file}...")
        
        with open(output_file, 'w') as f:
            for incident in incidents:
                f.write(json.dumps(incident) + '\n')
        
        log.info(f"✓ Saved {len(incidents)} incidents")
        
        # Save summary statistics
        self._save_summary(scenarios, incidents)
        
        return len(incidents)
    
    def _save_summary(self, scenarios: List, incidents: List) -> None:
        """Save summary statistics about the dataset."""
        
        # Aggregate statistics from all incidents
        total_labels = 0
        positive_count = 0
        negative_count = 0
        type_dist = {}
        anomaly_dist = {}
        
        for incident in incidents:
            # Count labels
            for label in incident['labels']:
                total_labels += 1
                if label['label'] == 1:
                    positive_count += 1
                else:
                    negative_count += 1
            
            # Count by failure type
            metadata = incident.get('scenario_metadata', {})
            failure_type = metadata.get('failure_type', 'unknown')
            type_dist[failure_type] = type_dist.get(failure_type, 0) + 1
            
            # Count by anomaly type (from incident anomalies)
            for anomaly in incident['incident']['anomalies']:
                atype = anomaly['anomaly_type']
                anomaly_dist[atype] = anomaly_dist.get(atype, 0) + 1
        
        summary = {
            "total_incidents": len(incidents),
            "total_scenarios": len(scenarios),
            "total_service_labels": total_labels,
            "label_distribution": {
                "root_cause": positive_count,
                "not_root_cause": negative_count,
                "balance_ratio": positive_count / negative_count if negative_count > 0 else 0,
            },
            "failure_type_distribution": type_dist,
            "anomaly_type_distribution": anomaly_dist,
            "class_balance_analysis": {
                "note": "Binary classification is naturally imbalanced: 1 root cause per incident, N-1 non-causes",
                "positive_class_fraction": positive_count / total_labels if total_labels > 0 else 0,
                "recommendation": "Use class_weight='balanced' in LogisticRegression or RandomForest",
            },
            "format_info": {
                "structure": "Each JSONL line is an incident with Component 2 event format",
                "incident_fields": ["incident_id", "endpoint", "time_window_start", "time_window_end", "anomalies"],
                "labels_structure": "Array of {service, endpoint, label, confidence, method, reasoning}",
            },
        }
        
        summary_file = self.output_dir / "training_data_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        log.info(f"Summary saved to {summary_file}")
        log.info(f"\nDataset Summary:")
        log.info(f"  Total incidents: {len(incidents)}")
        log.info(f"  Total scenarios: {len(scenarios)}")
        log.info(f"  Total service labels: {total_labels}")
        log.info(f"  Root cause (label=1): {positive_count}")
        log.info(f"  Not root cause (label=0): {negative_count}")
        log.info(f"  Class balance: {positive_count}/{negative_count} = {positive_count/negative_count:.2f}")
        log.info(f"\n  Failure types: {len(type_dist)}")
        log.info(f"  Anomaly types: {list(anomaly_dist.keys())}")
        log.info(f"\nFormat: Component 2 incident structure with grouped labels")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic training dataset for ML Ranker (Module D)"
    )
    parser.add_argument(
        "--output-dir",
        default="training_data",
        help="Output directory for training data",
    )
    parser.add_argument(
        "--scenarios",
        type=int,
        default=500,
        help="Target number of failure scenarios to generate (will be higher with combinations and intensities)",
    )
    parser.add_argument(
        "--edge-case-multiplier",
        type=float,
        default=2.0,
        help="Multiplier for edge case generation (1.0=normal, 2.0=double, 3.0=triple)",
    )
    parser.add_argument(
        "--normal-case-multiplier",
        type=float,
        default=2.0,
        help="Multiplier for normal case generation (1.0=normal, 2.0=double, 3.0=triple)",
    )
    
    args = parser.parse_args()
    
    gen = SyntheticTrainingDataGenerator(output_dir=args.output_dir)
    count = gen.generate(
        num_scenarios=args.scenarios,
        edge_case_multiplier=args.edge_case_multiplier,
        normal_case_multiplier=args.normal_case_multiplier,
    )
    
    log.info("=" * 70)
    log.info("SYNTHETIC TRAINING DATA GENERATION COMPLETE")
    log.info("=" * 70)
    log.info(f"Output: {args.output_dir}/training_examples_synthetic.jsonl")
    log.info(f"Examples: {count}")
    log.info("")
    log.info("Next steps:")
    log.info("  1. Review training_data_summary.json for dataset statistics")
    log.info("  2. Train Module D (ML Ranker):")
    log.info("     python rca/train_ml_ranker.py --input training_data/training_examples_synthetic.jsonl")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
