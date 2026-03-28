"""HTTP client for consuming the running Detection service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import requests


@dataclass
class DetectionClientConfig:
    """Minimal config surface needed by the integrated runner."""

    poll_interval_seconds: int = 1


class DetectionApiClient:
    """Lightweight client for the external Detection API."""

    def __init__(self, base_url: str = "http://localhost:8010", timeout_seconds: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.config = DetectionClientConfig()
        self.refresh_status()

    def refresh_status(self) -> Dict[str, Any]:
        """Refresh remote Detection status and sync runner-relevant config."""
        response = requests.get(f"{self.base_url}/status", timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        poll_interval = payload.get("config", {}).get("poll_interval_seconds")
        if isinstance(poll_interval, int) and poll_interval > 0:
            self.config.poll_interval_seconds = poll_interval
        return payload

    def tick(self) -> Dict[str, Any]:
        """Run one detection tick through the external Detection API."""
        response = requests.post(f"{self.base_url}/tick", timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()
