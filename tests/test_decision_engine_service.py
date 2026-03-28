"""Unit tests for Decision Engine orchestration and event emission."""

import pickle
from datetime import datetime, timedelta, timezone

from decision_engine.events import InMemoryEventPublisher
from decision_engine.service import DecisionEngine, DecisionEngineConfig


def build_engine(tmp_path):
    """Create a DecisionEngine wired to a temporary Q-table and test publisher."""
    q_table = {
        ((0, 0, 1, 0, 2, 1), 0): 1.4,
        ((0, 0, 1, 0, 2, 1), 1): 0.8,
        ((0, 0, 1, 0, 2, 1), 3): 1.1,
    }
    q_path = tmp_path / "q_table.pkl"
    q_path.write_bytes(pickle.dumps(q_table))
    publisher = InMemoryEventPublisher()
    engine = DecisionEngine(
        DecisionEngineConfig(
            q_table_path=q_path,
            db_services={"db"},
        ),
        publisher=publisher,
    )
    return engine, publisher


def test_process_emits_decision_and_rl_events(tmp_path):
    """Successful processing should return a decision and publish two SSE events."""
    engine, publisher = build_engine(tmp_path)
    started_at = datetime.now(timezone.utc) - timedelta(seconds=9)

    result = engine.process(
        {
            "incident_id": "inc-1042",
            "root_cause": "payment",
            "confidence": {"value": 0.84, "bucket": "high"},
            "state_vector": [0, 0, 1, 0, 2, 1],
            "original_severity": 0.91,
            "affected_services": ["checkout", "frontend"],
            "incident_started_at": started_at.isoformat(),
        }
    )

    assert result.action.action_type == "restart"
    assert result.rollback_watch is False
    assert len(publisher.events) == 2
    assert publisher.events[0].type == "DECISION_MADE"
    assert publisher.events[1].type == "RL_DECISION"


def test_process_skips_non_actionable_all_zero_state(tmp_path):
    """All-zero low-severity states should be skipped instead of remediated."""
    engine, publisher = build_engine(tmp_path)

    result = engine.process(
        {
            "incident_id": "inc-2000",
            "root_cause": "payment",
            "confidence": {"value": 0.9, "bucket": "high"},
            "state_vector": [0, 0, 0, 0, 0, 0],
            "original_severity": 0.2,
        }
    )

    assert result.decision == "SKIPPED"
    assert publisher.events[-1].type == "DECISION_SKIPPED"


def test_process_blocks_service_after_action_is_marked_fired(tmp_path):
    """Cooldown should block later incidents once an action has been acknowledged."""
    engine, publisher = build_engine(tmp_path)

    first = engine.process(
        {
            "incident_id": "inc-3000",
            "root_cause": "payment",
            "confidence": {"value": 0.84, "bucket": "high"},
            "state_vector": [0, 0, 1, 0, 2, 1],
            "original_severity": 0.91,
        }
    )
    engine.mark_action_fired(first.action.service)
    engine.release_incident(first.incident_id, first.action.service)

    blocked = engine.process(
        {
            "incident_id": "inc-3001",
            "root_cause": "payment",
            "confidence": {"value": 0.84, "bucket": "high"},
            "state_vector": [0, 0, 1, 0, 2, 1],
            "original_severity": 0.91,
        }
    )

    assert blocked.decision == "BLOCKED"
    assert publisher.events[-1].type == "DECISION_BLOCKED"
