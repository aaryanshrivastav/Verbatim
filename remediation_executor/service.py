"""Queue-backed remediation executor for Component 5."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from decision_engine.actions import ACTION_FORCE_KILL, ACTION_RESTART, ACTION_SCALE_DOWN, ACTION_SCALE_UP
from decision_engine.events import EventPublisher, InMemoryEventPublisher
from decision_engine.models import DecisionOutput
from decision_engine.registry import DecisionRegistry
from remediation_executor.catalog import ServiceCatalog, build_default_catalog
from remediation_executor.events import (
    build_action_fired_event,
    build_cooldown_race_blocked_event,
    build_execution_failed_event,
    build_fallback_event,
    build_queue_overflow_event,
)
from remediation_executor.models import ExecutionLog, ExecutorRequest
from remediation_executor.router import ActionRouter
from remediation_executor.runtime import ContainerNotFoundError, DockerRuntime, RuntimeErrorBase, SubprocessDockerRuntime


@dataclass
class RemediationExecutorConfig:
    """Configuration for the remediation worker."""

    queue_size: int = 5
    restart_timeout_seconds: int = 5
    docker_timeout_seconds: int = 15
    compose_file: str | Path = "docker-compose.yml"


class RemediationExecutor:
    """Executes Decision Engine actions one at a time against Docker."""

    def __init__(
        self,
        config: Optional[RemediationExecutorConfig] = None,
        catalog: Optional[ServiceCatalog] = None,
        runtime: Optional[DockerRuntime] = None,
        registry: Optional[DecisionRegistry] = None,
        publisher: Optional[EventPublisher] = None,
    ) -> None:
        self.config = config or RemediationExecutorConfig()
        self.catalog = catalog or build_default_catalog(compose_file=self.config.compose_file)
        self.runtime = runtime or SubprocessDockerRuntime(
            compose_file=self.config.compose_file,
            docker_timeout_seconds=self.config.docker_timeout_seconds,
        )
        self.registry = registry or DecisionRegistry()
        self.publisher = publisher or InMemoryEventPublisher()
        self.router = ActionRouter()
        self.queue: asyncio.Queue[ExecutorRequest] = asyncio.Queue(maxsize=self.config.queue_size)
        self._worker_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def enqueue(
        self,
        request: Union[ExecutorRequest, DecisionOutput, dict],
        incident_started_at: Optional[datetime] = None,
        detection_timestamp: Optional[datetime] = None,
    ) -> ExecutorRequest:
        """Add a request to the queue, dropping the oldest if full."""
        queue_item = self._coerce_request(request, incident_started_at, detection_timestamp)
        if self.queue.full():
            dropped = self.queue.get_nowait()
            self.registry.release(dropped.incident_id, dropped.service)
            self.publisher.publish(build_queue_overflow_event(dropped))
            self.queue.task_done()
        await self.queue.put(queue_item)
        return queue_item

    async def process_next(self) -> Optional[ExecutionLog]:
        """Process one queued request if available."""
        if self.queue.empty():
            return None
        request = await self.queue.get()
        try:
            return await self.execute(request)
        finally:
            self.queue.task_done()

    async def execute(self, request: ExecutorRequest) -> ExecutionLog:
        """Execute a single request without using the queue."""
        return await asyncio.to_thread(self._execute_sync, request)

    async def start_worker(self) -> None:
        """Start the background single-consumer worker."""
        if self._worker_task and not self._worker_task.done():
            return
        self._stop_event.clear()
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop_worker(self) -> None:
        """Stop the background worker."""
        self._stop_event.set()
        if self._worker_task:
            await self._worker_task

    def _worker_running(self) -> bool:
        return self._worker_task is not None and not self._worker_task.done()

    async def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self.process_next(), timeout=0.1)
            except asyncio.TimeoutError:
                continue

    def _execute_sync(self, request: ExecutorRequest) -> ExecutionLog:
        start_perf = time.perf_counter()
        execution_start = self._utc_now()
        try:
            target = self.catalog.resolve(request.service)
        except KeyError as exc:
            log = ExecutionLog(
                incident_id=request.incident_id,
                service=request.service,
                action_type=request.requested_action_type,
                action_id=request.requested_action_id,
                requested_action_type=request.requested_action_type,
                requested_action_id=request.requested_action_id,
                source=str(request.action["source"]),
                q_value=float(request.action["q_value"]),
                all_q_values=dict(request.action["all_q_values"]),
                state_vector=request.state_vector,
                original_severity=request.original_severity,
                confidence_bucket=str(request.confidence_log["tier"]).lower(),
                api_latency_ms=int(round((time.perf_counter() - start_perf) * 1000)),
                pipeline_elapsed_s=self._pipeline_elapsed_seconds(request, execution_start),
                api_status="failed",
                docker_response=str(exc),
                rollback_watch=request.rollback_watch,
                cascade_secondary_pending=request.cascade_secondary_pending,
                safety_overridden=request.safety_overridden,
                detection_timestamp=request.detection_timestamp,
            )
            self.registry.release(request.incident_id, request.service)
            self.publisher.publish(build_execution_failed_event(log, log.pipeline_elapsed_s))
            return log

        remaining = self.registry.cooldown_remaining(request.service, execution_start)
        if remaining > 0:
            log = self._build_log(
                request=request,
                target=target,
                execution_start=execution_start,
                start_perf=start_perf,
                action_type=request.requested_action_type,
                action_id=request.requested_action_id,
                api_status="blocked",
                docker_response=f"cooldown race condition caught in Executor ({remaining:.1f}s remaining)",
            )
            self.registry.release(request.incident_id, request.service)
            self.publisher.publish(build_cooldown_race_blocked_event(log, log.pipeline_elapsed_s))
            return log

        replica_count = self.runtime.get_replica_count(target.compose_service_name) if target.scalable else 1
        routed = self.router.route(request, target, replica_count)

        try:
            container = self.runtime.inspect_container(target.container_name)
            status = container.status
            if status == "paused":
                self.runtime.unpause_container(target.container_name)
                status = self.runtime.inspect_container(target.container_name).status

            if status == "removing":
                raise RuntimeErrorBase("container being removed, cannot act")

            response = self._dispatch_action(routed.effective_action_id, target, status, replica_count)
            log = self._build_log(
                request=request,
                target=target,
                execution_start=execution_start,
                start_perf=start_perf,
                action_type=routed.effective_action_type,
                action_id=routed.effective_action_id,
                api_status="success",
                docker_response=response,
                fallback_used=routed.fallback_used,
                fallback_reason=routed.fallback_reason,
            )
            self.registry.mark_action_fired(request.service, execution_start)
            if routed.fallback_used:
                self.publisher.publish(build_fallback_event(log, log.pipeline_elapsed_s))
            self.publisher.publish(build_action_fired_event(log, log.pipeline_elapsed_s))
            return log
        except (ContainerNotFoundError, RuntimeErrorBase) as exc:
            log = self._build_log(
                request=request,
                target=target,
                execution_start=execution_start,
                start_perf=start_perf,
                action_type=routed.effective_action_type,
                action_id=routed.effective_action_id,
                api_status="failed",
                docker_response=str(exc),
                fallback_used=routed.fallback_used,
                fallback_reason=routed.fallback_reason,
            )
            self.registry.release(request.incident_id, request.service)
            if routed.fallback_used:
                self.publisher.publish(build_fallback_event(log, log.pipeline_elapsed_s))
            self.publisher.publish(build_execution_failed_event(log, log.pipeline_elapsed_s))
            return log

    def _dispatch_action(
        self,
        action_id: int,
        target,
        status: str,
        replica_count: int,
    ) -> str:
        if action_id == ACTION_RESTART:
            if status == "running":
                return self.runtime.restart_container(target.container_name, self.config.restart_timeout_seconds)
            return self.runtime.start_container(target.container_name)

        if action_id == ACTION_SCALE_UP:
            desired = max(replica_count + 1, 2)
            return self.runtime.scale_service(target.compose_service_name, desired)

        if action_id == ACTION_SCALE_DOWN:
            desired = max(1, replica_count - 1)
            return self.runtime.scale_service(target.compose_service_name, desired)

        if action_id == ACTION_FORCE_KILL:
            self.runtime.kill_container(target.container_name)
            self.runtime.start_container(target.container_name)
            return "container force-killed and restarted"

        raise RuntimeErrorBase(f"unsupported action id: {action_id}")

    def _build_log(
        self,
        request: ExecutorRequest,
        target,
        execution_start: datetime,
        start_perf: float,
        action_type: str,
        action_id: int,
        api_status: str,
        docker_response: str,
        fallback_used: bool = False,
        fallback_reason: Optional[str] = None,
    ) -> ExecutionLog:
        execution_end = self._utc_now()
        pipeline_elapsed_s = self._pipeline_elapsed_seconds(request, execution_end)
        return ExecutionLog(
            incident_id=request.incident_id,
            service=request.service,
            container_name=target.container_name,
            compose_service_name=target.compose_service_name,
            action_type=action_type,
            action_id=action_id,
            requested_action_type=request.requested_action_type,
            requested_action_id=request.requested_action_id,
            source=str(request.action["source"]),
            q_value=float(request.action["q_value"]),
            all_q_values=dict(request.action["all_q_values"]),
            state_vector=request.state_vector,
            original_severity=request.original_severity,
            confidence_bucket=str(request.confidence_log["tier"]).lower(),
            execution_start=execution_start,
            execution_end=execution_end,
            api_latency_ms=int(round((time.perf_counter() - start_perf) * 1000)),
            pipeline_elapsed_s=pipeline_elapsed_s,
            api_status=api_status,
            docker_response=docker_response,
            rollback_watch=request.rollback_watch,
            cascade_secondary_pending=request.cascade_secondary_pending,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            safety_overridden=request.safety_overridden,
            detection_timestamp=request.detection_timestamp,
        )

    @staticmethod
    def _coerce_request(
        request: Union[ExecutorRequest, DecisionOutput, dict],
        incident_started_at: Optional[datetime],
        detection_timestamp: Optional[datetime],
    ) -> ExecutorRequest:
        if isinstance(request, ExecutorRequest):
            return request
        if isinstance(request, DecisionOutput):
            return ExecutorRequest.from_decision_output(
                request,
                incident_started_at=incident_started_at,
                detection_timestamp=detection_timestamp,
            )
        return ExecutorRequest.model_validate(request)

    @staticmethod
    def _pipeline_elapsed_seconds(request: ExecutorRequest, when: datetime) -> Optional[float]:
        reference = request.detection_timestamp or request.incident_started_at
        if reference is None:
            return None
        return round((when - reference).total_seconds(), 2)

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)
