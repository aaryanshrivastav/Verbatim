"""Runnable entry point for the integrated Detection -> RCA path."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from detection.config import DetectionConfig
from detection.service import DetectionService
from triage_integration.service import TriagePipeline, TriagePipelineConfig


class TriagePipelineRunner:
    """Runs Detection and forwards incidents into RCA."""

    def __init__(
        self,
        pipeline: Optional[TriagePipeline] = None,
        detection_service: Optional[DetectionService] = None,
    ) -> None:
        self.pipeline = pipeline or TriagePipeline()
        self.detection_service = detection_service or DetectionService(DetectionConfig.from_env())

    async def run_once(self) -> Dict[str, Any]:
        tick_result = self.detection_service.tick()
        outcomes = await self.pipeline.handle_detection_tick(tick_result)
        return {
            "tick": tick_result,
            "outcomes": outcomes,
        }

    async def run_loop(
        self,
        max_iterations: Optional[int] = None,
        sleep_seconds: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        sleep_seconds = (
            sleep_seconds
            if sleep_seconds is not None
            else self.detection_service.config.poll_interval_seconds
        )
        results: List[Dict[str, Any]] = []
        iteration = 0
        while True:
            iteration += 1
            results.append(await self.run_once())
            if max_iterations is not None and iteration >= max_iterations:
                return results
            time.sleep(sleep_seconds)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the integrated Detection -> RCA pipeline.")
    parser.add_argument("--once", action="store_true", help="Run a single detection tick and exit.")
    parser.add_argument("--iterations", type=int, help="Run N iterations and exit.")
    parser.add_argument("--sleep-seconds", type=int, help="Override sleep between iterations.")
    parser.add_argument("--output-file", type=Path, help="Optional JSONL file to append outcomes.")
    parser.add_argument("--jaeger-base-url", default="http://localhost:16686")
    parser.add_argument("--prometheus-base-url", default="http://localhost:9090")
    parser.add_argument("--loki-base-url", default="http://localhost:3100")
    parser.add_argument("--ml-model-path", type=Path, default=Path("models") / "ml_ranker_logistic_regression.pkl")
    return parser


async def _main_async(args: argparse.Namespace) -> None:
    runner = TriagePipelineRunner(
        pipeline=TriagePipeline(
            TriagePipelineConfig(
                jaeger_base_url=args.jaeger_base_url,
                prometheus_base_url=args.prometheus_base_url,
                loki_base_url=args.loki_base_url,
                ml_model_path=args.ml_model_path,
            )
        )
    )

    if args.once:
        results = [await runner.run_once()]
    else:
        results = await runner.run_loop(
            max_iterations=args.iterations,
            sleep_seconds=args.sleep_seconds,
        )

    for result in results:
        line = json.dumps(result, default=str)
        if args.output_file:
            args.output_file.parent.mkdir(parents=True, exist_ok=True)
            with args.output_file.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        else:
            print(line)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
