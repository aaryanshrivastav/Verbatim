"""Collect incident dataset from detection module for ML Ranker training.

This script:
1. Runs the detection module (consumes Prometheus metrics)
2. Generates AnomalyEvent objects
3. Clusters them into Incident objects
4. Saves incidents to JSONL file for training data generation
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from rca.data_collection.config import DetectionConfig
from rca.data_collection.detector import AnomalyDetector
from rca.data_collection.incident_cluster import IncidentCluster
from rca.data_collection.prometheus_client import PrometheusClient


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


class IncidentDatasetCollector:
    """Collects incidents from detection module and saves to file."""
    
    def __init__(self, output_dir: str = "training_data"):
        """Initialize collector.
        
        Args:
            output_dir: Directory to save incident dataset.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.incidents_file = self.output_dir / "incidents.jsonl"
        self.config = DetectionConfig()
        self.config.validate()
        
        log.info(f"Collector initialized")
        log.info(f"Prometheus URL: {self.config.prometheus_base_url}")
        log.info(f"Warmup period: {self.config.warmup_seconds}s")
        log.info(f"Output: {self.incidents_file}")
    
    def verify_prometheus_connectivity(self) -> bool:
        """Verify Prometheus is reachable.
        
        Returns:
            True if Prometheus is accessible, False otherwise.
        """
        try:
            client = PrometheusClient(self.config.prometheus_base_url)
            services = client.get_available_services_and_endpoints()
            
            if not services:
                log.warning("No services/endpoints found in Prometheus")
                return False
            
            log.info(f"✓ Prometheus connected. Found {len(services)} services:")
            for service, endpoints in services.items():
                log.info(f"  - {service}: {len(endpoints)} endpoints")
            
            return True
        
        except Exception as e:
            log.error(f"✗ Failed to connect to Prometheus: {e}")
            return False
    
    def collect(self, duration_seconds: int = 300) -> int:
        """Collect incidents for specified duration.
        
        Args:
            duration_seconds: How long to collect (default 5 min).
            
        Returns:
            Number of incidents collected.
        """
        # Verify Prometheus first
        if not self.verify_prometheus_connectivity():
            log.error("Cannot proceed without Prometheus connectivity")
            return 0
        
        # Initialize detection and clustering
        detector = AnomalyDetector(self.config)
        clusterer = IncidentCluster(self.config.cluster_window_seconds)
        
        start_time = datetime.utcnow()
        incidents_count = 0
        events_count = 0
        
        log.info(f"Starting incident collection for {duration_seconds} seconds...")
        log.info(f"Warm-up period: {detector.get_warmup_remaining_seconds()}s remaining")
        
        with open(self.incidents_file, 'w') as f:
            iteration = 0
            
            while True:
                iteration += 1
                now = datetime.utcnow()
                elapsed = (now - start_time).total_seconds()
                
                try:
                    # Run one detection cycle
                    events = detector.tick()
                    events_count += len(events)
                    
                    # Log warmup status
                    if detector.is_in_warmup():
                        warmup_remaining = detector.get_warmup_remaining_seconds()
                        log.info(
                            f"[{iteration}] Warm-up: {warmup_remaining}s remaining "
                            f"({len(events)} events detected but suppressed)"
                        )
                    else:
                        # Cluster events into incidents
                        for event in events:
                            incident = clusterer.add_event(event)
                            
                            # Close expired incidents and save them
                            closed = clusterer.close_old_incidents(now)
                            
                            for closed_incident in closed:
                                incident_dict = closed_incident.to_dict()
                                f.write(json.dumps(incident_dict) + '\n')
                                
                                incidents_count += 1
                                log.info(
                                    f"[{iteration}] Saved incident {closed_incident.incident_id}: "
                                    f"{closed_incident.endpoint} "
                                    f"(severity={closed_incident.max_severity():.2f})"
                                )
                        
                        # Log active incidents
                        active = clusterer.get_active_incidents(now)
                        if active:
                            log.debug(f"Active incidents: {len(active)}")
                
                except Exception as e:
                    log.error(f"Detection cycle {iteration} failed: {e}", exc_info=True)
                
                # Check if duration reached
                if elapsed >= duration_seconds:
                    log.info(f"Duration reached ({elapsed:.0f}s / {duration_seconds}s)")
                    break
                
                # Sleep before next cycle
                time.sleep(self.config.poll_interval_seconds)
        
        # Close any remaining active incidents
        final_now = datetime.utcnow()
        remaining = clusterer.close_old_incidents(final_now + time.timedelta(seconds=1000))
        
        with open(self.incidents_file, 'a') as f:
            for incident in remaining:
                incident_dict = incident.to_dict()
                f.write(json.dumps(incident_dict) + '\n')
                incidents_count += 1
        
        # Summary
        log.info("=" * 70)
        log.info("COLLECTION COMPLETE")
        log.info(f"  Duration: {(datetime.utcnow() - start_time).total_seconds():.0f}s")
        log.info(f"  Events detected: {events_count}")
        log.info(f"  Incidents clustered: {incidents_count}")
        log.info(f"  Output file: {self.incidents_file}")
        log.info("=" * 70)
        
        return incidents_count


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Collect incident dataset from Prometheus-based anomaly detection"
    )
    parser.add_argument(
        "--prometheus-url",
        default="http://localhost:9090",
        help="Prometheus base URL"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=300,
        help="Collection duration in seconds (default: 5 min)"
    )
    parser.add_argument(
        "--output-dir",
        default="training_data",
        help="Output directory for dataset"
    )
    parser.add_argument(
        "--warmup-seconds",
        type=int,
        default=600,
        help="Warmup period in seconds (default: 10 min)"
    )
    
    args = parser.parse_args()
    
    # Create collector
    collector = IncidentDatasetCollector(output_dir=args.output_dir)
    
    # Override config if needed
    collector.config.prometheus_base_url = args.prometheus_url
    collector.config.warmup_seconds = args.warmup_seconds
    
    # Collect dataset
    count = collector.collect(duration_seconds=args.duration)
    
    if count > 0:
        log.info("✓ Dataset ready for training data generation")
    else:
        log.warning("✗ No incidents collected")


if __name__ == "__main__":
    main()
