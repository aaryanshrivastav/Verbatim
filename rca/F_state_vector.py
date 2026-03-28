"""Module F: State Vector for RL.

Builds state vector representing system state for RL agent.
"""

import logging
from typing import List

from rca.models import Incident
from rca.config import RCAConfig

logger = logging.getLogger(__name__)


class StateVectorBuilder:
    """Builds state vector for RL agent."""
    
    def __init__(self, config: RCAConfig):
        """Initialize builder.
        
        Args:
            config: RCAConfig instance
        """
        self.config = config
    
    def build_state_vector(self, incident: Incident) -> List[int]:
        """Build state vector from incident.
        
        For each fixed service in order:
        - state = 2 (critical) if metrics_severity >= critical_threshold
        - state = 1 (degraded) if metrics_severity >= degraded_threshold
        - state = 0 (healthy) otherwise
        
        Args:
            incident: Incident object
            
        Returns:
            List of 6 integers [s0, s1, ..., s5]
        """
        max_per_slot = {slot: 0.0 for slot in self.config.state_slots}
        for anomaly in incident.anomalies:
            slot = self.config.state_slot_for(anomaly.service)
            if slot is None:
                continue
            max_per_slot[slot] = max(max_per_slot[slot], float(anomaly.severity))

        state_vector = []
        for slot in self.config.state_slots:
            severity = max_per_slot[slot]
            if severity >= self.config.critical_severity_threshold:
                state = 2
            elif severity >= self.config.degraded_severity_threshold:
                state = 1
            else:
                state = 0
            
            state_vector.append(state)
        
        logger.debug(f"State vector: {state_vector}")
        return state_vector
