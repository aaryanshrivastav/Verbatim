"""Example simulation: demonstrate detection with synthetic metrics.

This script simulates Prometheus metrics and runs the detector
without requiring actual Prometheus instance.

Useful for:
- Testing detection logic
- Demonstrating behavior
- Tuning thresholds
- Development
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple
import random
import json

from detection.config import DetectionConfig
from detection.detector import AnomalyDetector
from detection.prometheus_client import PrometheusClient
from detection.derived_metrics import DerivedMetricsComputer
from unittest.mock import patch, MagicMock


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - [%(levelname)s] - %(message)s"
    )


class SyntheticMetricsGenerator:
    """Generate synthetic metrics for simulation."""
    
    def __init__(self, seed: int = 42, anomaly_at: int = 20):
        """Initialize generator.
        
        Args:
            seed: Random seed
            anomaly_at: Introduce anomaly at tick N
        """
        random.seed(seed)
        self.anomaly_at = anomaly_at
        self.tick = 0
        
        # Service/endpoint pairs to simulate
        self.service_endpoints = [
            ("auth-service", "/login"),
            ("auth-service", "/validate"),
            ("catalog-service", "/products"),
            ("order-service", "/create"),
            ("payment-service", "/checkout"),
            ("payment-service", "/refund"),
        ]
    
    def get_metrics(self) -> Dict[Tuple[str, str], Dict[str, float]]:
        """Generate current metrics.
        
        Returns:
            Dict mapping (service, endpoint) -> {p95_latency, error_rate, request_rate}
        """
        self.tick += 1
        result = {}
        
        for service, endpoint in self.service_endpoints:
            # Base metrics (normal state)
            base_latency = 0.050 + random.gauss(0, 0.005)  # 50ms ± 5ms
            base_error_rate = 0.01 + random.gauss(0, 0.002)  # 1% ± 0.2%
            base_request_rate = 100 + random.gauss(0, 10)  # 100 req/s ± 10
            
            # Introduce anomaly at specific tick
            if self.tick >= self.anomaly_at:
                if service == "payment-service":
                    # Payment service experiences latency spike
                    base_latency *= 5.0  # 250ms
                    base_error_rate *= 3.0  # 3%
            
            # Clip to valid ranges
            latency = max(0.0, base_latency)
            error_rate = min(1.0, max(0.0, base_error_rate))
            request_rate = max(0.0, base_request_rate)
            
            result[(service, endpoint)] = {
                "p95_latency": latency,
                "error_rate": error_rate,
                "request_rate": request_rate,
            }
        
        return result


def run_simulation(
    num_ticks: int = 50,
    anomaly_at: int = 20,
    poll_interval: float = 0.1,
) -> None:
    """Run anomaly detection simulation.
    
    Args:
        num_ticks: Number of detection cycles to run
        anomaly_at: Introduce anomaly at tick N
        poll_interval: Sleep between ticks (seconds)
    """
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Create config
    config = DetectionConfig(
        prometheus_base_url="http://localhost:9090",  # Unused in simulation
        window_size=30,  # Smaller window for faster warmup
        warmup_seconds=10,  # Shorter warmup for demo
        latency_threshold=0.5,
        error_threshold=0.5,
        severity_threshold=0.8,
    )
    
    # Create detector
    detector = AnomalyDetector(config)
    generator = SyntheticMetricsGenerator(seed=42, anomaly_at=anomaly_at)
    
    logger.info("=" * 70)
    logger.info("Starting Anomaly Detection Simulation")
    logger.info("=" * 70)
    logger.info(f"Configuration:")
    logger.info(f"  - Window size: {config.window_size} values")
    logger.info(f"  - Warmup: {config.warmup_seconds}s")
    logger.info(f"  - Thresholds: L={config.latency_threshold}, "
                f"E={config.error_threshold}, S={config.severity_threshold}")
    logger.info(f"  - Anomaly introduces at tick {anomaly_at}")
    logger.info("=" * 70)
    
    # Patch the metrics fetcher to use synthetic generator
    original_refresh = detector.computer.refresh_all
    detector.computer.refresh_all = lambda: generator.get_metrics()
    
    all_events = []
    all_incidents = []
    
    try:
        for tick in range(1, num_ticks + 1):
            # Run detection tick
            events, incidents = detector.tick()
            
            # Log tick progress
            warmup_remaining = detector.get_warmup_remaining_seconds()
            
            if warmup_remaining > 0:
                logger.info(f"[Tick {tick:2d}] WARMUP: {warmup_remaining}s remaining")
            else:
                # Count streams
                num_streams = len(detector.streams)
                logger.info(f"[Tick {tick:2d}] DETECTION: {num_streams} streams active")
            
            # Log events
            if events:
                logger.warning(f"           ⚠ {len(events)} ANOMALIES DETECTED:")
                for event in events:
                    logger.warning(
                        f"           - {event.service}:{event.endpoint} "
                        f"({event.anomaly_type}, severity={event.severity:.2f})"
                    )
                all_events.extend(events)
            
            # Log incidents
            if incidents:
                logger.warning(f"           🔴 {len(incidents)} INCIDENTS CREATED:")
                for incident in incidents:
                    logger.warning(
                        f"           - {incident.incident_id}: {incident.endpoint} "
                        f"(max_severity={incident.max_severity:.2f}, "
                        f"services={incident.affected_services})"
                    )
                all_incidents.extend(incidents)
            
            # Sleep
            time.sleep(poll_interval)
    
    except KeyboardInterrupt:
        logger.info("Simulation interrupted")
    except Exception as e:
        logger.error(f"Simulation error: {e}", exc_info=True)
    
    # Final summary
    logger.info("=" * 70)
    logger.info("Simulation Complete")
    logger.info("=" * 70)
    logger.info(f"Ticks executed: {num_ticks}")
    logger.info(f"Total anomalies detected: {len(all_events)}")
    logger.info(f"Total incidents created: {len(all_incidents)}")
    logger.info(f"Active streams: {len(detector.streams)}")
    logger.info("=" * 70)
    
    # Print events
    if all_events:
        logger.info("\nAnomalies:")
        for event in all_events:
            logger.info(
                f"  {event.timestamp.isoformat()} | "
                f"{event.service} | {event.endpoint} | "
                f"{event.anomaly_type} | severity={event.severity:.2f}"
            )
    
    # Print incidents
    if all_incidents:
        logger.info("\nIncidents:")
        for incident in all_incidents:
            logger.info(
                f"  {incident.incident_id} | {incident.endpoint} | "
                f"max_severity={incident.max_severity:.2f} | "
                f"services={incident.affected_services}"
            )
    
    logger.info("=" * 70)


def main():
    """Entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Anomaly Detection Simulation"
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=50,
        help="Number of detection cycles"
    )
    parser.add_argument(
        "--anomaly-at",
        type=int,
        default=20,
        help="Introduce anomaly at tick N"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.1,
        help="Sleep between ticks (seconds)"
    )
    
    args = parser.parse_args()
    
    run_simulation(
        num_ticks=args.ticks,
        anomaly_at=args.anomaly_at,
        poll_interval=args.poll_interval,
    )


if __name__ == "__main__":
    main()
