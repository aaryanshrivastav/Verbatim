"""End-to-end orchestrator: Generate unlabeled data -> Run pipeline A-G.

Quick start:
    python rca/orchestrate.py --count 150

This will:
  1. Generate 150 unlabeled incidents
  2. Run pipeline on all incidents
  3. Save results to results/rca_results.jsonl
  4. Print summary statistics
"""

import sys
import logging
import argparse
from pathlib import Path

# Add parent directory to path so RCA modules can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))

from rca.data_collection.generate_unlabeled_data import generate_unlabeled_dataset
from rca.run_full_pipeline import load_incidents_from_jsonl, run_pipeline_on_incidents, save_results, print_summary

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s'
)
log = logging.getLogger(__name__)


def generate_data(count: int = 150, output_file: str = "training_data/unlabeled_incidents.jsonl") -> bool:
    """Generate unlabeled incident data.
    
    Args:
        count: Number of incidents (100-200)
        output_file: Output file path
        
    Returns:
        True if successful, False otherwise
    """
    log.info(f"\n{'='*70}")
    log.info(f"Step 1: Generating {count} unlabeled incidents...")
    log.info(f"{'='*70}\n")
    
    try:
        result = subprocess.run(
            [
                sys.executable,
                "rca/data_collection/generate_unlabeled_data.py",
                "--count", str(count),
                "--output", output_file
            ],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=60
        )
        
        print(result.stdout)
        if result.stderr:
            log.warning(result.stderr)
        
        if result.returncode != 0:
            log.error(f"Data generation failed with exit code {result.returncode}")
            return False
        
        return True
    
    except Exception as e:
        log.error(f"Error running data generator: {e}")
        return False


def run_pipeline(input_file: str, output_file: str, limit: int = None) -> bool:
    """Run full RCA pipeline on incidents.
    
    Args:
        input_file: Input JSONL file with incidents
        output_file: Output JSONL file for results
        limit: Max incidents to process (None for all)
        
    Returns:
        True if successful, False otherwise
    """
    log.info(f"\n{'='*70}")
    log.info(f"Step 2: Running RCA pipeline (A-G)...")
    log.info(f"{'='*70}\n")
    
    try:
        cmd = [
            sys.executable,
            "rca/run_full_pipeline.py",
            "--input", input_file,
            "--output", output_file
        ]
        
        if limit:
            cmd.extend(["--limit", str(limit)])
        
        result = subprocess.run(
            cmd,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout for pipeline
        )
        
        print(result.stdout)
        if result.stderr:
            log.warning(result.stderr)
        
        if result.returncode != 0:
            log.error(f"Pipeline execution failed with exit code {result.returncode}")
            log.error(f"STDERR: {result.stderr}")
            return False
        
        return True
    
    except subprocess.TimeoutExpired:
        log.error("Pipeline execution timed out after 10 minutes")
        return False
    except Exception as e:
        log.error(f"Error running pipeline: {e}")
        return False


def main():
    """Main orchestration."""
    parser = argparse.ArgumentParser(
        description="Generate unlabeled data and run RCA pipeline end-to-end"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=150,
        help="Number of unlabeled incidents to generate (100-200)"
    )
    parser.add_argument(
        "--data-file",
        default="training_data/unlabeled_incidents.jsonl",
        help="Output file for generated incidents"
    )
    parser.add_argument(
        "--results-file",
        default="results/rca_results.jsonl",
        help="Output file for RCA results"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of incidents to process through pipeline (for testing)"
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Skip data generation and use existing file"
    )
    
    args = parser.parse_args()
    
    log.info("\n" + "="*70)
    log.info("RCA PIPELINE END-TO-END ORCHESTRATOR")
    log.info("="*70)
    log.info(f"Configuration:")
    log.info(f"  Generate incidents: {not args.skip_generation}")
    log.info(f"  Incident count: {args.count}")
    log.info(f"  Data file: {args.data_file}")
    log.info(f"  Results file: {args.results_file}")
    if args.limit:
        log.info(f"  Limit: {args.limit} incidents")
    
    # Step 1: Generate data
    if not args.skip_generation:
        log.info(f"\n{'='*70}")
        log.info(f"Step 1: Generating {args.count} unlabeled incidents...")
        log.info(f"{'='*70}\n")
        
        try:
            count = generate_unlabeled_dataset(
                count=args.count,
                output_file=args.data_file,
            )
            log.info(f"[OK] Generated {count} incidents")
        except Exception as e:
            log.error(f"Data generation failed: {e}")
            return 1
    else:
        log.info(f"Skipping data generation, using {args.data_file}")
        if not Path(args.data_file).exists():
            log.error(f"Data file not found: {args.data_file}")
            return 1
    
    # Step 2: Load incidents
    log.info(f"\nLoading incidents from {args.data_file}...")
    incidents = load_incidents_from_jsonl(args.data_file)
    
    if not incidents:
        log.error("No incidents loaded. Exiting.")
        return 1
    
    # Apply limit if specified
    if args.limit:
        incidents = incidents[:args.limit]
        log.info(f"Limited to {len(incidents)} incidents")
    
    # Step 3: Run pipeline
    log.info(f"\n{'='*70}")
    log.info(f"Step 2: Running RCA pipeline (A-G)...")
    log.info(f"{'='*70}\n")
    
    try:
        results = run_pipeline_on_incidents(incidents)
    except Exception as e:
        log.error(f"Pipeline execution failed: {e}")
        return 1
    
    # Step 4: Save results
    save_results(results, args.results_file)
    
    # Step 5: Print summary
    print_summary(results)
    
    # Done
    log.info("\n" + "="*70)
    log.info("[OK] END-TO-END EXECUTION COMPLETE")
    log.info("="*70)
    log.info(f"Results saved to: {args.results_file}")
    log.info(f"\nTo view results:")
    log.info(f"  python -c \"import json; [print(json.dumps(json.loads(line), indent=2)) for i, line in enumerate(open('{args.results_file}')) if i < 3]\"")
    log.info("")
    
    return 0


if __name__ == "__main__":
    exit(main())
