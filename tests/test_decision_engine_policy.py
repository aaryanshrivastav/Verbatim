"""Unit tests for Decision Engine policy selection."""

import pickle

from decision_engine.policy import PolicyConfig, QTablePolicy


def test_policy_masks_live_unsafe_actions_for_db(tmp_path):
    """Force-kill and scale-down should be masked for DB services in live mode."""
    q_table = {
        ((0, 0, 0, 0, 2, 0), 0): 1.1,
        ((0, 0, 0, 0, 2, 0), 1): 0.8,
        ((0, 0, 0, 0, 2, 0), 2): 2.0,
        ((0, 0, 0, 0, 2, 0), 3): 1.9,
    }
    path = tmp_path / "q_table.pkl"
    path.write_bytes(pickle.dumps(q_table))

    policy = QTablePolicy(PolicyConfig(q_table_path=path, db_services={"db"}))
    selection = policy.select_action([0, 0, 0, 0, 2, 0], service="db")

    assert selection.action_type == "restart"
    assert "scale_down" in selection.masked_actions
    assert "force_kill" in selection.masked_actions


def test_policy_defaults_to_restart_for_unseen_state(tmp_path):
    """Unseen states should fall back to restart instead of random action selection."""
    path = tmp_path / "missing.pkl"
    policy = QTablePolicy(PolicyConfig(q_table_path=path))

    selection = policy.select_action([0, 1, 0, 0, 2, 0], service="payment")

    assert selection.action_type == "restart"
    assert selection.defaulted is True
    assert selection.q_table_hit is False


def test_policy_rejects_stale_q_table_shape(tmp_path):
    """State-size mismatches should invalidate old Q-table files safely."""
    stale_q_table = {
        ((0, 0, 2), 0): 1.0,
    }
    path = tmp_path / "stale.pkl"
    path.write_bytes(pickle.dumps(stale_q_table))

    policy = QTablePolicy(PolicyConfig(q_table_path=path, state_size=6))

    assert policy.q_table == {}
    assert policy.validated is False
