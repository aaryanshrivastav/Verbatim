"""Run full RCA pipeline (A-G) on unlabeled incident data.

Usage:
    python rca/run_full_pipeline.py --input training_data/unlabeled_incidents.jsonl
"""

import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict

from rca.models import Incident, AnomalyDetail
from rca.core import RCAPipeline
from rca.config import RCAConfig

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)


def load_incidents_from_jsonl(filepath: str) -> List[Incident]:
    """Load incidents from JSONL file.
    
    Args:
        filepath: Path to JSONL file
        
    Returns:
        List of Incident objects
    """
    incidents = []
    
    if not Path(filepath).exists():
        log.error(f"File not found: {filepath}")
        return incidents
    
    try:
        with open(filepath, 'r') as f:
            for i, line in enumerate(f):
                try:
                    data = json.loads(line)
                    
                    # Parse timestamps
                    start_dt = datetime.fromisoformat(data['time_window_start'])
                    end_dt = datetime.fromisoformat(data['time_window_end'])
                    
                    # Build anomalies
                    anomalies = [
                        AnomalyDetail(
                            service=anom['service'],
                            severity=anom['severity'],
                            anomaly_type=anom['anomaly_type']
                        )
                        for anom in data.get('anomalies', [])
                    ]
                    
                    # Build incident
                    incident = Incident(
                        incident_id=data['incident_id'],
                        endpoint=data['endpoint'],
                        time_window_start=start_dt,
                        time_window_end=end_dt,
                        anomalies=anomalies
                    )
                    
                    incidents.append(incident)
                except Exception as e:
                    log.warning(f"Failed to parse line {i+1}: {e}")
                    continue
        
        log.info(f"[OK] Loaded {len(incidents)} incidents from {filepath}")
        return incidents
    
    except Exception as e:
        log.error(f"Error reading file: {e}")
        return []


def run_pipeline_on_incidents(incidents: List[Incident]) -> List[Dict]:
    """Run RCA pipeline on all incidents.
    
    Args:
        incidents: List of Incident objects
        
    Returns:
        List of RCAOutput results (as dicts)
    """
    config = RCAConfig()
    pipeline = RCAPipeline(config)
    
    results = []
    
    log.info(f"\n{'='*70}")
    log.info(f"Running RCA Pipeline on {len(incidents)} incidents")
    log.info(f"{'='*70}\n")
    
    for idx, incident in enumerate(incidents, 1):
        try:
            log.info(f"[{idx}/{len(incidents)}] Processing {incident.incident_id}...")
            
            # Run analysis
            rca_output = pipeline.analyze(incident)
            
            # Convert to dict for storage
            result = {
                'incident_id': rca_output.incident_id,
                'endpoint': rca_output.endpoint,
                'root_cause': rca_output.root_cause,
                'confidence': {
                    'value': rca_output.confidence.value,
                    'bucket': rca_output.confidence.bucket
                },
                'top_candidates': [
                    {'service': c.service, 'probability': float(c.probability)}
                    for c in rca_output.top_candidates
                ],
                'affected_services': rca_output.affected_services,
                'original_severity': float(rca_output.original_severity),
                'time_window': rca_output.time_window,
            }
            
            results.append(result)
            
            # Log summary
            log.info(
                f"  [OK] Root Cause: {rca_output.root_cause} "
                f"({rca_output.confidence.bucket}: {rca_output.confidence.value:.3f})"
            )
            
        except Exception as e:
            log.error(f"  ✗ Analysis failed: {e}")
            results.append({
                'incident_id': incident.incident_id,
                'error': str(e),
                'root_cause': None,
                'confidence': None
            })
    
    return results


def save_results(results: List[Dict], output_file: str):
    """Save RCA results to JSONL file.
    
    Args:
        results: List of RCAOutput dicts
        output_file: Output file path
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        for result in results:
            json.dump(result, f)
            f.write('\n')
    
    log.info(f"\n[OK] Results saved to {output_file}")


def print_summary(results: List[Dict]):
    """Print summary statistics.
    
    Args:
        results: List of RCAOutput dicts
    """
    total = len(results)
    successful = len([r for r in results if 'root_cause' in r and r['root_cause']])
    failed = total - successful
    
    # Confidence distribution
    high_conf = len([r for r in results if r.get('confidence') and r['confidence'].get('bucket') == 'high'])
    med_conf = len([r for r in results if r.get('confidence') and r['confidence'].get('bucket') == 'medium'])
    low_conf = len([r for r in results if r.get('confidence') and r['confidence'].get('bucket') == 'low'])
    
    # Root cause distribution
    root_causes = {}
    for result in results:
        if result.get('root_cause'):
            root_causes[result['root_cause']] = root_causes.get(result['root_cause'], 0) + 1
    
    print(f"\n{'='*70}")
    print(f"PIPELINE SUMMARY")
    print(f"{'='*70}")
    print(f"\nResults:")
    print(f"  Total processed: {total}")
    print(f"  Successful: {successful} [OK]")
    print(f"  Failed: {failed} [FAILED]")
    
    if successful > 0:
        print(f"\nConfidence Distribution:")
        print(f"  High: {high_conf} ({100*high_conf/successful:.1f}%)")
        print(f"  Medium: {med_conf} ({100*med_conf/successful:.1f}%)")
        print(f"  Low: {low_conf} ({100*low_conf/successful:.1f}%)")
        
        print(f"\nRoot Cause Distribution (Top 10):")
        for service, count in sorted(root_causes.items(), key=lambda x: -x[1])[:10]:
            print(f"  {service}: {count} ({100*count/successful:.1f}%)")
    
    print(f"\n{'='*70}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run full RCA pipeline (A-G) on unlabeled incidents"
    )
    parser.add_argument(
        "--input",
        default="training_data/unlabeled_incidents.jsonl",
        help="Input file with unlabeled incidents"
    )
    parser.add_argument(
        "--output",
        default="results/rca_results.jsonl",
        help="Output file with RCA results"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of incidents to process (for testing)"
    )
    
    args = parser.parse_args()
    
    # 1. Load incidents
    log.info(f"Loading incidents from {args.input}...")
    incidents = load_incidents_from_jsonl(args.input)
    
    if not incidents:
        log.error("No incidents loaded. Exiting.")
        return 1
    
    # Apply limit if specified
    if args.limit:
        incidents = incidents[:args.limit]
        log.info(f"Limited to {len(incidents)} incidents")
    
    # 2. Run pipeline
    results = run_pipeline_on_incidents(incidents)
    
    # 3. Save results
    save_results(results, args.output)
    
    # 4. Print summary
    print_summary(results)
    
    log.info("Pipeline execution complete!")
    return 0


if __name__ == "__main__":
    exit(main())
