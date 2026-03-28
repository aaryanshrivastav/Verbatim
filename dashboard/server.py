"""
AXIOM OBSERVE — Dashboard SSE Server
FastAPI backend serving the dashboard UI and real-time SSE streams.

Streams:
  /stream/health    → service severity every 2s
  /stream/incidents → milestone events from pipeline components
  /stream/rl        → Q-table updates from Feedback Loop

REST:
  /api/incidents         → incident history
  /api/incidents/latest  → most recent incident
  /api/services/health   → current severity per service

Internal event bus: asyncio.Queue shared across pipeline components.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("dashboard")
logging.basicConfig(level=logging.INFO)

DASHBOARD_DIR = Path(__file__).parent

# ─── Event Bus ───────────────────────────────────────────────────
# Central asyncio queue. All pipeline components publish DashboardEvent
# dicts here. SSE endpoints fan-out to connected clients.

_event_bus: asyncio.Queue = asyncio.Queue(maxsize=500)

# Per-stream subscriber lists (each subscriber gets its own Queue)
_subscribers: Dict[str, List[asyncio.Queue]] = {
    "health": [],
    "incidents": [],
    "rl": [],
}

# ─── State stores ────────────────────────────────────────────────
_service_health: Dict[str, Dict[str, Any]] = {}
_incidents: deque = deque(maxlen=100)
_current_incident: Optional[Dict[str, Any]] = None
_rl_state: Dict[str, Any] = {
    "offline_episodes": 2000,
    "live_episodes": 0,
    "last_reward": None,
    "q_values": {},
    "state_vector": [0, 0, 0, 0, 0, 0],
    "q_table_size": 0,
    "chosen_action": None,
}
_start_time = time.time()


# ─── Public API for pipeline components ──────────────────────────

def publish_event(event: Dict[str, Any]) -> None:
    """Non-blocking publish from any component. Fire-and-forget."""
    try:
        _event_bus.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning("Dashboard event bus full, dropping event")


def publish_dashboard_event(event) -> None:
    """Accept a DashboardEvent pydantic model or dict."""
    if hasattr(event, "model_dump"):
        d = event.model_dump(mode="json")
    elif hasattr(event, "dict"):
        d = event.dict()
    else:
        d = dict(event)
    publish_event(d)


def get_event_bus() -> asyncio.Queue:
    """Return the event bus queue for direct usage."""
    return _event_bus


# ─── Fan-out dispatcher ─────────────────────────────────────────

async def _dispatch_loop():
    """Read from central bus and fan-out to per-stream subscribers."""
    while True:
        event = await _event_bus.get()
        stream = event.get("stream", "incidents")

        # Update internal state stores
        _update_state(stream, event)

        # Fan-out to subscribers of this stream
        subs = _subscribers.get(stream, [])
        dead = []
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            subs.remove(q)


def _update_state(stream: str, event: Dict[str, Any]):
    """Keep in-memory state current for REST endpoints."""
    global _current_incident

    if stream == "health":
        data = event.get("data", {})
        if "services" in data:
            _service_health.update(data["services"])
        elif "service" in data:
            _service_health[data["service"]] = {
                "severity": data.get("severity", 0),
                "status": data.get("status", "healthy"),
            }

    elif stream == "incidents":
        etype = event.get("type", "")
        incident_id = event.get("incident_id")

        if etype == "ANOMALY_DETECTED" and incident_id:
            _current_incident = {
                "incident_id": incident_id,
                "status": "ACTIVE",
                "milestones": [],
                "started_at": event.get("timestamp"),
            }
            _incidents.append(_current_incident)

        if _current_incident and incident_id == _current_incident.get("incident_id"):
            _current_incident["milestones"].append({
                "type": etype,
                "timestamp_relative": event.get("timestamp_relative"),
                "data": event.get("data", {}),
            })
            if etype in ("CONFIRMED_RECOVERED", "REMEDIATION_INEFFECTIVE"):
                _current_incident["status"] = "RESOLVED" if etype == "CONFIRMED_RECOVERED" else "FAILED"
                _current_incident = None

    elif stream == "rl":
        data = event.get("data", {})
        if "q_values" in data:
            _rl_state["q_values"] = data["q_values"]
        if "state" in data:
            _rl_state["state_vector"] = data["state"]
        if "chosen_action" in data:
            _rl_state["chosen_action"] = data["chosen_action"]
        if "reward" in data:
            _rl_state["last_reward"] = data["reward"]
        if "live_episodes" in data:
            _rl_state["live_episodes"] = data["live_episodes"]
        if "q_table_size" in data:
            _rl_state["q_table_size"] = data["q_table_size"]


# ─── SSE Generator ──────────────────────────────────────────────

async def _sse_generator(request: Request, stream: str):
    """Yield SSE events for a given stream. One generator per client."""
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers.setdefault(stream, []).append(q)
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                payload = json.dumps(event.get("data", event), default=str)
                yield f"data: {payload}\n\n"
            except asyncio.TimeoutError:
                # Send keepalive comment
                yield ": keepalive\n\n"
    finally:
        if q in _subscribers.get(stream, []):
            _subscribers[stream].remove(q)


async def _health_ticker(request: Request):
    """Push health state every 2 seconds, independent of event bus."""
    while True:
        if await request.is_disconnected():
            break
        uptime = time.time() - _start_time
        payload = {
            "services": _service_health,
            "request_rate": 0,
            "error_rate": 0,
            "uptime_seconds": uptime,
        }
        yield f"data: {json.dumps(payload, default=str)}\n\n"
        await asyncio.sleep(2)


# ─── FastAPI App ─────────────────────────────────────────────────

app = FastAPI(title="AXIOM OBSERVE Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    asyncio.create_task(_dispatch_loop())
    logger.info("Dashboard event dispatcher started")


# ─── SSE Endpoints ───────────────────────────────────────────────

@app.get("/stream/health")
async def stream_health(request: Request):
    return StreamingResponse(
        _health_ticker(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/stream/incidents")
async def stream_incidents(request: Request):
    return StreamingResponse(
        _sse_generator(request, "incidents"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/stream/rl")
async def stream_rl(request: Request):
    return StreamingResponse(
        _sse_generator(request, "rl"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── REST Endpoints ─────────────────────────────────────────────

@app.get("/api/incidents")
async def get_incidents():
    return {"incidents": list(_incidents)}


@app.get("/api/incidents/latest")
async def get_latest_incident():
    if _incidents:
        return _incidents[-1]
    return {"message": "No incidents recorded"}


@app.get("/api/services/health")
async def get_services_health():
    return {"services": _service_health}


@app.get("/api/rl/state")
async def get_rl_state():
    return _rl_state


# ─── Static file serving (dashboard UI) ─────────────────────────

# Serve index.html at root
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_path = DASHBOARD_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


# Mount static assets (css, js)
app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR)), name="static")


# ─── Entry point ─────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "dashboard.server:app",
        host="0.0.0.0",
        port=8050,
        reload=True,
        log_level="info",
    )
