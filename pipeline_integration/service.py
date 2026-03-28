"""End-to-end orchestration for Detection -> RCA -> Decision -> Executor.

The pipeline now uses the full RCA Modules A-G for comprehensive root cause analysis.
"""

from __future__ import annotations

import logging
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
from pipeline_integration.rca_integration import RCAPipelineConfig

logger = logging.getLogger(__name__)


@dataclass
class IntegratedPipelineConfig:
    """Configuration for the integrated pipeline with full RCA support."""

    q_table_path: str | Path = Path("decision_engine") / "artifacts" / "q_table.pkl"
    compose_file: str | Path = "docker-compose.yml"
    cooldown_seconds: int = 60
    max_in_flight: int = 2
    
    # RCA Configuration
    enable_rca: bool = True
    jaeger_host: str = "localhost"
    jaeger_port: int = 6831
    prometheus_url: str = "http://localhost:9090"
    loki_url: str = "http://localhost:3100"
    ml_ranker_model_path: str | Path = Path("models/ml_ranker_logistic_regression.pkl")
    rca_fallback_on_error: bool = True  # Fall back to simple adapter if RCA fails


class IntegratedPipeline:
    """Coordinates Detection, full RCA pipeline (A-G), Decision Engine, and Executor.
    
    Uses comprehensive root cause analysis from RCA Modules A-G instead of
    simple fallback adapter.
    """

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
        
        # Initialize adapter with RCA configuration
        rca_config = None
        if self.config.enable_rca:
            rca_config = RCAPipelineConfig(
                jaeger_host=self.config.jaeger_host,
                jaeger_port=self.config.jaeger_port,
                prometheus_url=self.config.prometheus_url,
                loki_url=self.config.loki_url,
                ml_ranker_model_path=self.config.ml_ranker_model_path,
                fallback_on_error=self.config.rca_fallback_on_error,
            )
        
        adapter_config = IncidentAdapterConfig(
            use_full_rca=self.config.enable_rca,
            fallback_on_error=self.config.rca_fallback_on_error,
            rca_config=rca_config,
        )
        
        self.adapter = adapter or DetectionIncidentAdapter(adapter_config)
        
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
        
        logger.info(
            f"IntegratedPipeline initialized (RCA enabled: {self.config.enable_rca})"
        )

    async def handle_detection_tick(self, tick_result: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """Process every incident emitted by one Detection tick."""
        outcomes = []
        for incident in tick_result.get("incidents", []):
            outcomes.append(await self.handle_incident(incident))
        return outcomes

    async def handle_incident(self, incident: Mapping[str, Any]) -> Dict[str, Any]:
        """Adapt a Detection incident through full RCA pipeline, then run Decision and Executor.
        
        Flow:
        1. Detection incident → RCA Modules A-G analysis
        2. RCA output → Decision Engine for strategy selection
        3. If actionable → Remediation Executor for remediating actions
        
        Args:
            incident: Detection incident as dict/model
            
        Returns:
            Results dict with incident_id, rca_output, decision, execution_log
        """
        try:
            # Run RCA analysis (full pipeline A-G)
            logger.debug(f"Running RCA analysis for incident {incident.get('incident_id')}")
            rca_output = self.adapter.adapt(incident)
            
            # Run Decision Engine
            logger.debug(f"Running Decision Engine for {incident.get('incident_id')}")
            decision = self.decision_engine.process(rca_output)
            
            result: Dict[str, Any] = {
                "incident_id": rca_output.incident_id,
                "rca_output": rca_output.model_dump(mode="json"),
                "decision": self._serialize_decision(decision),
                "execution_log": None,
            }

            # Execute if actionable
            if isinstance(decision, DecisionOutput):
                logger.info(
                    f"Executing remediation for incident {rca_output.incident_id} "
                    f"(root_cause={rca_output.root_cause})"
                )
                executor_request = ExecutorRequest.from_decision_output(
                    decision,
                    incident_started_at=rca_output.incident_started_at,
                    detection_timestamp=rca_output.incident_started_at,
                )
                execution_log = await self.executor.execute(executor_request)
                result["execution_log"] = execution_log.model_dump(mode="json")
            else:
                logger.info(
                    f"Skipping execution for {rca_output.incident_id} "
                    f"(decision={decision.__class__.__name__})"
                )

            return result
        
        except Exception as e:
            logger.error(
                f"Error handling incident {incident.get('incident_id')}: {e}",
                exc_info=True
            )
            raise

    @staticmethod
    def _serialize_decision(
        decision: DecisionOutput | DecisionBlockedOutput | DecisionSkippedOutput,
    ) -> Dict[str, Any]:
        return decision.model_dump(mode="json")
