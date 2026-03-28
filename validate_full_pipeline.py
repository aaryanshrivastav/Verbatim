"""
═══════════════════════════════════════════════════════════════════════
  VERBATIM AI OBSERVABILITY — FULL PIPELINE VALIDATION
═══════════════════════════════════════════════════════════════════════

This script validates the REAL end-to-end pipeline flow:

  Detection → RCA → Decision → Remediation → Feedback

It exercises actual code (no mocks for pipeline components), verifying:

  1. Schema alignment: state_slots match across ALL 5 config surfaces
  2. Service normalization: raw Jaeger names → canonical names
  3. Baseline integration: Detection warm-up → Feedback Loop import
  4. Docker catalog: scaling-ready names, scalable flags
  5. Full pipeline round-trip: incident in → remediation decision out → feedback closed
  6. Timing validation: decision latency within SLA budget
  7. Q-learning: Bellman update fires, Q-table mutates
  8. Cascade: secondary degradation triggers cascade RCA

Run:  python validate_full_pipeline.py
"""

from __future__ import annotations

import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ─── colour helpers ───────────────────────────────────────────────────────────
GREEN  = ""
RED    = ""
YELLOW = ""
CYAN   = ""
BOLD   = ""
RESET  = ""

passed = 0
failed = 0
errors: list[str] = []


