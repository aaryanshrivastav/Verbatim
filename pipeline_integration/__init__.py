"""Compatibility integration for Detection -> Decision -> Executor."""

from pipeline_integration.adapter import DetectionIncidentAdapter, IncidentAdapterConfig
from pipeline_integration.runner import IntegratedPipelineRunner
from pipeline_integration.service import IntegratedPipeline, IntegratedPipelineConfig

__all__ = [
    "DetectionIncidentAdapter",
    "IncidentAdapterConfig",
    "IntegratedPipelineRunner",
    "IntegratedPipeline",
    "IntegratedPipelineConfig",
]
