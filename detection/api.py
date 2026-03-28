"""HTTP API server for anomaly detection.

FastAPI wrapper around DetectionService.
Exposes detection results via REST endpoints.
"""

import logging
import os
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from detection.config import DetectionConfig
from detection.service import DetectionService
from detection.models import AnomalyEvent, Incident

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Anomaly Detection Service",
    description="Production-ready metrics-only anomaly detection for microservices",
    version="1.0.0"
)

# Global service instance
_service: DetectionService = None


def get_service() -> DetectionService:
    """Get or create service instance."""
    global _service
    if _service is None:
        config = DetectionConfig.from_env()
        _service = DetectionService(config)
        logger.info("DetectionService initialized")
    return _service


@app.on_event("startup")
async def startup():
    """Initialize service on startup."""
    service = get_service()
    logger.info(f"Service ready: prometheus={service.config.prometheus_base_url}")


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    service = get_service()
    return {
        "status": "ok",
        "service": "anomaly-detector",
        "version": "1.0.0"
    }


@app.get("/status")
async def get_status() -> Dict[str, Any]:
    """Get service status and configuration."""
    service = get_service()
    return service.get_status()


@app.post("/tick")
async def run_detection_tick() -> Dict[str, Any]:
    """Run one detection cycle.
    
    Returns:
        Detection results (events, incidents, warmup status)
    """
    service = get_service()
    return service.tick()


@app.get("/events")
async def get_recent_events(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent anomaly events.
    
    Args:
        limit: Max number of events to return
        
    Returns:
        List of recent events
    """
    if limit <= 0 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")
    
    service = get_service()
    return service.get_recent_events(limit)


@app.get("/incidents")
async def get_recent_incidents(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent incidents.
    
    Args:
        limit: Max number of incidents to return
        
    Returns:
        List of recent incidents
    """
    if limit <= 0 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    
    service = get_service()
    return service.get_recent_incidents(limit)


@app.get("/streams/{service}/{endpoint}")
async def get_stream_state(service: str, endpoint: str) -> Dict[str, Any]:
    """Get stream state for a service endpoint.
    
    Args:
        service: Service name
        endpoint: Endpoint path
        
    Returns:
        Stream statistics (mean, std, buffer sizes)
    """
    svc = get_service()
    state = svc.get_stream_state(service, endpoint)
    
    if state is None or "error" in state:
        raise HTTPException(
            status_code=404,
            detail=f"No stream state for {service}/{endpoint}"
        )
    
    return state


@app.get("/config")
async def get_config() -> Dict[str, Any]:
    """Get current configuration."""
    service = get_service()
    return {
        "prometheus_url": service.config.prometheus_base_url,
        "latency_threshold": service.config.latency_threshold,
        "error_threshold": service.config.error_threshold,
        "severity_threshold": service.config.severity_threshold,
        "window_size": service.config.window_size,
        "z_max": service.config.z_max,
        "warmup_seconds": service.config.warmup_seconds,
        "cluster_window_seconds": service.config.cluster_window_seconds,
        "poll_interval_seconds": service.config.poll_interval_seconds,
        "latency_weight": service.config.latency_weight,
        "error_weight": service.config.error_weight,
        "dedup_cooldown_seconds": service.config.dedup_cooldown_seconds,
    }


if __name__ == "__main__":
    import uvicorn
    
    logging.basicConfig(level=logging.INFO)
    
    # Start server
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "detection.api:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )
