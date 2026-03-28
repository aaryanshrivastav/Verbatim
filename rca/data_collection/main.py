"""Application entry point and main orchestration loop."""

import argparse
import logging
import time
import json
from datetime import datetime
from typing import List

from .config import DetectionConfig
from .detector import AnomalyDetector
from .incident_cluster import IncidentCluster
from .models import AnomalyEvent, Incident


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


class DetectionPipeline:
    """End-to-end anomaly detection pipeline."""
    
    def __init__(self, config: DetectionConfig):
        """Initialize pipeline.
        
        Args:
            config: DetectionConfig instance.
        """
        self.config = config
        self.detector = AnomalyDetector(config)
        self.clusterer = IncidentCluster(config.cluster_window_seconds)
        self.incidents: List[Incident] = []
    
    def run_once(self) -> tuple:
        """Execute one detection cycle.
        
        Returns:
            Tuple of (events, incidents).
        """
        # Detect anomalies
        events = self.detector.tick()
        
        # Cluster events into incidents
        new_incidents = []
        for event in events:
            incident = self.clusterer.add_event(event)
            if incident not in new_incidents:
                new_incidents.append(incident)
        
        # Close expired incidents
        closed = self.clusterer.close_old_incidents()
        for incident in closed:
            log.info(f"Incident closed: {incident.incident_id}")
            self.incidents.append(incident)
        
        return events, new_incidents
    
    def run_loop(self, duration_seconds: int = 0):
        """Run detection loop continuously.
        
        Args:
            duration_seconds: How long to run (0 = infinite).
        """
        start_time = time.time()
        iteration = 0
        
        try:
            while True:
                iteration += 1
                log.info(f"--- Detection cycle {iteration} ---")
                
                try:
                    events, incidents = self.run_once()
                    
                    if events:
                        log.warning(f"Detected {len(events)} anomalies")
                        for event in events:
                            log.warning(f"  {event.to_dict()}")
                    
                    if incidents:
                        log.warning(f"Active incidents: {len(incidents)}")
                        for incident in incidents:
                            log.warning(f"  {incident.to_dict()}")
                    
                except Exception as e:
                    log.error(f"Detection cycle failed: {e}", exc_info=True)
                
                # Check duration
                if duration_seconds > 0:
                    elapsed = time.time() - start_time
                    if elapsed > duration_seconds:
                        log.info(f"Duration reached, stopping")
                        break
                
                # Sleep before next cycle
                time.sleep(self.config.poll_interval_seconds)
        
        except KeyboardInterrupt:
            log.info("Detection loop interrupted by user")
    
    def get_latest_incidents(self) -> List[Incident]:
        """Get all incidents (active and closed).
        
        Returns:
            List of Incident objects.
        """
        active = self.clusterer.get_active_incidents()
        return active + self.incidents


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Anomaly Detection Pipeline for Microservices"
    )
    parser.add_argument(
        "--prometheus-url",
        default="http://localhost:9090",
        help="Prometheus base URL",
    )
    parser.add_argument(
        "--latency-threshold",
        type=float,
        default=0.5,
        help="Latency anomaly threshold (0-1)",
    )
    parser.add_argument(
        "--error-threshold",
        type=float,
        default=0.5,
        help="Error rate anomaly threshold (0-1)",
    )
    parser.add_argument(
        "--severity-threshold",
        type=float,
        default=0.8,
        help="Severity threshold for incident (0-1)",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=60,
        help="Ring buffer size (# of samples)",
    )
    parser.add_argument(
        "--warmup-seconds",
        type=int,
        default=600,
        help="Warm-up period (seconds)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=1,
        help="Detection poll interval (seconds)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="Run for N seconds (0 = infinite)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one cycle and exit",
    )
    
    args = parser.parse_args()
    
    # Build config
    config = DetectionConfig(
        prometheus_base_url=args.prometheus_url,
        latency_threshold=args.latency_threshold,
        error_threshold=args.error_threshold,
        severity_threshold=args.severity_threshold,
        window_size=args.window_size,
        warmup_seconds=args.warmup_seconds,
        poll_interval_seconds=args.poll_interval,
    )
    
    log.info(f"Config: {config}")
    
    # Create pipeline
    pipeline = DetectionPipeline(config)
    
    if args.once:
        log.info("Running one detection cycle...")
        events, incidents = pipeline.run_once()
        
        print("\n=== EVENTS ===")
        for event in events:
            print(json.dumps(event.to_dict(), indent=2))
        
        print("\n=== INCIDENTS ===")
        for incident in incidents:
            print(json.dumps(incident.to_dict(), indent=2))
    else:
        duration = args.duration if args.duration > 0 else None
        log.info(f"Starting detection loop (duration: {duration}s)")
        pipeline.run_loop(duration_seconds=args.duration)


if __name__ == "__main__":
    main()
