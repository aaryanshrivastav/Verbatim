"""API server for RCA pipeline (optional HTTP interface)."""

import logging
from datetime import datetime, timezone
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ImportError:
    print("FastAPI not installed; install with: pip install fastapi uvicorn")

from rca.models import Incident, AnomalyDetail, RCAOutput
from rca.core import RCAPipeline
from rca.config import RCAConfig

logger = logging.getLogger(__name__)

app = FastAPI(
    title="RCA API",
    description="Root Cause Analysis for Microservice Incidents",
    version="1.0.0"
)

# Initialize pipeline at startup
pipeline = None


@app.on_event("startup")
def startup_event():
    """Initialize RCA pipeline on startup."""
    global pipeline
    config = RCAConfig()
    pipeline = RCAPipeline(config)
    logger.info("RCA API started")


class IncidentRequest(BaseModel):
    """HTTP request to RCA API."""
    incident_id: str
    endpoint: str
    time_window_start: str  # ISO 8601
    time_window_end: str    # ISO 8601
    anomalies: list  # [{service, severity, anomaly_type}, ...]


def _parse_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


@app.post("/rca/analyze", response_model=RCAOutput)
@app.post("/analyze", response_model=RCAOutput)
async def analyze_incident(request: IncidentRequest) -> RCAOutput:
    """Analyze incident and return root cause.
    
    Args:
        request: IncidentRequest
        
    Returns:
        RCAOutput with root cause and evidence
    """
    try:
        # Parse timestamps
        start = _parse_datetime(request.time_window_start)
        end = _parse_datetime(request.time_window_end)
        
        # Build incident
        incident = Incident(
            incident_id=request.incident_id,
            endpoint=request.endpoint,
            time_window_start=start,
            time_window_end=end,
            anomalies=[
                AnomalyDetail(
                    service=a["service"],
                    severity=a["severity"],
                    anomaly_type=a["anomaly_type"]
                )
                for a in request.anomalies
            ]
        )
        
        # Run analysis
        rca_output = pipeline.analyze(incident)
        
        return rca_output
    
    except Exception as e:
        logger.error(f"RCA analysis failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rca/health")
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "rca-api"
    }


if __name__ == "__main__":
    import uvicorn
    
    logging.basicConfig(level=logging.INFO)
    
    # Usage: python -m rca.api --host 0.0.0.0 --port 8001
    uvicorn.run(
        "rca.api:app",
        host="0.0.0.0",
        port=8001,
        reload=False
    )