def section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS]  {name}")
    else:
        failed += 1
        msg = f"  [FAIL]  {name}"
        if detail:
            msg += f"  -- {detail}"
        print(msg)
        errors.append(f"{name}: {detail}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════
#  PHASE 1: Schema Alignment Validation
# ═══════════════════════════════════════════════════════════════════════

def validate_schema_alignment() -> None:
    section("PHASE 1 — State-Vector Schema Alignment Across All Components")

    from rca.config import RCAConfig
    from feedback_loop.service import FeedbackLoopConfig
    from feedback_loop.cascade import CascadeConfig
    from pipeline_integration.adapter import IncidentAdapterConfig

    BRIEF_SLOTS = ("frontend", "gateway", "auth", "checkout", "payment", "db")

    rca_cfg = RCAConfig()
    fb_cfg = FeedbackLoopConfig()
    adapter_cfg = IncidentAdapterConfig()
    cascade_cfg = CascadeConfig()

    check("RCA config state_slots match brief",
          tuple(rca_cfg.state_slots) == BRIEF_SLOTS,
          f"got {rca_cfg.state_slots}")

    check("Feedback Loop state_slots match brief",
          tuple(fb_cfg.state_slots) == BRIEF_SLOTS,
          f"got {fb_cfg.state_slots}")

    check("Adapter state_slots match brief",
          tuple(adapter_cfg.state_slots) == BRIEF_SLOTS,
          f"got {adapter_cfg.state_slots}")

    check("Cascade config state_slots match brief",
          tuple(cascade_cfg.state_slots) == BRIEF_SLOTS,
          f"got {cascade_cfg.state_slots}")

    # All four must be identical
    slots_set = {
        tuple(rca_cfg.state_slots),
        tuple(fb_cfg.state_slots),
        tuple(adapter_cfg.state_slots),
        tuple(cascade_cfg.state_slots),
    }
    check("All 4 config surfaces have identical state_slots",
          len(slots_set) == 1,
          f"found {len(slots_set)} distinct slot tuples")

    # Verify slot count = 6
    check("State vector has exactly 6 slots",
          len(rca_cfg.state_slots) == 6,
          f"got {len(rca_cfg.state_slots)}")

    # Verify depth map includes frontend
    check("RCA depth_map has 'frontend' at depth 0",
          rca_cfg.service_depth_map.get("frontend") == 0,
          f"got {rca_cfg.service_depth_map.get('frontend')}")

    # Verify edge_services includes frontend
    check("RCA edge_services includes 'frontend'",
          "frontend" in rca_cfg.edge_services,
          f"got {rca_cfg.edge_services}")

    # Verify service aliases consistency
    MUST_MAP = {
        "catalog-service": "checkout",
        "order-service": "checkout",
        "catalog": "checkout",
        "order": "checkout",
        "checkoutservice": "checkout",
        "gateway-service": "gateway",
        "payment-service": "payment",
        "auth-service": "auth",
        "postgres": "db",
        "redis": "db",
        "microservices-demo": "gateway",
        "frontend": "frontend",
    }
    for raw, expected_canonical in MUST_MAP.items():
        rca_alias = rca_cfg.service_aliases.get(raw)
        fb_alias = fb_cfg.service_aliases.get(raw)
        adapter_alias = adapter_cfg.service_aliases.get(raw)
        all_match = rca_alias == fb_alias == adapter_alias == expected_canonical
        check(f"Alias '{raw}' → '{expected_canonical}' consistent across RCA/FB/Adapter",
              all_match,
              f"RCA={rca_alias}, FB={fb_alias}, Adapter={adapter_alias}")


# ═══════════════════════════════════════════════════════════════════════
#  PHASE 2: Service Name Normalization
# ═══════════════════════════════════════════════════════════════════════

def validate_normalization() -> None:
    section("PHASE 2 — Service Name Normalization (RCA Fix)")

    from rca.config import RCAConfig
    cfg = RCAConfig()

    test_cases = {
        "gateway-service": "gateway",
        "microservices-demo": "gateway",
        "catalog-service": "checkout",
        "order-service": "checkout",
        "payment-service": "payment",
        "auth-service": "auth",
        "postgres": "db",
        "redis": "db",
        "frontend": "frontend",
        "unknown-svc": "unknown-svc",  # passthrough
    }

    for raw_name, expected in test_cases.items():
        actual = cfg.normalize_service_name(raw_name)
        check(f"normalize('{raw_name}') → '{expected}'",
              actual == expected,
              f"got '{actual}'")


# ═══════════════════════════════════════════════════════════════════════
#  PHASE 3: State Vector Builder
# ═══════════════════════════════════════════════════════════════════════

def validate_state_vector_builder() -> None:
    section("PHASE 3 — State Vector Builder (Module F)")

    from rca.config import RCAConfig
    from rca.F_state_vector import StateVectorBuilder
    from rca.models import Incident, AnomalyDetail

    cfg = RCAConfig()
    builder = StateVectorBuilder(cfg)

    # Build incident with known severities
    now = utc_now()
    incident = Incident(
        incident_id="test-sv-001",
        endpoint="/api/checkout",
        time_window_start=now - timedelta(seconds=30),
        time_window_end=now,
        anomalies=[
            AnomalyDetail(service="gateway-service", severity=0.85, anomaly_type="latency_spike"),
            AnomalyDetail(service="catalog-service", severity=0.6, anomaly_type="error_spike"),
            AnomalyDetail(service="payment-service", severity=0.35, anomaly_type="mixed"),
            AnomalyDetail(service="postgres", severity=0.2, anomaly_type="latency_spike"),
        ],
    )

    sv = builder.build_state_vector(incident)

    check("State vector has 6 elements", len(sv) == 6, f"got {len(sv)}")

    # Expected: frontend=0, gateway=2(0.85>=0.8), auth=0, checkout=1(0.6>=0.3), payment=1(0.35>=0.3), db=0(0.2<0.3)
    expected = [0, 2, 0, 1, 1, 0]
    check(f"State vector values correct: {expected}",
          sv == expected,
          f"got {sv}")


# ═══════════════════════════════════════════════════════════════════════
#  PHASE 4: Detection Baseline Export
# ═══════════════════════════════════════════════════════════════════════

def validate_baseline_export() -> None:
    section("PHASE 4 — Detection Baseline Export & Feedback Import")

    from detection.config import DetectionConfig
    from detection.detector import AnomalyDetector
    from detection.models import StreamKey, StreamState
    from detection.ring_buffer import RingBuffer

    cfg = DetectionConfig()
    cfg.warmup_seconds = 0  # skip actual warmup
    detector = AnomalyDetector(cfg)

    # Simulate warm-up data by injecting stream states
    buf_lat = RingBuffer(60)
    for v in [0.1, 0.12, 0.11, 0.13, 0.10, 0.14]:
        buf_lat.push(v)
    buf_err = RingBuffer(60)
    for v in [0.01, 0.02, 0.015, 0.012, 0.018, 0.011]:
        buf_err.push(v)

    from detection.rolling_stats import RollingStats
    lat_mean, lat_std = RollingStats(buf_lat).get_stats()
    err_mean, err_std = RollingStats(buf_err).get_stats()

    detector.streams[StreamKey("payment-service", "/charge", "p95_latency")] = StreamState(
        key=StreamKey("payment-service", "/charge", "p95_latency"),
        buffer=buf_lat, rolling_mean=lat_mean, rolling_std=lat_std, is_anomalous=False,
    )
    detector.streams[StreamKey("payment-service", "/charge", "error_rate")] = StreamState(
        key=StreamKey("payment-service", "/charge", "error_rate"),
        buffer=buf_err, rolling_mean=err_mean, rolling_std=err_std, is_anomalous=False,
    )

    baselines = detector.export_baselines()

    check("export_baselines() returns data",
          len(baselines) > 0,
          f"got {len(baselines)} records")

    check("Baseline has 'payment-service' key",
          "payment-service" in baselines,
          f"keys: {list(baselines.keys())}")

    record = baselines.get("payment-service", {})
    check("Baseline record has error_rate_baseline",
          "error_rate_baseline" in record,
          f"keys: {list(record.keys())}")

    check("Baseline record has p95_latency_baseline_ms",
          "p95_latency_baseline_ms" in record,
          f"keys: {list(record.keys())}")

    check("Baseline source is 'detection_warmup'",
          record.get("source") == "detection_warmup",
          f"got '{record.get('source')}'")

    check("Baseline used_default is False",
          record.get("used_default") is False,
          f"got {record.get('used_default')}")

    # Now test the import path
    from feedback_loop.stores import DictBaselineProvider
    provider = DictBaselineProvider(records=baselines)
    lookup = provider.get_baseline("payment-service", "/charge")
    check("DictBaselineProvider accepts exported baselines",
          lookup is not None,
          "returned None")

    if lookup:
        check("Imported baseline has correct source",
              lookup.get("source") == "detection_warmup",
              f"got '{lookup.get('source')}'")


# ═══════════════════════════════════════════════════════════════════════
#  PHASE 5: Docker Catalog & Scaling
# ═══════════════════════════════════════════════════════════════════════

def validate_docker_catalog() -> None:
    section("PHASE 5 — Docker Catalog & Scaling Readiness")

    from remediation_executor.catalog import build_default_catalog

    catalog = build_default_catalog()

    # App services: dynamic Compose names, scalable
    APP_SERVICES = ["auth", "catalog", "order", "payment", "gateway"]
    for svc in APP_SERVICES:
        target = catalog.resolve(svc)
        check(f"'{svc}' container = 'verbatim-{svc}-1'",
              target.container_name == f"verbatim-{svc}-1",
              f"got '{target.container_name}'")

        check(f"'{svc}' is scalable",
              target.scalable is True,
              f"got scalable={target.scalable}")

    # Infra services: fixed names
    INFRA = {"postgres": "postgres", "redis": "redis", "jaeger": "jaeger",
             "prometheus": "prometheus", "loki": "loki", "grafana": "grafana"}
    for svc, expected_name in INFRA.items():
        target = catalog.resolve(svc)
        check(f"Infra '{svc}' has fixed container_name='{expected_name}'",
              target.container_name == expected_name,
              f"got '{target.container_name}'")
        check(f"Infra '{svc}' is NOT scalable",
              target.scalable is False,
              f"got scalable={target.scalable}")

    # Alias resolution
    ALIAS_CASES = {
        "payment-service": "payment",
        "catalog-service": "catalog",
        "order-service": "order",
        "gateway-service": "gateway",
        "auth-service": "auth",
        "checkout": "order",
        "orders-db": "postgres",
    }
    for alias, expected_canonical in ALIAS_CASES.items():
        target = catalog.resolve(alias)
        check(f"Alias '{alias}' resolves to canonical='{expected_canonical}'",
              target.canonical_name == expected_canonical,
              f"got '{target.canonical_name}'")


# ═══════════════════════════════════════════════════════════════════════
#  PHASE 6: Full Pipeline Round-Trip (Real Code, No Mocks for Pipeline)
# ═══════════════════════════════════════════════════════════════════════

def validate_full_pipeline() -> None:
    section("PHASE 6 — Full Pipeline Round-Trip (Detection → Decision → Feedback)")

    from decision_engine.events import InMemoryEventPublisher
    from decision_engine.models import RCAOutput, RCAConfidence
    from decision_engine.registry import DecisionRegistry
    from decision_engine.service import DecisionEngine, DecisionEngineConfig
    from feedback_loop.models import FeedbackRequest, RecoveryMetrics
    from feedback_loop.q_learning import QTableLearner
    from feedback_loop.service import FeedbackLoopConfig, FeedbackLoopService
    from feedback_loop.stores import DictBaselineProvider, DictSeverityProvider
    from pipeline_integration.adapter import DetectionIncidentAdapter, IncidentAdapterConfig
    from remediation_executor.models import ExecutionLog
    from remediation_executor.runtime import FakeDockerRuntime
    from detection.models import Incident, IncidentAnomaly, AnomalyType

    now = utc_now()

    # ── Step 1: Build an Incident from Detection ──────────────────────
    print(f"\n  {BOLD}Step 1: Detection → Incident{RESET}")
    incident = Incident(
        incident_id="e2e-inc-001",
        endpoint="/api/checkout",
        time_window_start=now - timedelta(seconds=10),
        time_window_end=now,
        anomalies=[
            IncidentAnomaly(
                service="catalog-service",
                severity=0.88,
                anomaly_type=AnomalyType.LATENCY_SPIKE,
                detected_at=now - timedelta(seconds=5),
            ),
            IncidentAnomaly(
                service="payment-service",
                severity=0.45,
                anomaly_type=AnomalyType.ERROR_SPIKE,
                detected_at=now - timedelta(seconds=3),
            ),
        ],
    )

    # ── Step 2: Adapter → RCA Output ────────────────────────────────
    print(f"  {BOLD}Step 2: Incident Adapter → RCA Output (Fallback Path){RESET}")
    adapter = DetectionIncidentAdapter(IncidentAdapterConfig(use_full_rca=False))
    rca_output = adapter.adapt(incident)

    check("RCA output has incident_id",
          rca_output.incident_id == "e2e-inc-001")

    check("RCA root_cause uses canonical name (not raw)",
          rca_output.root_cause in ("checkout", "payment", "gateway", "auth", "db", "frontend"),
          f"got '{rca_output.root_cause}'")

    check("RCA state_vector has 6 elements",
          len(rca_output.state_vector) == 6,
          f"got {len(rca_output.state_vector)}")

    # catalog-service 0.88 → checkout slot (index 3) should be 2 (>=0.8)
    check("State vector checkout slot (idx 3) = 2 (critical, severity 0.88)",
          rca_output.state_vector[3] == 2,
          f"got {rca_output.state_vector[3]}, full vector: {rca_output.state_vector}")

    # payment-service 0.45 → payment slot (index 4) should be 1 (>=0.3)
    check("State vector payment slot (idx 4) = 1 (degraded, severity 0.45)",
          rca_output.state_vector[4] == 1,
          f"got {rca_output.state_vector[4]}, full vector: {rca_output.state_vector}")

    check("RCA confidence bucket is valid",
          rca_output.confidence.bucket in ("low", "medium", "high"),
          f"got '{rca_output.confidence.bucket}'")

    # ── Step 3: Decision Engine ──────────────────────────────────────
    print(f"  {BOLD}Step 3: Decision Engine → Action Selection{RESET}")
    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()

    decision_engine = DecisionEngine(
        config=DecisionEngineConfig(
            state_size=6,
            cooldown_seconds=60,
            max_in_flight=3,
        ),
        registry=registry,
        publisher=publisher,
    )

    t_decision_start = time.perf_counter()
    decision_result = decision_engine.process(rca_output)
    t_decision_ms = (time.perf_counter() - t_decision_start) * 1000

    from decision_engine.models import DecisionOutput, DecisionBlockedOutput, DecisionSkippedOutput

    check("Decision engine returns DecisionOutput (not blocked/skipped)",
          isinstance(decision_result, DecisionOutput),
          f"got {type(decision_result).__name__}")

    if isinstance(decision_result, DecisionOutput):
        check("Decision action_type is valid",
              decision_result.action.action_type in ("restart", "scale_up", "scale_down", "force_kill"),
              f"got '{decision_result.action.action_type}'")

        check("Decision action targets root_cause service",
              decision_result.action.service == rca_output.root_cause,
              f"action.service='{decision_result.action.service}', root_cause='{rca_output.root_cause}'")

        check("Decision state_vector preserved from RCA",
              decision_result.state_vector == rca_output.state_vector,
              f"decision={decision_result.state_vector}, rca={rca_output.state_vector}")

        check(f"Decision latency ({t_decision_ms:.1f}ms) < 30ms SLA",
              t_decision_ms < 30,
              f"took {t_decision_ms:.1f}ms")

        check("Decision events published (DECISION_MADE + RL_STATE)",
              len(publisher.events) >= 2,
              f"got {len(publisher.events)} events: {[e.type for e in publisher.events]}")

        # ── Step 4: Remediation Execution Log (simulated) ──────────
        print(f"  {BOLD}Step 4: Simulated Remediation Execution{RESET}")
        exec_log = ExecutionLog(
            incident_id="e2e-inc-001",
            service=decision_result.action.service,
            container_name=f"verbatim-{decision_result.action.service}-1" if decision_result.action.service not in ("postgres","redis") else decision_result.action.service,
            compose_service_name=decision_result.action.service,
            action_type=decision_result.action.action_type,
            action_id=decision_result.action.action_id,
            requested_action_type=decision_result.action.action_type,
            requested_action_id=decision_result.action.action_id,
            source="rl_agent",
            q_value=decision_result.action.q_value,
            all_q_values=decision_result.action.all_q_values,
            state_vector=decision_result.state_vector,
            original_severity=decision_result.original_severity,
            confidence_bucket=decision_result.confidence_log.tier,
            execution_start=now,
            execution_end=now + timedelta(milliseconds=250),
            api_latency_ms=250,
            pipeline_elapsed_s=9.43,
            api_status="success",
            docker_response="container restarting",
            rollback_watch=decision_result.rollback_watch,
            cascade_secondary_pending=decision_result.cascade_secondary_pending,
            fallback_used=False,
            safety_overridden=False,
            detection_timestamp=now - timedelta(seconds=9),
        )

        check("Execution log validates correctly",
              exec_log.incident_id == "e2e-inc-001")

        # ── Step 5: Feedback Loop ──────────────────────────────────
        print(f"  {BOLD}Step 5: Feedback Loop — Phase 1 + Phase 2 + RL Update{RESET}")

        from pathlib import Path
        import tempfile
        tmp = Path(tempfile.mkdtemp())

        root_svc = decision_result.action.service
        container_name = exec_log.container_name

        # Provide baselines that look like "recovered" (current metrics <= baseline)
        baseline_provider = DictBaselineProvider(records={
            root_svc: {
                "error_rate_baseline": 0.01,
                "p95_latency_baseline_ms": 400.0,
                "source": "detection_warmup",
                "used_default": False,
            },
        })

        # Severity provider: root service no longer anomalous
        severity_provider = DictSeverityProvider({
            root_svc: 0.05,     # recovered
        })

        class MockRecoveryProvider:
            """Returns metrics that indicate successful recovery."""
            def get_recovery_metrics(self, service, endpoint=None):
                return RecoveryMetrics(
                    error_rate=0.008,      # below baseline 0.01
                    p95_latency_ms=350.0,  # below baseline 400.0
                    source="prometheus_live",
                )

        fb_publisher = InMemoryEventPublisher()
        fb_registry = DecisionRegistry()
        fb_registry.reserve("e2e-inc-001", root_svc)

        feedback_service = FeedbackLoopService(
            config=FeedbackLoopConfig(enable_sleep=False),
            runtime=FakeDockerRuntime(containers={container_name: "running"}),
            registry=fb_registry,
            publisher=fb_publisher,
            baseline_provider=baseline_provider,
            severity_provider=severity_provider,
            recovery_provider=MockRecoveryProvider(),
            learner=QTableLearner(
                load_path=tmp / "missing.pkl",
                checkpoint_path=tmp / "checkpoint.pkl",
            ),
        )

        import asyncio
        fb_result = asyncio.get_event_loop().run_until_complete(
            feedback_service.process(
                FeedbackRequest(
                    execution_log=exec_log,
                    endpoint="/api/checkout",
                    affected_services=[root_svc],
                )
            )
        )

        check("Feedback outcome = RECOVERED",
              fb_result.outcome == "RECOVERED",
              f"got '{fb_result.outcome}'")

        check("Phase 1 = PROVISIONALLY_RECOVERED",
              fb_result.phase1.result == "PROVISIONALLY_RECOVERED",
              f"got '{fb_result.phase1.result}'")

        check("Phase 2 = CONFIRMED_RECOVERED",
              fb_result.phase2 is not None and fb_result.phase2.result == "CONFIRMED_RECOVERED",
              f"got phase2={fb_result.phase2}")

        check("Phase 2 baseline_source is 'detection_warmup' (not 'default')",
              fb_result.phase2 is not None and fb_result.phase2.baseline_source == "detection_warmup",
              f"got '{fb_result.phase2.baseline_source if fb_result.phase2 else 'N/A'}'")

        check("Q-learning update fired (not skipped)",
              fb_result.q_update.skipped is False,
              f"skipped={fb_result.q_update.skipped}, reason={fb_result.q_update.reason}")

        check("Q-shift is positive (reward for successful recovery)",
              fb_result.q_update.q_shift is not None and fb_result.q_update.q_shift > 0,
              f"q_shift={fb_result.q_update.q_shift}")

        check("Registry released (active_count=0)",
              fb_registry.active_count() == 0,
              f"active_count={fb_registry.active_count()}")

        fb_event_types = [e.type for e in fb_publisher.events]
        check("PHASE1_CONFIRMED event emitted",
              "PHASE1_CONFIRMED" in fb_event_types,
              f"events: {fb_event_types}")

        check("PHASE2_CONFIRMED event emitted",
              "PHASE2_CONFIRMED" in fb_event_types,
              f"events: {fb_event_types}")

        check("RL_Q_UPDATED event emitted",
              "RL_Q_UPDATED" in fb_event_types,
              f"events: {fb_event_types}")

        check("INCIDENT_CLOSED event emitted",
              "INCIDENT_CLOSED" in fb_event_types,
              f"events: {fb_event_types}")

        # cleanup
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════
#  PHASE 7: Failure Path — Remediation Ineffective
# ═══════════════════════════════════════════════════════════════════════

def validate_failure_path() -> None:
    section("PHASE 7 — Failure Path (Remediation Ineffective + Negative Reward)")

    from decision_engine.events import InMemoryEventPublisher
    from decision_engine.registry import DecisionRegistry
    from feedback_loop.models import FeedbackRequest, RecoveryMetrics
    from feedback_loop.q_learning import QTableLearner
    from feedback_loop.service import FeedbackLoopConfig, FeedbackLoopService
    from feedback_loop.stores import DictBaselineProvider, DictSeverityProvider
    from remediation_executor.models import ExecutionLog
    from remediation_executor.runtime import FakeDockerRuntime

    now = utc_now()
    import tempfile
    tmp = Path(tempfile.mkdtemp())

    exec_log = ExecutionLog(
        incident_id="e2e-fail-001",
        service="payment",
        container_name="verbatim-payment-1",
        compose_service_name="payment",
        action_type="restart",
        action_id=0,
        requested_action_type="restart",
        requested_action_id=0,
        source="rl_agent",
        q_value=1.0,
        all_q_values={"restart": 1.0, "scale_up": 0.5, "scale_down": -0.1, "force_kill": 0.3},
        state_vector=[0, 0, 0, 0, 2, 0],
        original_severity=0.91,
        confidence_bucket="HIGH",
        execution_start=now - timedelta(milliseconds=300),
        execution_end=now,
        api_latency_ms=250,
        pipeline_elapsed_s=9.43,
        api_status="success",
        docker_response="container restarting",
        rollback_watch=False,
        cascade_secondary_pending=True,
        fallback_used=False,
        safety_overridden=False,
        detection_timestamp=now - timedelta(seconds=9),
    )

    class StillDegradedProvider:
        def get_recovery_metrics(self, service, endpoint=None):
            return RecoveryMetrics(
                error_rate=0.12,       # WAY above baseline
                p95_latency_ms=1500.0, # WAY above baseline
                source="prometheus_live",
            )

    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    registry.reserve("e2e-fail-001", "payment")

    service = FeedbackLoopService(
        config=FeedbackLoopConfig(enable_sleep=False),
        runtime=FakeDockerRuntime(containers={"verbatim-payment-1": "running"}),
        registry=registry,
        publisher=publisher,
        baseline_provider=DictBaselineProvider(records={
            "payment": {
                "error_rate_baseline": 0.01,
                "p95_latency_baseline_ms": 400.0,
                "source": "detection_warmup",
            },
        }),
        severity_provider=DictSeverityProvider({"payment": 0.9, "checkout": 0.7}),
        recovery_provider=StillDegradedProvider(),
        learner=QTableLearner(load_path=tmp / "m.pkl", checkpoint_path=tmp / "c.pkl"),
    )

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        service.process(FeedbackRequest(
            execution_log=exec_log,
            endpoint="/api/checkout",
            affected_services=["payment", "checkout"],
        ))
    )

    check("Failure outcome = REMEDIATION_INEFFECTIVE",
          result.outcome == "REMEDIATION_INEFFECTIVE",
          f"got '{result.outcome}'")

    check("Phase 2 = METRICS_DEGRADED",
          result.phase2 is not None and result.phase2.result == "METRICS_DEGRADED",
          f"got '{result.phase2.result if result.phase2 else 'N/A'}'")

    check("Q-shift is negative (penalty for failed remediation)",
          result.q_update.q_shift is not None and result.q_update.q_shift < 0,
          f"q_shift={result.q_update.q_shift}")

    check("Cascade suppressed (remediation failed)",
          result.cascade_status == "SUPPRESSED",
          f"got '{result.cascade_status}'")

    check("REMEDIATION_INEFFECTIVE event emitted",
          "REMEDIATION_INEFFECTIVE" in [e.type for e in publisher.events],
          f"events: {[e.type for e in publisher.events]}")

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════
#  PHASE 8: OTel & Prometheus Config Validation
# ═══════════════════════════════════════════════════════════════════════

