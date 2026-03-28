"""End-to-end orchestration for Components 1 -> 2 -> 3."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from detection.config import DetectionConfig
from detection.service import DetectionService
from rca.models import RCAOutput
from triage_integration.adapter import DetectionRCAAdapter, DetectionRCAAdapterConfig


@dataclass
class TriagePipelineConfig:
    """Configuration for the Detection -> RCA integration path."""

    enable_rca: bool = True
    jaeger_base_url: str = "http://localhost:16686"
    prometheus_base_url: str = "http://localhost:9090"
    loki_base_url: str = "http://localhost:3100"
    ml_model_path: str | Path = Path("models") / "ml_ranker_logistic_regression.pkl"
    fallback_on_error: bool = True


class TriagePipeline:
    """Coordinates Detection output into native RCA results."""

    def __init__(
        self,
        config: Optional[TriagePipelineConfig] = None,
        detection_service: Optional[DetectionService] = None,
        adapter: Optional[DetectionRCAAdapter] = None,
    ) -> None:
        self.config = config or TriagePipelineConfig()
        self.detection_service = detection_service or DetectionService(DetectionConfig.from_env())
        self.adapter = adapter or DetectionRCAAdapter(
            DetectionRCAAdapterConfig(
                jaeger_base_url=self.config.jaeger_base_url,
                prometheus_base_url=self.config.prometheus_base_url,
                loki_base_url=self.config.loki_base_url,
                ml_model_path=self.config.ml_model_path,
                fallback_on_error=self.config.fallback_on_error,
            )
        )

    async def handle_detection_tick(self, tick_result: Mapping[str, Any]) -> List[Dict[str, Any]]:
        outcomes = []
        for incident in tick_result.get("incidents", []):
            outcomes.append(await self.handle_incident(incident))
        return outcomes

    async def handle_incident(self, incident: Mapping[str, Any]) -> Dict[str, Any]:
        rca_output = self.adapter.analyze(incident)
        return {
            "incident_id": rca_output.incident_id,
            "endpoint": rca_output.endpoint,
            "affected_services": list(rca_output.affected_services),
            "rca_output": rca_output.model_dump(mode="json"),
        }

    async def tick_and_analyze(self) -> Dict[str, Any]:
        tick = self.detection_service.tick()
        return {
            "tick": tick,
            "outcomes": await self.handle_detection_tick(tick),
        }
