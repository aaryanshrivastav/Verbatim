"""Action identifiers and helpers for the Decision Engine."""

from __future__ import annotations

from typing import Dict, List

ACTION_RESTART = 0
ACTION_SCALE_UP = 1
ACTION_SCALE_DOWN = 2
ACTION_FORCE_KILL = 3

DEFAULT_ACTION_ID = ACTION_RESTART

ACTION_NAMES: Dict[int, str] = {
    ACTION_RESTART: "restart",
    ACTION_SCALE_UP: "scale_up",
    ACTION_SCALE_DOWN: "scale_down",
    ACTION_FORCE_KILL: "force_kill",
}

LIVE_MASKED_ACTION_IDS = {ACTION_SCALE_DOWN}

DEFAULT_DB_SERVICES = {
    "postgres",
    "redis",
    "mysql",
    "mongodb",
    "orders-db",
    "db",
}


def ordered_action_ids() -> List[int]:
    """Return action IDs in a stable order for inference and dashboards."""
    return [ACTION_RESTART, ACTION_SCALE_UP, ACTION_SCALE_DOWN, ACTION_FORCE_KILL]


def action_name(action_id: int) -> str:
    """Return the external action name for an action identifier."""
    return ACTION_NAMES[action_id]
