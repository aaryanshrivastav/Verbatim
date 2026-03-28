"""Integration layer: Detection -> RCA -> Decision -> Executor.

Combines Detection anomalies, full RCA analysis (Modules A-G),
Decision Engine strategies, and Remediation Executor actions.
"""

from pipeline_integration.adapter import DetectionIncidentAdapter, IncidentAdapterConfig
from pipeline_integration.rca_integration import RCAIntegration, RCAPipelineConfig
from pipeline_integration.runner import IntegratedPipelineRunner
from pipeline_integration.service import IntegratedPipeline, IntegratedPipelineConfig

__all__ = [
    "DetectionIncidentAdapter",
    "IncidentAdapterConfig",
    "RCAIntegration",
    "RCAPipelineConfig",
    "IntegratedPipelineRunner",
    "IntegratedPipeline",
    "IntegratedPipelineConfig",
]
