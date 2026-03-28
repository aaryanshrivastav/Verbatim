"""In-memory registry for cooldowns and in-flight remediation tracking."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Dict, Optional, Set


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionRegistry:
    """Tracks safety-critical state for Component 4."""

    def __init__(
        self,
        cooldown_seconds: int = 60,
        max_in_flight: int = 2,
        snapshot_path: Optional[str | Path] = None,
    ) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.max_in_flight = max_in_flight
        self.snapshot_path = Path(snapshot_path) if snapshot_path else None
        self._cooldowns: Dict[str, datetime] = {}
        self._active_incident_ids: Set[str] = set()
        self._active_services: Set[str] = set()
        self._active_remediations_in_flight = 0
        self._lock = RLock()

    def cooldown_remaining(self, service: str, now: Optional[datetime] = None) -> float:
        """Return cooldown remaining in seconds for a service."""
        now = now or _utc_now()
        with self._lock:
            last_remediation = self._cooldowns.get(service)
            if last_remediation is None:
                return 0.0
            elapsed = (now - last_remediation).total_seconds()
            return max(0.0, self.cooldown_seconds - elapsed)

    def active_count(self) -> int:
        """Return the current number of in-flight remediations."""
        with self._lock:
            return self._active_remediations_in_flight

    def is_incident_active(self, incident_id: str) -> bool:
        """Return whether an incident already has a remediation in flight."""
        with self._lock:
            return incident_id in self._active_incident_ids

    def is_service_active(self, service: str) -> bool:
        """Return whether a service is already being remediated."""
        with self._lock:
            return service in self._active_services

    def reserve(self, incident_id: str, service: str) -> None:
        """Reserve a remediation slot after safety checks pass."""
        with self._lock:
            self._active_incident_ids.add(incident_id)
            self._active_services.add(service)
            self._active_remediations_in_flight += 1

    def mark_action_fired(self, service: str, now: Optional[datetime] = None) -> None:
        """Start the cooldown timer once the executor confirms action dispatch."""
        with self._lock:
            self._cooldowns[service] = now or _utc_now()
        self.save_snapshot()

    def release(self, incident_id: str, service: str) -> None:
        """Release an incident and service after Feedback Loop closure."""
        with self._lock:
            self._active_incident_ids.discard(incident_id)
            self._active_services.discard(service)
            if self._active_remediations_in_flight > 0:
                self._active_remediations_in_flight -= 1

    def snapshot(self) -> Dict[str, object]:
        """Return a serializable snapshot of registry state."""
        with self._lock:
            return {
                "cooldown_seconds": self.cooldown_seconds,
                "max_in_flight": self.max_in_flight,
                "cooldowns": {
                    service: timestamp.isoformat()
                    for service, timestamp in self._cooldowns.items()
                },
                "active_incident_ids": sorted(self._active_incident_ids),
                "active_services": sorted(self._active_services),
                "active_remediations_in_flight": self._active_remediations_in_flight,
            }

    def save_snapshot(self) -> None:
        """Persist cooldown snapshot if a path was configured."""
        if self.snapshot_path is None:
            return
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")

    def load_snapshot(self) -> None:
        """Load persisted cooldown state if present."""
        if self.snapshot_path is None or not self.snapshot_path.exists():
            return
        payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        with self._lock:
            self._cooldowns = {
                service: datetime.fromisoformat(timestamp)
                for service, timestamp in payload.get("cooldowns", {}).items()
            }
