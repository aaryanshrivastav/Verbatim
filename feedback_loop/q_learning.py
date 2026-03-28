"""Live Bellman update support for Component 6."""

from __future__ import annotations

import pickle
from pathlib import Path
from threading import RLock
from typing import Dict, Optional, Sequence, Tuple

from decision_engine.actions import action_name, ordered_action_ids


class QTableLearner:
    """Loads, updates, and periodically checkpoints the Q-table."""

    def __init__(
        self,
        load_path: Optional[str | Path] = None,
        checkpoint_path: Optional[str | Path] = None,
        alpha: float = 0.1,
        gamma: float = 0.9,
        min_q: float = -5.0,
        max_q: float = 5.0,
        save_every_updates: int = 5,
    ) -> None:
        self.load_path = Path(load_path) if load_path else None
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path else None
        self.alpha = alpha
        self.gamma = gamma
        self.min_q = min_q
        self.max_q = max_q
        self.save_every_updates = save_every_updates
        self._lock = RLock()
        self._q_table: Dict[Tuple[tuple[int, ...], int], float] = {}
        self._episodes_live = 0
        self._load()

    @property
    def episodes_live(self) -> int:
        return self._episodes_live

    @property
    def q_table_size(self) -> int:
        return len(self._q_table)

    def q_values_for_state(self, state: Sequence[int]) -> Dict[str, float]:
        state_key = tuple(state)
        return {
            action_name(action_id): round(self._q_table.get((state_key, action_id), 0.0), 4)
            for action_id in ordered_action_ids()
        }

    def update(
        self,
        state: Sequence[int],
        action_id: int,
        reward: float,
        next_state: Sequence[int],
    ) -> Dict[str, object]:
        state_key = tuple(state)
        next_state_key = tuple(next_state)

        with self._lock:
            q_current = self._q_table.get((state_key, action_id), 0.0)
            q_next_max = max(
                self._q_table.get((next_state_key, candidate), 0.0)
                for candidate in ordered_action_ids()
            )
            q_new = q_current + self.alpha * (reward + self.gamma * q_next_max - q_current)
            q_new = max(self.min_q, min(self.max_q, q_new))
            self._q_table[(state_key, action_id)] = q_new

            self._episodes_live += 1
            checkpoint_saved = False
            if self.checkpoint_path and self.save_every_updates > 0 and self._episodes_live % self.save_every_updates == 0:
                self._save_checkpoint()
                checkpoint_saved = True

            return {
                "q_before": round(q_current, 4),
                "q_after": round(q_new, 4),
                "q_shift": round(q_new - q_current, 4),
                "all_q_values_updated": self.q_values_for_state(state_key),
                "episodes_live": self._episodes_live,
                "q_table_size": len(self._q_table),
                "checkpoint_saved": checkpoint_saved,
            }

    def _load(self) -> None:
        source_path = None
        if self.checkpoint_path and self.checkpoint_path.exists():
            source_path = self.checkpoint_path
        elif self.load_path and self.load_path.exists():
            source_path = self.load_path

        if source_path is None:
            self._q_table = {}
            return

        with source_path.open("rb") as handle:
            payload = pickle.load(handle)
        self._q_table = payload if isinstance(payload, dict) else {}

    def _save_checkpoint(self) -> None:
        assert self.checkpoint_path is not None
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        with self.checkpoint_path.open("wb") as handle:
            pickle.dump(self._q_table, handle)
