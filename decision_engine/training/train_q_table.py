"""CLI entry point for offline Q-table training."""

from __future__ import annotations

import argparse
from pathlib import Path

from decision_engine.training.simulator import QTrainer, TrainingConfig


def train_and_save(
    output_path: str | Path,
    episodes: int = 2000,
    seed: int = 42,
) -> Path:
    """Train a Q-table and persist it to disk."""
    trainer = QTrainer(TrainingConfig(episodes=episodes, seed=seed))
    q_table = trainer.train()
    return trainer.save(q_table, output_path)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Train the Decision Engine Q-table.")
    parser.add_argument(
        "--episodes",
        type=int,
        default=2000,
        help="Number of offline training episodes to run.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible training.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("decision_engine") / "artifacts" / "q_table.pkl",
        help="Path where the trained q_table.pkl will be written.",
    )
    return parser


def main() -> None:
    """Train a Q-table and print a compact sanity summary."""
    args = build_parser().parse_args()
    config = TrainingConfig(episodes=args.episodes, seed=args.seed)
    trainer = QTrainer(config)
    q_table = trainer.train()
    output_path = trainer.save(q_table, args.output)
    representative_states = [
        ("payment latency", (0, 0, 0, 0, 2, 1)),
        ("checkout cascade", (0, 0, 0, 2, 1, 0)),
        ("auth degraded", (0, 0, 1, 0, 0, 0)),
    ]

    print(f"Training complete. {args.episodes} episodes.")
    print(f"Q-table entries filled: {len(q_table)} / 2916")
    print(f"Saved to: {output_path}")
    print("Representative Q-values:")
    for label, state in representative_states:
        q_values = trainer.sample_q_values(q_table, state)
        print(f"State {list(state)} ({label}):")
        for name, value in q_values.items():
            print(f"  {name}: {value}")


if __name__ == "__main__":
    main()
