"""Offline simulator and Bellman training for the Decision Engine Q-table."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from decision_engine.actions import (
    ACTION_FORCE_KILL,
    ACTION_RESTART,
    ACTION_SCALE_DOWN,
    ACTION_SCALE_UP,
    DEFAULT_DB_SERVICES,
    action_name,
    ordered_action_ids,
)
from decision_engine.policy import QTable


@dataclass(frozen=True)
class EpisodeSpec:
    """Generated training episode with scenario metadata."""

    initial_state: Tuple[int, ...]
    root_cause_index: int
    failure_mode: str
    original_severity: float


@dataclass
class TrainingConfig:
    """Configuration for offline Q-learning simulation."""

    episodes: int = 2000
    max_steps: int = 10
    alpha: float = 0.1
    gamma: float = 0.9
    epsilon_start: float = 1.0
    epsilon_decay: float = 0.995
    epsilon_min: float = 0.1
    seed: int = 42
    service_names: Tuple[str, ...] = (
        "frontend",
        "gateway",
        "auth",
        "checkout",
        "payment",
        "db",
    )
    scenario_weights: Dict[str, int] = field(
        default_factory=lambda: {
            "crash": 400,
            "memory": 400,
            "latency": 400,
            "cascade": 400,
            "noise": 400,
        }
    )


class QTrainer:
    """State simulator plus Bellman trainer for the Q-table policy."""

    def __init__(self, config: TrainingConfig | None = None) -> None:
        self.config = config or TrainingConfig()
        self.random = random.Random(self.config.seed)
        self.db_indices = {
            index
            for index, service in enumerate(self.config.service_names)
            if service in DEFAULT_DB_SERVICES
        }
        self.downstream_map = {
            0: [1],
            1: [2, 3],
            2: [3],
            3: [4, 5],
            4: [5],
            5: [],
        }

    def train(self) -> QTable:
        """Run epsilon-greedy Q-learning over generated failure episodes."""
        q_table: QTable = {}
        epsilon = self.config.epsilon_start
        scenarios = self._expanded_scenarios()

        for episode_index in range(self.config.episodes):
            failure_mode = scenarios[episode_index % len(scenarios)]
            spec = self._generate_episode(failure_mode)
            state = spec.initial_state

            for _ in range(self.config.max_steps):
                action_id = self._select_training_action(q_table, state, epsilon)
                next_state, reward, _ = self._transition(spec, state, action_id)
                q_current = q_table.get((state, action_id), 0.0)
                q_next_max = max(
                    q_table.get((next_state, next_action), 0.0)
                    for next_action in ordered_action_ids()
                )
                q_new = q_current + self.config.alpha * (
                    reward + self.config.gamma * q_next_max - q_current
                )
                q_table[(state, action_id)] = q_new
                state = next_state
                if self._is_recovered(spec, state):
                    break

            epsilon = max(self.config.epsilon_min, epsilon * self.config.epsilon_decay)

        return q_table

    def save(self, q_table: QTable, output_path: str | Path) -> Path:
        """Persist a trained Q-table to disk."""
        from pickle import dump

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            dump(q_table, handle)
        return path

    def sample_q_values(self, q_table: QTable, state: Sequence[int]) -> Dict[str, float]:
        """Return human-readable Q-values for a given state."""
        state_tuple = tuple(state)
        return {
            action_name(action_id): round(q_table.get((state_tuple, action_id), 0.0), 4)
            for action_id in ordered_action_ids()
        }

    def _expanded_scenarios(self) -> List[str]:
        """Expand weighted scenario counts into a deterministic training sequence."""
        scenarios: List[str] = []
        for name, count in self.config.scenario_weights.items():
            scenarios.extend([name] * count)
        self.random.shuffle(scenarios)
        return scenarios

    def _generate_episode(self, failure_mode: str) -> EpisodeSpec:
        """Generate an initial state and target service for a training episode."""
        root_cause_index = self.random.randrange(len(self.config.service_names))
        state = [0] * len(self.config.service_names)

        if failure_mode == "crash":
            state[root_cause_index] = 2
            self._degrade_downstream(state, root_cause_index, limit=1)
            severity = 0.9
        elif failure_mode == "memory":
            state[root_cause_index] = 2
            self._degrade_downstream(state, root_cause_index, limit=1)
            severity = 0.85
        elif failure_mode == "latency":
            state[root_cause_index] = 2
            self._degrade_downstream(state, root_cause_index, limit=1)
            severity = 0.88
        elif failure_mode == "cascade":
            state[root_cause_index] = 2
            self._degrade_downstream(state, root_cause_index, limit=2)
            severity = 0.93
        else:
            state[root_cause_index] = 1
            maybe_secondary = (root_cause_index + 1) % len(self.config.service_names)
            state[maybe_secondary] = self.random.choice([0, 1])
            severity = 0.45

        return EpisodeSpec(
            initial_state=tuple(state),
            root_cause_index=root_cause_index,
            failure_mode=failure_mode,
            original_severity=severity,
        )

    def _degrade_downstream(self, state: List[int], root_cause_index: int, limit: int) -> None:
        """Propagate one-step degradation to downstream dependents."""
        for downstream_index in self.downstream_map.get(root_cause_index, [])[:limit]:
            state[downstream_index] = max(state[downstream_index], 1)

    def _transition(
        self,
        spec: EpisodeSpec,
        state: Tuple[int, ...],
        action_id: int,
    ) -> Tuple[Tuple[int, ...], float, int]:
        """Simulate action effect, reward, and recovery time in coarse steps."""
        next_state = list(state)
        root_index = spec.root_cause_index
        root_state = next_state[root_index]
        simulated_steps = self.random.choice([1, 2, 3])

        if action_id == ACTION_RESTART:
            if root_state == 2:
                next_state[root_index] = 0 if self.random.random() < 0.8 else 2
            elif root_state == 1:
                next_state[root_index] = 0 if self.random.random() < 0.9 else 1
        elif action_id == ACTION_SCALE_UP:
            if spec.failure_mode == "memory":
                next_state[root_index] = 1 if self.random.random() < 0.85 else 2
            elif spec.failure_mode == "latency":
                next_state[root_index] = 1 if self.random.random() < 0.75 else root_state
            else:
                if root_state == 2 and self.random.random() < 0.4:
                    next_state[root_index] = 1
        elif action_id == ACTION_SCALE_DOWN:
            if self.random.random() < 0.1:
                next_state[root_index] = min(2, root_state + 1)
        elif action_id == ACTION_FORCE_KILL:
            if root_index in self.db_indices:
                if self.random.random() < 0.7:
                    next_state[root_index] = 2
                else:
                    next_state[root_index] = max(1, root_state)
            else:
                if spec.failure_mode == "crash":
                    next_state[root_index] = 0 if self.random.random() < 0.75 else root_state
                    simulated_steps = max(1, simulated_steps - 1)
                else:
                    next_state[root_index] = 1 if root_state == 2 and self.random.random() < 0.35 else root_state
                    simulated_steps += 1

        if next_state[root_index] == 0:
            for downstream_index in self.downstream_map.get(root_index, []):
                next_state[downstream_index] = max(0, next_state[downstream_index] - 1)

        reward = self._reward(
            previous_root_state=root_state,
            next_root_state=next_state[root_index],
            severity=spec.original_severity,
            simulated_steps=simulated_steps,
            action_id=action_id,
            failure_mode=spec.failure_mode,
        )
        return tuple(next_state), reward, simulated_steps

    def _reward(
        self,
        previous_root_state: int,
        next_root_state: int,
        severity: float,
        simulated_steps: int,
        action_id: int,
        failure_mode: str,
    ) -> float:
        """Mirror the feedback-loop reward shape for offline pretraining."""
        if previous_root_state == 2 and next_root_state == 0:
            base = 1.5
        elif previous_root_state == 2 and next_root_state == 1:
            base = 0.7
        elif next_root_state > previous_root_state:
            base = -1.0
        elif next_root_state == previous_root_state:
            base = -0.3
        else:
            base = 0.4

        if action_id == ACTION_SCALE_DOWN:
            base -= 0.4
        if action_id == ACTION_FORCE_KILL and failure_mode != "crash":
            base -= 0.5

        reward = base + (severity * 0.5) - (0.02 * simulated_steps)
        return max(-2.0, min(2.0, reward))

    def _select_training_action(
        self,
        q_table: QTable,
        state: Tuple[int, ...],
        epsilon: float,
    ) -> int:
        """Use epsilon-greedy exploration during offline training only."""
        if self.random.random() < epsilon:
            return self.random.choice(ordered_action_ids())
        return max(
            ordered_action_ids(),
            key=lambda action_id: (q_table.get((state, action_id), 0.0), -action_id),
        )

    @staticmethod
    def _is_recovered(spec: EpisodeSpec, state: Tuple[int, ...]) -> bool:
        """Stop early when the root cause is healthy and no critical services remain."""
        return state[spec.root_cause_index] == 0 and all(value < 2 for value in state)