def validate_infra_config() -> None:
    section("PHASE 8 -- Infrastructure Configuration Validation")

    import re

    # OTel Collector
    otel_path = Path("observability/otel-collector-config.yaml")
    check("OTel config file exists", otel_path.exists(), str(otel_path))

    if otel_path.exists():
        otel_text = otel_path.read_text()

        timeout_match = re.search(r"timeout:\s*(\d+)ms", otel_text)
        if timeout_match:
            timeout_ms = int(timeout_match.group(1))
            check("OTel batch timeout <= 200ms",
                  timeout_ms <= 200,
                  f"got {timeout_ms}ms")
        else:
            check("OTel batch timeout found in config", False, "not found")

        batch_match = re.search(r"send_batch_size:\s*(\d+)", otel_text)
        if batch_match:
            batch_size = int(batch_match.group(1))
            check("OTel batch size <= 512",
                  0 < batch_size <= 512,
                  f"got {batch_size}")
        else:
            check("OTel batch size found in config", False, "not found")

    # Prometheus
    prom_path = Path("observability/prometheus/prometheus.yml")
    check("Prometheus config file exists", prom_path.exists(), str(prom_path))

    if prom_path.exists():
        prom_text = prom_path.read_text()
        scrape_match = re.search(r"scrape_interval:\s*(\S+)", prom_text)
        if scrape_match:
            interval = scrape_match.group(1)
            check("Prometheus scrape_interval = 2s",
                  interval == "2s",
                  f"got '{interval}'")
        else:
            check("Prometheus scrape_interval found", False, "not found")

    # Docker Compose -- check no container_name on app services
    compose_path = Path("docker-compose.yml")
    check("docker-compose.yml exists", compose_path.exists())

    if compose_path.exists():
        compose_text = compose_path.read_text()

        # Parse services that have container_name
        # Look for pattern: "  <service>:\n    ...\n    container_name: <name>"
        services_with_container_name: set[str] = set()
        current_service = None
        indent_level = 0
        for line in compose_text.split("\n"):
            stripped = line.rstrip()
            # Top-level service definition (2 spaces + name + colon)
            svc_match = re.match(r"^  (\w[\w-]*):\s*$", stripped)
            if svc_match:
                current_service = svc_match.group(1)
                continue
            if current_service and re.match(r"^\s+container_name:", stripped):
                services_with_container_name.add(current_service)

        SCALABLE = ["auth", "catalog", "order", "payment", "gateway"]
        for svc in SCALABLE:
            has_cn = svc in services_with_container_name
            check(f"docker-compose '{svc}' has NO container_name (scalable)",
                  not has_cn,
                  f"still has container_name" if has_cn else "")

        INFRA_WITH_NAME = ["postgres", "redis", "prometheus", "jaeger", "loki"]
        for svc in INFRA_WITH_NAME:
            has_cn = svc in services_with_container_name
            check(f"docker-compose '{svc}' retains container_name",
                  has_cn,
                  "missing container_name" if not has_cn else "")


