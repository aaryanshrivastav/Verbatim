"""Action routing and fallback logic for the Remediation Executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from decision_engine.actions import (
    ACTION_FORCE_KILL,
    ACTION_RESTART,
    ACTION_SCALE_DOWN,
    ACTION_SCALE_UP,
    action_name,
)
from remediation_executor.catalog import ServiceTarget
from remediation_executor.models import ExecutorRequest


@dataclass
class RoutedAction:
    """Effective action after runtime safety checks and fallbacks."""

    effective_action_id: int
    effective_action_type: str
    requested_action_id: int
    requested_action_type: str
    fallback_used: bool = False
    fallback_reason: Optional[str] = None


class ActionRouter:
    """Maps requested RL actions to runtime-safe effective actions."""

    def route(
        self,
        request: ExecutorRequest,
        target: ServiceTarget,
        replica_count: int,
    ) -> RoutedAction:
        """Apply executor-side action masking and fallback rules."""
        requested_action_id = request.requested_action_id
        requested_action_type = request.requested_action_type

        if requested_action_id == ACTION_RESTART:
            return RoutedAction(ACTION_RESTART, "restart", requested_action_id, requested_action_type)

        if requested_action_id == ACTION_SCALE_UP:
            if not target.scalable:
                return self._fallback(requested_action_id, requested_action_type, "scale_up blocked for non-scalable service")
            return RoutedAction(ACTION_SCALE_UP, "scale_up", requested_action_id, requested_action_type)

        if requested_action_id == ACTION_SCALE_DOWN:
            if not target.scalable or replica_count <= 1:
                return self._fallback(requested_action_id, requested_action_type, "cannot scale below 1 replica")
            return RoutedAction(ACTION_SCALE_DOWN, "scale_down", requested_action_id, requested_action_type)

        if requested_action_id == ACTION_FORCE_KILL:
            if target.is_db:
                return self._fallback(requested_action_id, requested_action_type, "force_kill blocked for DB service")
            return RoutedAction(ACTION_FORCE_KILL, "force_kill", requested_action_id, requested_action_type)

        return self._fallback(requested_action_id, requested_action_type, "unknown action requested")

    @staticmethod
    def _fallback(requested_action_id: int, requested_action_type: str, reason: str) -> RoutedAction:
        return RoutedAction(
            effective_action_id=ACTION_RESTART,
            effective_action_type=action_name(ACTION_RESTART),
            requested_action_id=requested_action_id,
            requested_action_type=requested_action_type,
            fallback_used=True,
            fallback_reason=reason,
        )
