"""Example RCA analysis with synthetic incident."""

import logging
from datetime import datetime, timedelta

from rca.models import Incident, AnomalyDetail
from rca.core import RCAPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_example_incident() -> Incident:
    """Create a synthetic incident for testing.
    
    Returns:
        Example Incident object
    """
    now = datetime.utcnow()
    
    incident = Incident(
        incident_id="inc-1042",
        endpoint="/checkout",
        time_window_start=now - timedelta(seconds=10),
        time_window_end=now,
        anomalies=[
            AnomalyDetail("frontend", 0.78, "latency_spike"),
            AnomalyDetail("checkout", 0.86, "latency_spike"),
            AnomalyDetail("payment-service", 0.91, "latency_spike")
        ]
    )
    
    return incident


def main():
    """Run example RCA."""
    logger.info("=== RCA Pipeline Example ===")
    
    # Create example incident
    incident = create_example_incident()
    logger.info(f"Created incident: {incident.incident_id}")
    logger.info(f"  Endpoint: {incident.endpoint}")
    logger.info(f"  Affected services: {[a.service for a in incident.anomalies]}")
    
    # Initialize pipeline
    pipeline = RCAPipeline()
    
    # Run analysis
    logger.info("Starting analysis...")
    rca_output = pipeline.analyze(incident)
    
    # Print results
    logger.info("\n=== RCA RESULTS ===")
    logger.info(f"Root Cause: {rca_output.root_cause}")
    logger.info(f"Confidence: {rca_output.confidence.value:.3f} ({rca_output.confidence.bucket})")
    logger.info(f"State Vector: {rca_output.state_vector}")
    logger.info(f"Top Candidates:")
    for i, cand in enumerate(rca_output.top_candidates, 1):
        logger.info(f"  {i}. {cand.service}: {cand.probability:.3f}")
    
    logger.info(f"\nEvidence:")
    logger.info(f"  Metrics: {len(rca_output.evidence.metrics)} entries")
    for metric in rca_output.evidence.metrics:
        logger.info(f"    - {metric}")
    
    logger.info(f"  Traces: {len(rca_output.evidence.traces)} entries")
    for trace in rca_output.evidence.traces:
        logger.info(f"    - {trace}")
    
    logger.info(f"  Logs: {len(rca_output.evidence.logs)} entries")
    for log in rca_output.evidence.logs:
        logger.info(f"    - {log}")
    
    # Print full JSON
    logger.info(f"\n=== FULL JSON OUTPUT ===")
    logger.info(rca_output.json(indent=2))


if __name__ == "__main__":
    main()
