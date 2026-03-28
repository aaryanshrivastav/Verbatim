"""Unit tests for offline Q-table training."""

from decision_engine.training.simulator import QTrainer, TrainingConfig


def test_q_trainer_generates_non_empty_q_table(tmp_path):
    """Short training runs should still populate useful Q-values."""
    trainer = QTrainer(TrainingConfig(episodes=80, seed=7))
    q_table = trainer.train()

    path = trainer.save(q_table, tmp_path / "q_table.pkl")
    q_values = trainer.sample_q_values(q_table, [0, 0, 0, 0, 2, 0])

    assert len(q_table) > 0
    assert path.exists()
    assert set(q_values.keys()) == {"restart", "scale_up", "scale_down", "force_kill"}