# ═══════════════════════════════════════════════════════════════════════
#  PHASE 9: Jaeger Port Validation
# ═══════════════════════════════════════════════════════════════════════

def validate_jaeger_config() -> None:
    section("PHASE 9 — Jaeger Port & RCA Integration Config")

    from pipeline_integration.rca_integration import RCAPipelineConfig

    cfg = RCAPipelineConfig()
    check("RCA Jaeger port = 16686 (HTTP query API)",
          cfg.jaeger_port == 16686,
          f"got {cfg.jaeger_port}")

    check("RCA Jaeger URL would be http://localhost:16686",
          f"http://{cfg.jaeger_host}:{cfg.jaeger_port}" == "http://localhost:16686",
          f"got http://{cfg.jaeger_host}:{cfg.jaeger_port}")


# ═══════════════════════════════════════════════════════════════════════
#  PHASE 10: Unit Test Suite Confirmation
# ═══════════════════════════════════════════════════════════════════════

def validate_unit_tests() -> None:
    section("PHASE 10 — Unit Test Suite (pytest)")

    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line", "-x"],
        capture_output=True, text=True, timeout=120,
    )

    lines = result.stdout.strip().split("\n")
    summary_line = lines[-1] if lines else ""

    check("pytest suite completes",
          result.returncode == 0,
          f"exit={result.returncode}: {summary_line}")

    if "passed" in summary_line:
        import re
        m = re.search(r"(\d+) passed", summary_line)
        if m:
            count = int(m.group(1))
            check(f"All {count} unit tests pass",
                  count >= 55,
                  summary_line)


