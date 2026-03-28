"""Entry point for anomaly detection service.

Runs detection loop continuously, publishing events and incidents.
Can be run standalone or imported as a module.
"""

import logging
import sys
import time
import json
from pathlib import Path

from detection.config import DetectionConfig
from detection.service import DetectionService


def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def run_detection_server(
    config: DetectionConfig,
    poll_interval: int = None,
    max_iterations: int = None,
    output_file: str = None
) -> None:
    """Run detection server in a loop.
    
    Args:
        config: DetectionConfig instance
        poll_interval: Override config poll interval (seconds)
        max_iterations: Stop after N iterations (for testing)
        output_file: Write events/incidents to JSON file (optional)
    """
    poll_interval = poll_interval or config.poll_interval_seconds
    
    service = DetectionService(config)
    logger = logging.getLogger(__name__)
    
    logger.info(f"Starting anomaly detection service")
    logger.info(f"Prometheus URL: {config.prometheus_base_url}")
    logger.info(f"Poll interval: {poll_interval}s")
    logger.info(f"Warming up for {config.warmup_seconds}s")
    
    iteration = 0
    
    try:
        while True:
            iteration += 1
            
            # Execute detection tick
            result = service.tick()
            
            # Log if events or incidents detected
            if result["events"]:
                logger.warning(f"Detected {len(result['events'])} anomalies")
                for event in result["events"]:
                    logger.warning(
                        f"  - {event['service']}: {event['endpoint']} "
                        f"({event['anomaly_type']}, severity={event['severity']:.2f})"
                    )
            
            if result["incidents"]:
                logger.warning(f"Created {len(result['incidents'])} incidents")
                for incident in result["incidents"]:
                    logger.warning(
                        f"  - {incident['incident_id']}: {incident['endpoint']} "
                        f"(max_severity={incident['max_severity']:.2f}, "
                        f"services={incident['affected_services']})"
                    )
            
            # If warming up, log progress
            if result["in_warmup"]:
                logger.info(f"Warming up... {result['warmup_remaining_seconds']}s remaining")
            
            # Optional: write to file
            if output_file and (result["events"] or result["incidents"]):
                _write_results_to_file(output_file, result)
            
            # Check iteration limit (for testing)
            if max_iterations and iteration >= max_iterations:
                logger.info(f"Reached max iterations ({max_iterations}), stopping")
                break
            
            # Sleep before next tick
            time.sleep(poll_interval)
    
    except KeyboardInterrupt:
        logger.info("Detection service interrupted by user")
    except Exception as e:
        logger.error(f"Detection service error: {e}", exc_info=True)
        sys.exit(1)
    
    # Final status
    logger.info(f"Detection service stopped after {iteration} iterations")
    logger.info(f"Total events: {len(service.detector.events)}")
    logger.info(f"Total incidents: {len(service.detector.incidents)}")


def _write_results_to_file(output_file: str, result: dict) -> None:
    """Append results to JSON file.
    
    Args:
        output_file: Path to output file
        result: Result dict from service.tick()
    """
    try:
        path = Path(output_file)
        
        # Append result as JSON line
        with open(path, "a") as f:
            f.write(json.dumps(result) + "\n")
    except Exception as e:
        logging.error(f"Failed to write results to {output_file}: {e}")


def main() -> None:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Anomaly Detection Service")
    parser.add_argument(
        "--prometheus-url",
        default="http://localhost:9090",
        help="Prometheus base URL"
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=1,
        help="Poll interval (seconds)"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        help="Stop after N iterations (for testing)"
    )
    parser.add_argument(
        "--output-file",
        help="Write events/incidents to JSON file"
    )
    parser.add_argument(
        "--l-thresh",
        type=float,
        default=0.5,
        help="Latency threshold"
    )
    parser.add_argument(
        "--e-thresh",
        type=float,
        default=0.5,
        help="Error threshold"
    )
    parser.add_argument(
        "--s-severe",
        type=float,
        default=0.8,
        help="Severity threshold"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    
    # Build config
    config = DetectionConfig(
        prometheus_base_url=args.prometheus_url,
        latency_threshold=args.l_thresh,
        error_threshold=args.e_thresh,
        severity_threshold=args.s_severe,
    )
    
    # Run server
    run_detection_server(
        config,
        poll_interval=args.poll_interval,
        max_iterations=args.max_iterations,
        output_file=args.output_file
    )


if __name__ == "__main__":
    main()
