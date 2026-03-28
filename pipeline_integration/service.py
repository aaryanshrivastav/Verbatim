"""End-to-end orchestration for Detection -> Decision -> Executor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from decision_engine.events import EventPublisher, InMemoryEventPublisher
from decision_engine.models import DecisionBlockedOutput, DecisionOutput, DecisionSkippedOutput
from decision_engine.registry import DecisionRegistry
from decision_engine.service import DecisionEngine, DecisionEngineConfig
from remediation_executor.models import ExecutionLog, ExecutorRequest
from remediation_executor.service import RemediationExecutor, RemediationExecutorConfig

from pipeline_integration.adapter import DetectionIncidentAdapter, IncidentAdapterConfig


@dataclass
class IntegratedPipelineConfig:
    """Configuration for the temporary integrated pipeline."""

    q_table_path: str | Path = Path("decision_engine") / "artifacts" / "q_table.pkl"
    compose_file: str | Path = "docker-compose.yml"
    cooldown_seconds: int = 60
    max_in_flight: int = 2


class IntegratedPipeline:
    """Coordinates the currently available components with a temporary RCA shim."""

    def __init__(
        self,
        config: Optional[IntegratedPipelineConfig] = None,
        adapter: Optional[DetectionIncidentAdapter] = None,
        decision_engine: Optional[DecisionEngine] = None,
        executor: Optional[RemediationExecutor] = None,
        registry: Optional[DecisionRegistry] = None,
        publisher: Optional[EventPublisher] = None,
    ) -> None:
        self.config = config or IntegratedPipelineConfig()
        self.publisher = publisher or InMemoryEventPublisher()
        self.registry = registry or DecisionRegistry(
            cooldown_seconds=self.config.cooldown_seconds,
            max_in_flight=self.config.max_in_flight,
        )
        self.adapter = adapter or DetectionIncidentAdapter(IncidentAdapterConfig())
        self.decision_engine = decision_engine or DecisionEngine(
            DecisionEngineConfig(
                q_table_path=self.config.q_table_path,
                cooldown_seconds=self.config.cooldown_seconds,
                max_in_flight=self.config.max_in_flight,
            ),
            registry=self.registry,
            publisher=self.publisher,
        )
        self.executor = executor or RemediationExecutor(
            RemediationExecutorConfig(compose_file=self.config.compose_file),
            registry=self.registry,
            publisher=self.publisher,
        )

    async def handle_detection_tick(self, tick_result: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """Process every incident emitted by one Detection tick."""
        outcomes = []
        for incident in tick_result.get("incidents", []):
            outcomes.append(await self.handle_incident(incident))
        return outcomes

    async def handle_incident(self, incident: Mapping[str, Any]) -> Dict[str, Any]:
        """Adapt a Detection incident, run Decision, then execute if actionable."""
        rca_output = self.adapter.adapt(incident)
        decision = self.decision_engine.process(rca_output)
        result: Dict[str, Any] = {
            "incident_id": rca_output.incident_id,
            "rca_output": rca_output.model_dump(mode="json"),
            "decision": self._serialize_decision(decision),
            "execution_log": None,
        }

        if isinstance(decision, DecisionOutput):
            executor_request = ExecutorRequest.from_decision_output(
                decision,
                incident_started_at=rca_output.incident_started_at,
                detection_timestamp=rca_output.incident_started_at,
            )
            execution_log = await self.executor.execute(executor_request)
            result["execution_log"] = execution_log.model_dump(mode="json")

        return result

    @staticmethod
    def _serialize_decision(
        decision: DecisionOutput | DecisionBlockedOutput | DecisionSkippedOutput,
    ) -> Dict[str, Any]:
        return decision.model_dump(mode="json")
