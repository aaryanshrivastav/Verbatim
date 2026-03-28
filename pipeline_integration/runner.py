"""Runnable entry point for the integrated Detection -> RCA -> Decision -> Executor pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from detection.config import DetectionConfig
from detection.service import DetectionService
from pipeline_integration.service import IntegratedPipeline, IntegratedPipelineConfig


class IntegratedPipelineRunner:
    """Runs Detection and forwards incidents through the full RCA -> Decision -> Executor pipeline."""

    def __init__(
        self,
        pipeline: Optional[IntegratedPipeline] = None,
        detection_service: Optional[DetectionService] = None,
    ) -> None:
        self.pipeline = pipeline or IntegratedPipeline()
        self.detection_service = detection_service or DetectionService(DetectionConfig.from_env())

    async def run_once(self) -> Dict[str, Any]:
        """Execute one detection tick and process resulting incidents through full pipeline."""
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
        """Run the integrated loop repeatedly."""
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
    parser = argparse.ArgumentParser(
        description="Run the integrated Detection -> RCA -> Decision -> Executor pipeline with full RCA analysis."
    )
    parser.add_argument("--once", action="store_true", help="Run a single detection tick and exit.")
    parser.add_argument("--iterations", type=int, help="Run N iterations and exit.")
    parser.add_argument("--sleep-seconds", type=int, help="Override sleep between iterations.")
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Optional JSONL file to append pipeline outcomes.",
    )
    
    # RCA Configuration
    parser.add_argument(
        "--enable-rca",
        action="store_true",
        default=True,
        help="Enable full RCA pipeline (default: True)",
    )
    parser.add_argument(
        "--disable-rca",
        action="store_true",
        help="Disable RCA pipeline (use fallback adapter only)",
    )
    parser.add_argument(
        "--jaeger-host",
        default="localhost",
        help="Jaeger server host for trace collection (default: localhost)",
    )
    parser.add_argument(
        "--jaeger-port",
        type=int,
        default=6831,
        help="Jaeger server UDP port (default: 6831)",
    )
    parser.add_argument(
        "--prometheus-url",
        default="http://localhost:9090",
        help="Prometheus URL for metrics collection (default: http://localhost:9090)",
    )
    parser.add_argument(
        "--loki-url",
        default="http://localhost:3100",
        help="Loki URL for log collection (default: http://localhost:3100)",
    )
    parser.add_argument(
        "--ml-ranker-model",
        type=Path,
        default=Path("models/ml_ranker_logistic_regression.pkl"),
        help="Path to ML ranker model file",
    )
    parser.add_argument(
        "--rca-fallback",
        action="store_true",
        default=True,
        help="Enable fallback to simple adapter if RCA fails (default: True)",
    )
    
    return parser


async def _main_async(args: argparse.Namespace) -> None:
    # Build pipeline configuration from CLI arguments
    enable_rca = args.enable_rca and not args.disable_rca
    
    config = IntegratedPipelineConfig(
        q_table_path=Path("decision_engine") / "artifacts" / "q_table.pkl",
        compose_file="docker-compose.yml",
        enable_rca=enable_rca,
        jaeger_host=args.jaeger_host,
        jaeger_port=args.jaeger_port,
        prometheus_url=args.prometheus_url,
        loki_url=args.loki_url,
        ml_ranker_model_path=args.ml_ranker_model,
        rca_fallback_on_error=args.rca_fallback,
    )
    
    runner = IntegratedPipelineRunner(
        pipeline=IntegratedPipeline(config)
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
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO)
    parser = _build_parser()
    args = parser.parse_args()

    import asyncio

    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
