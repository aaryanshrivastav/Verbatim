"""Tests for Component 5: Remediation Executor."""

from datetime import datetime, timedelta, timezone

import pytest

from decision_engine.events import InMemoryEventPublisher
from decision_engine.registry import DecisionRegistry
from remediation_executor.catalog import ServiceCatalog, ServiceTarget
from remediation_executor.models import ExecutorRequest
from remediation_executor.runtime import FakeDockerRuntime
from remediation_executor.service import RemediationExecutor


def build_catalog() -> ServiceCatalog:
    """Build a compact catalog for executor tests."""
    targets = {
        "payment": ServiceTarget("payment", "payment-service", "payment", False, False),
        "postgres": ServiceTarget("postgres", "postgres", "postgres", False, True),
        "worker": ServiceTarget("worker", "worker-service", "worker", True, False),
    }
    aliases = {"payment-service": "payment", "orders-db": "postgres"}
    return ServiceCatalog(targets=targets, aliases=aliases)


def build_request(service: str, action_id: int, action_type: str, incident_id: str = "inc-1") -> ExecutorRequest:
    """Return a minimal executor request for tests."""
    return ExecutorRequest(
        incident_id=incident_id,
        decision_timestamp=datetime.now(timezone.utc),
        detection_timestamp=datetime.now(timezone.utc) - timedelta(seconds=9),
        action={
            "service": service,
            "action_type": action_type,
            "action_id": action_id,
            "source": "rl_agent",
            "q_value": 1.23,
            "all_q_values": {
                "restart": 1.23,
                "scale_up": 0.87,
                "scale_down": -0.31,
                "force_kill": 0.94,
            },
        },
        confidence_log={"tier": "HIGH"},
        state_vector=[0, 0, 1, 0, 2, 1],
        original_severity=0.91,
        rollback_watch=False,
        cascade_secondary_pending=True,
    )


@pytest.mark.asyncio
async def test_executor_happy_path_restart():
    """Restart should fire against the mapped container and mark cooldown."""
    runtime = FakeDockerRuntime(containers={"payment-service": "running"})
    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    registry.reserve("inc-1", "payment")
    executor = RemediationExecutor(
        catalog=build_catalog(),
        runtime=runtime,
        registry=registry,
        publisher=publisher,
    )

    log = await executor.execute(build_request("payment", 0, "restart"))

    assert log.api_status == "success"
    assert log.action_type == "restart"
    assert runtime.calls == [("restart", "payment-service", 5)]
    assert publisher.events[-1].type == "ACTION_FIRED"
    assert registry.cooldown_remaining("payment") > 0


@pytest.mark.asyncio
async def test_executor_force_kill_db_falls_back_to_restart():
    """DB force-kill requests should fall back to restart and emit fallback visibility."""
    runtime = FakeDockerRuntime(containers={"postgres": "running"})
    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    registry.reserve("inc-2", "orders-db")
    executor = RemediationExecutor(
        catalog=build_catalog(),
        runtime=runtime,
        registry=registry,
        publisher=publisher,
    )

    log = await executor.execute(build_request("orders-db", 3, "force_kill", "inc-2"))

    assert log.api_status == "success"
    assert log.fallback_used is True
    assert log.action_type == "restart"
    assert publisher.events[0].type == "FALLBACK_USED"
    assert publisher.events[1].type == "ACTION_FIRED"


@pytest.mark.asyncio
async def test_executor_queue_processes_requests_sequentially():
    """Queued requests should execute one at a time through the single consumer flow."""
    runtime = FakeDockerRuntime(
        containers={"payment-service": "running", "worker-service": "running"},
        replica_counts={"worker": 2},
    )
    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    registry.reserve("inc-3", "payment")
    registry.reserve("inc-4", "worker")
    executor = RemediationExecutor(
        catalog=build_catalog(),
        runtime=runtime,
        registry=registry,
        publisher=publisher,
    )

    await executor.enqueue(build_request("payment", 0, "restart", "inc-3"))
    await executor.enqueue(build_request("worker", 2, "scale_down", "inc-4"))
    first = await executor.process_next()
    second = await executor.process_next()

    assert first.incident_id == "inc-3"
    assert second.incident_id == "inc-4"
    assert runtime.calls[0][0] == "restart"
    assert runtime.calls[1] == ("scale", "worker", 1)


@pytest.mark.asyncio
async def test_executor_container_not_found_fails_gracefully():
    """Missing containers should fail without crashing and release the reservation."""
    runtime = FakeDockerRuntime(containers={})
    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    registry.reserve("inc-5", "payment")
    executor = RemediationExecutor(
        catalog=build_catalog(),
        runtime=runtime,
        registry=registry,
        publisher=publisher,
    )

    log = await executor.execute(build_request("payment", 0, "restart", "inc-5"))

    assert log.api_status == "failed"
    assert publisher.events[-1].type == "EXECUTION_FAILED"
    assert registry.is_incident_active("inc-5") is False


@pytest.mark.asyncio
async def test_executor_cooldown_race_blocks_second_action():
    """Executor should catch cooldown races even after Decision already passed once."""
    runtime = FakeDockerRuntime(containers={"payment-service": "running"})
    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    registry.reserve("inc-6", "payment")
    executor = RemediationExecutor(
        catalog=build_catalog(),
        runtime=runtime,
        registry=registry,
        publisher=publisher,
    )

    first = await executor.execute(build_request("payment", 0, "restart", "inc-6"))
    registry.release(first.incident_id, first.service)
    registry.reserve("inc-7", "payment")
    second = await executor.execute(build_request("payment", 0, "restart", "inc-7"))

    assert first.api_status == "success"
    assert second.api_status == "blocked"
    assert publisher.events[-1].type == "COOLDOWN_RACE_BLOCKED"


def test_default_catalog_matches_component1_service_names():
    """Executor default aliases should match the service names emitted by ingestion."""
    from remediation_executor.catalog import build_default_catalog

    catalog = build_default_catalog()

    assert catalog.resolve("payment-service").container_name == "payment-service"
    assert catalog.resolve("auth-service").container_name == "auth-service"
    assert catalog.resolve("order-service").container_name == "order-service"
    assert catalog.resolve("gateway-service").container_name == "gateway-service"
    assert catalog.resolve("microservices-demo").container_name == "main-app"
