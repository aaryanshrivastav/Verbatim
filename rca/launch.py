"""Quick launcher for collecting training data.

Options:
  1. Real collection: Collect from live Prometheus metrics (services must be running)
  2. Simulation: Generate synthetic incidents for testing (no services needed)
  3. Full pipeline: Collect → Generate training data → Train model
"""

import sys
import argparse
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def main():
    """Main menu."""
    parser = argparse.ArgumentParser(description="Training data collection launcher")
    parser.add_argument(
        "mode",
        choices=["real", "simulate", "pipeline"],
        help="Collection mode: real=Prometheus, simulate=synthetic, pipeline=full workflow"
    )
    parser.add_argument("--prometheus-url", default="http://localhost:9090", help="Prometheus URL")
    parser.add_argument("--duration", type=int, default=300, help="Collection duration (seconds)")
    parser.add_argument("--warmup", type=int, default=600, help="Warmup period (seconds)")
    parser.add_argument("--num-incidents", type=int, default=10, help="Num incidents to simulate")
    parser.add_argument("--output-dir", default="training_data", help="Output directory")
    
    args = parser.parse_args()
    
    if args.mode == "real":
        # Real collection from Prometheus
        log.info("Starting REAL incident collection from Prometheus...")
        log.info("Make sure:")
        log.info("  1. Services are running: docker compose up -d")
        log.info("  2. Traffic is being generated: docker compose -f docker-compose.k6.yml up -d")
        log.info("  3. Wait 10+ minutes for baselines")
        
        from rca.collect_dataset import IncidentDatasetCollector
        
        collector = IncidentDatasetCollector(output_dir=args.output_dir)
        collector.config.prometheus_base_url = args.prometheus_url
        collector.config.warmup_seconds = args.warmup
        
        count = collector.collect(duration_seconds=args.duration)
        
        if count > 0:
            log.info(f"✓ Collected {count} incidents")
        else:
            log.error("✗ No incidents collected")
            sys.exit(1)
    
    elif args.mode == "simulate":
        # Simulated incidents (for testing)
        log.info("Starting SIMULATED incident generation...")
        
        from rca.simulate_incidents import IncidentSimulator
        
        simulator = IncidentSimulator(output_dir=args.output_dir)
        count = simulator.generate(num_incidents=args.num_incidents)
        
        if count > 0:
            log.info(f"✓ Generated {count} simulated incidents")
        else:
            log.error("✗ No incidents generated")
            sys.exit(1)
    
    elif args.mode == "pipeline":
        # Full pipeline: collect → generate training data → train model
        log.info("Starting FULL PIPELINE...")
        log.info("  Stage 1: Collect incidents (real or simulate)")
        log.info("  Stage 2: Generate training data (Modules A→B→C)")
        log.info("  Stage 3: Train ML Ranker (Module D)")
        
        from rca.run_full_pipeline import FullPipeline
        
        pipeline = FullPipeline(
            output_dir=args.output_dir,
            prometheus_url=args.prometheus_url,
        )
        
        success = pipeline.run(
            collection_duration=args.duration,
            test_split=0.2,
        )
        
        if success:
            log.info("✓ Full pipeline completed successfully")
        else:
            log.error("✗ Pipeline failed")
            sys.exit(1)


if __name__ == "__main__":
    main()
