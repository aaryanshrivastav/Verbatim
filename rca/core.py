"""Core RCA pipeline orchestrator.

Chains all modules A-G to produce RCA output.
"""

import logging
from datetime import datetime
from typing import Optional

from rca.models import Incident, RCAOutput, CandidatePrediction, Evidence
from rca.config import RCAConfig
from rca.A_trace_graph_builder import TraceGraphBuilder
from rca.B_candidate_extractor import CandidateExtractor
from rca.C_feature_builder import FeatureBuilder
from rca.D_ml_ranker import MLRanker
from rca.E_root_cause_selector import RootCauseSelector
from rca.F_state_vector import StateVectorBuilder
from rca.G_evidence_assembler import EvidenceAssembler

logger = logging.getLogger(__name__)


class RCAPipeline:
    """Main RCA pipeline orchestrator."""
    
    def __init__(self, config: Optional[RCAConfig] = None):
        """Initialize pipeline.
        
        Args:
            config: RCAConfig instance, or None to use defaults
        """
        self.config = config or RCAConfig()
        
        # Initialize modules
        self.trace_builder = TraceGraphBuilder(self.config)
        self.candidate_extractor = CandidateExtractor(self.config)
        self.feature_builder = FeatureBuilder(self.config)
        self.ml_ranker = MLRanker(self.config)
        self.root_selector = RootCauseSelector(self.config)
        self.state_builder = StateVectorBuilder(self.config)
        self.evidence_assembler = EvidenceAssembler(self.config)
        
        logger.info("RCAPipeline initialized")
    
    def analyze(self, incident: Incident) -> RCAOutput:
        """Run full RCA pipeline.
        
        Incident → [A: Trace Graph] → [B: Candidates] → [C: Features]
                 → [D: ML Rank] → [E: Select] → [F: State Vector]
                 → [G: Evidence] → RCA Output
        
        Args:
            incident: Incident object from detection
            
        Returns:
            RCAOutput with root cause and evidence
        """
        logger.info(
            f"Starting RCA analysis for incident {incident.incident_id} "
            f"on endpoint {incident.endpoint}"
        )
        
        # MODULE A: Build trace graph
        logger.debug("Module A: Building trace graph...")
        trace_metrics = self.trace_builder.build_graph(incident)
        
        if not trace_metrics:
            logger.warning("No trace metrics available, returning default RCA")
            return self._create_default_rca(incident)
        
        # MODULE B: Extract candidates
        logger.debug("Module B: Extracting candidates...")
        candidates = self.candidate_extractor.extract_candidates(
            incident, trace_metrics
        )
        
        if not candidates:
            logger.warning("No candidates extracted, returning default RCA")
            return self._create_default_rca(incident)
        
        # MODULE C: Build features
        logger.debug("Module C: Building features...")
        candidates = self.feature_builder.build_features(candidates)
        
        # MODULE D: ML ranking
        logger.debug("Module D: ML ranking...")
        candidates = self.ml_ranker.rank_candidates(candidates)
        
        # MODULE E: Select root cause
        logger.debug("Module E: Selecting root cause...")
        root_cause, confidence, top_3 = self.root_selector.select_root_cause(
            candidates
        )
        
        if not root_cause:
            logger.warning("No root cause selected, returning default RCA")
            return self._create_default_rca(incident)
        
        # MODULE F: Build state vector
        logger.debug("Module F: Building state vector...")
        state_vector = self.state_builder.build_state_vector(incident)
        
        # MODULE G: Assemble evidence
        logger.debug("Module G: Assembling evidence...")
        evidence = self.evidence_assembler.assemble_evidence(
            incident, root_cause.service
        )
        
        # Build output
        top_candidates = [
            CandidatePrediction(service=c.service, probability=c.probability or 0.0)
            for c in top_3
        ]
        
        affected_services = list({
            self.config.normalize_service_name(a.service) for a in incident.anomalies
        })
        
        rca_output = RCAOutput(
            incident_id=incident.incident_id,
            endpoint=incident.endpoint,
            root_cause=root_cause.service,
            confidence=confidence,
            top_candidates=top_candidates,
            affected_services=affected_services,
            state_vector=state_vector,
            original_severity=incident.get_max_severity(),
            time_window=[
                incident.time_window_start.isoformat(),
                incident.time_window_end.isoformat()
            ],
            evidence=evidence
        )
        
        logger.info(
            f"RCA completed: root_cause={root_cause.service}, "
            f"confidence={confidence.bucket} ({confidence.value:.3f})"
        )
        
        return rca_output
    
    def _create_default_rca(self, incident: Incident) -> RCAOutput:
        """Create default RCA when analysis fails.
        
        Args:
            incident: Incident object
            
        Returns:
            RCAOutput with default/fallback values
        """
        # Pick highest severity anomaly
        max_anom = max(incident.anomalies, key=lambda a: a.severity)
        root_cause = self.config.normalize_service_name(max_anom.service)
        
        state_vector = self.state_builder.build_state_vector(incident)
        affected_services = list({
            self.config.normalize_service_name(a.service) for a in incident.anomalies
        })
        
        return RCAOutput(
            incident_id=incident.incident_id,
            endpoint=incident.endpoint,
            root_cause=root_cause,
            confidence={"value": 0.0, "bucket": "low"},
            top_candidates=[
                CandidatePrediction(
                    service=self.config.normalize_service_name(a.service),
                    probability=a.severity,
                )
                for a in incident.anomalies
            ],
            affected_services=affected_services,
            state_vector=state_vector,
            original_severity=incident.get_max_severity(),
            time_window=[
                incident.time_window_start.isoformat(),
                incident.time_window_end.isoformat()
            ],
            evidence=Evidence()
        )
