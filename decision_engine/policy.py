"""Q-table policy loading, validation, and live inference."""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Sequence, Set, Tuple

from decision_engine.actions import (
    ACTION_FORCE_KILL,
    ACTION_SCALE_UP,
    DEFAULT_ACTION_ID,
    DEFAULT_DB_SERVICES,
    LIVE_MASKED_ACTION_IDS,
    action_name,
    ordered_action_ids,
)
from decision_engine.models import PolicySelection

QTable = Dict[Tuple[Tuple[int, ...], int], float]


@dataclass
class PolicyConfig:
    """Runtime configuration for Q-table inference."""

    q_table_path: Optional[str | Path] = None
    state_size: int = 6
    default_action_id: int = DEFAULT_ACTION_ID
    db_services: Set[str] = field(default_factory=lambda: set(DEFAULT_DB_SERVICES))
    scalable_services: Optional[Set[str]] = None
    mask_scale_down: bool = True


class QTablePolicy:
    """Loads and queries a pre-trained Q-table for live decisions."""

    def __init__(self, config: Optional[PolicyConfig] = None) -> None:
        self.config = config or PolicyConfig()
        self.q_table: QTable = {}
        self.loaded_from_disk = False
        self.validated = False
        self.load()

    def load(self) -> None:
        """Load and validate a pickled Q-table if configured."""
        path = self.config.q_table_path
        if path is None:
            self.q_table = {}
            self.validated = True
            return

        file_path = Path(path)
        if not file_path.exists():
            self.q_table = {}
            self.validated = True
            return

        with file_path.open("rb") as handle:
            candidate = pickle.load(handle)

        if not self._is_valid_q_table(candidate):
            self.q_table = {}
            self.validated = False
            return

        self.q_table = candidate
        self.loaded_from_disk = True
        self.validated = True

    def save(self, path: Optional[str | Path] = None) -> Path:
        """Persist the current Q-table to disk."""
        output_path = Path(path or self.config.q_table_path or "q_table.pkl")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as handle:
            pickle.dump(self.q_table, handle)
        return output_path

    def select_action(self, state_vector: Sequence[int], service: str) -> PolicySelection:
        """Select the best live action after applying runtime safety masks."""
        state = tuple(int(value) for value in state_vector)
        q_values_by_id = {
            action_id: float(self.q_table.get((state, action_id), 0.0))
            for action_id in ordered_action_ids()
        }
        allowed_actions, masked_actions = self._allowed_actions(service)
        q_table_hit = any((state, action_id) in self.q_table for action_id in allowed_actions)

        if not allowed_actions:
            allowed_actions = [self.config.default_action_id]

        if all(abs(q_values_by_id[action_id]) < 1e-12 for action_id in allowed_actions):
            chosen_action_id = (
                self.config.default_action_id
                if self.config.default_action_id in allowed_actions
                else allowed_actions[0]
            )
            defaulted = True
        else:
            chosen_action_id = max(
                allowed_actions,
                key=lambda action_id: (q_values_by_id[action_id], -action_id),
            )
            defaulted = False

        return PolicySelection(
            action_id=chosen_action_id,
            action_type=action_name(chosen_action_id),
            q_value=q_values_by_id[chosen_action_id],
            all_q_values={
                action_name(action_id): q_values_by_id[action_id]
                for action_id in ordered_action_ids()
            },
            q_table_hit=q_table_hit,
            masked_actions=masked_actions,
            defaulted=defaulted,
        )

    def _allowed_actions(self, service: str) -> tuple[list[int], list[str]]:
        """Return runtime-safe actions plus the masked action names."""
        allowed = []
        masked = []
        for action_id in ordered_action_ids():
            blocked = False
            if self.config.mask_scale_down and action_id in LIVE_MASKED_ACTION_IDS:
                blocked = True
            if action_id == ACTION_FORCE_KILL and service in self.config.db_services:
                blocked = True
            if (
                action_id == ACTION_SCALE_UP
                and self.config.scalable_services is not None
                and service not in self.config.scalable_services
            ):
                blocked = True

            if blocked:
                masked.append(action_name(action_id))
            else:
                allowed.append(action_id)

        return allowed, masked

    def _is_valid_q_table(self, candidate: object) -> bool:
        """Validate key shape so stale files do not poison live inference."""
        if not isinstance(candidate, dict):
            return False
        if not candidate:
            return True

        for key, value in candidate.items():
            if not isinstance(key, tuple) or len(key) != 2:
                return False
            state, action_id = key
            if not isinstance(state, tuple) or len(state) != self.config.state_size:
                return False
            if any(state_value not in (0, 1, 2) for state_value in state):
                return False
            if action_id not in ordered_action_ids():
                return False
            if not isinstance(value, (int, float)):
                return False
        return True