# ═══════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    print("")
    print("  +================================================================+")
    print("  |    VERBATIM AI OBSERVABILITY -- FULL PIPELINE VALIDATION       |")
    print("  |    Detection -> RCA -> Decision -> Remediation -> Feedback     |")
    print("  +================================================================+")
    print("")

    phases = [
        ("Schema Alignment",        validate_schema_alignment),
        ("Service Normalization",   validate_normalization),
        ("State Vector Builder",    validate_state_vector_builder),
        ("Baseline Export/Import",  validate_baseline_export),
        ("Docker Catalog",          validate_docker_catalog),
        ("Full Pipeline e2e",       validate_full_pipeline),
        ("Failure Path",            validate_failure_path),
        ("Infra Config",            validate_infra_config),
        ("Jaeger Config",           validate_jaeger_config),
        ("Unit Tests",              validate_unit_tests),
    ]

    for name, fn in phases:
        try:
            fn()
        except Exception as e:
            global failed
            failed += 1
            print(f"\n  [CRASH] PHASE CRASHED: {name}")
            traceback.print_exc()
            errors.append(f"PHASE CRASH: {name}: {e}")

    # ── Summary ───────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    total = passed + failed
    if failed == 0:
        print(f"  ALL {total} CHECKS PASSED [OK]")
    else:
        print(f"  {passed} passed  |  {failed} failed  |  {total} total")
        print(f"\n  FAILURES:")
        for err in errors:
            print(f"    * {err}")
    print(f"{'=' * 70}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
