# Module D Training: ML Ranker Labeling Strategy

## Overview

### The Problem
We need to train a classifier to predict: **For a given service, is it the root cause of this incident?**

This is **binary classification** (0 = not root cause, 1 = root cause) that must handle the fact that incidents can have cascading effects where multiple services show anomalies.

### The Solution
Generate 200+ training examples using **synthetic failure scenarios**, then label them systematically based on a principled root cause identification strategy.

---

## Labeling Framework

### 1. The Key Insight: Temporal Primacy vs. Cascade

In distributed systems, root causes have distinct characteristics:

| Characteristic | Root Cause Service | Secondary (Affected) Service |
|---|---|---|
| **When it fails** | FIRST (t=10s) | Later (t=13-20s) |
| **Severity** | Typically HIGHEST | Lower (propagated effect) |
| **Dependencies** | Independent | May depend on root cause |
| **Recovery** | Sets the pattern | Follows recovery of root cause |

**Example:**
```
Time:  0s ──┬─────n─────────→
            │
DB (root):  ├─ Baseline ─────┬─ SPIKE @ t=10 ─ HIGH ────→
            │                 
Catalog:    ├─ Baseline ─────────────┬─ SPIKE @ t=13 ─ MEDIUM ──→
            │
Order:      ├─ Baseline ─────────────────┬─ SPIKE @ t=16 ─ MEDIUM ──→
            │
            └─ Cascade delay demonstrates propagation path
```

### 2. Labeling Algorithm

For each synthetic incident scenario:

#### Step 1: Identify Primary Root Cause
```python
def find_root_cause(scenario):
    # Root cause is KNOWN in synthetic data (from ScenarioGenerator)
    return scenario.root_cause_service  # e.g., "db", "auth-service", "redis"
```

#### Step 2: For Each Affected Service, Create Training Example
```python
for service in scenario.affected_services:
    # Extract time-series metrics
    metrics = scenario.metrics[service]
    
    # Detect first deviation time
    first_deviation_t = find_first_anomaly(metrics)
    
    # Assign label
    if service == root_cause:
        label = 1  # Root cause
        confidence = 0.98  # Very sure
    elif depends_on(service, root_cause):
        label = 0  # Secondary (affected by root cause)
        confidence = 0.95  # High confidence it's NOT root cause
    else:
        label = 0  # Coincidental or unrelated
        confidence = 0.80  # Less sure, but still marked as non-cause
```

#### Step 3: Store Transparent Labeling Rationale
```python
{
    "example_id": "scenario_db_5_service_catalog",
    "service": "catalog-service",
    "label": 0,
    "label_confidence": 0.95,
    "labeling_rationale": {
        "method": "temporal_primacy_and_dependency",
        "root_cause_service": "db",
        "this_service_first_deviation_time": 13,
        "root_cause_first_deviation_time": 10,
        "time_lag_seconds": 3,
        "depends_on_root_cause": true,
        "reasoning": "catalog-service depends on db and was affected 3s after DB failed"
    }
}
```

---

## The 7 Failure Types & Edge Cases

### 1. **DB Failure** → Slow Queries Cascade
**Root Cause:** `db`  
**Affected:** `catalog-service`, `order-service`, `payment-service`  
**Propagation:** 0s → DB latency spikes → dependent services' latency follows  
**Labels:**
- `db`: label=1 (root cause)
- `catalog-service`: label=0 (depends on db)
- `order-service`: label=0 (depends on db)
- `payment-service`: label=0 (depends on db)

### 2. **Redis (Cache) Failure** → DB Overload
**Root Cause:** `redis`  
**Affected:** `catalog-service`, `auth-service`, `payment-service`  
**Propagation:** Cache miss → DB hit spike → downstream latency  
**Labels:**
- `redis`: label=1
- All others: label=0

### 3. **API Gateway DDoS** → Saturation
**Root Cause:** `gateway`  
**Affected:** All downstream services  
**Propagation:** Gateway becomes bottleneck → all services slow  
**Labels:**
- `gateway`: label=1
- All others: label=0

### 4. **Auth Service Overload** → Login Bottleneck
**Root Cause:** `auth-service`  
**Affected:** `order-service` (depends on auth), `gateway`  
**Labels:**
- `auth-service`: label=1
- `order-service`: label=0 (affects orders indirectly)

### 5. **Payment Timeout** → Deep Chain
**Root Cause:** `payment-service`  
**Affected:** `order-service` (waits for payment), `gateway`  
**Propagation:** Payment slow → order slow (1-2s lag)  
**Labels:**
- `payment-service`: label=1
- `order-service`: label=0 (depends on payment)

### 6. **SQL Injection** → Silent DB Load
**Root Cause:** `db` (via malicious query on specific endpoint)  
**Affected:** Auth/Catalog services  
**Pattern:** Latency-only spike (no errors), targets `/api/auth/login`  
**Labels:**
- `db`: label=1
- `auth-service`: label=0 (affected endpoint)

### 7. **Retry Storm** → Amplification Loop
**Root Cause:** `payment-service` (initial failure)  
**Affected:** All services in chain  
**Pattern:** Request rate amplified 3-5x, latency/error both spike  
**Labels:**
- `payment-service`: label=1 (triggered retries)
- `order-service`: label=0 (retry multiplier applied but not root)

---

## Dataset Statistics

Generated dataset through `generate_synthetic_training_data.py`:

```
Total scenarios: 200+
Total training examples: 600-900 (3-4 services affected per scenario)

Label distribution:
  - Root cause (label=1): ~200 examples (20-25%)
  - Not root cause (label=0): ~600 examples (75-80%)
  
Class balance: Naturally imbalanced
  Highly realistic: 1 root cause per incident, N-1 non-causes
  Solution: LogisticRegression(class_weight='balanced')
             or RandomForest(class_weight='balanced')

Failure type distribution:
  - DB failure: ~80 examples
  - Redis failure: ~80 examples
  - Gateway DDoS: ~60 examples
  - Auth overload: ~50 examples
  - Payment timeout: ~80 examples
  - SQL injection: ~50 examples
  - Retry storm: ~50 examples

Anomaly types:
  - latency_spike: ~450 examples
  - error_spike: ~300 examples
  - mixed: ~100 examples
```

---

## Production Labeling (Beyond Synthetic Data)

In production, incident root causes come from:

1. **Post-Mortem Analysis** (Best)
   - Manual expert review of logs, traces, metrics
   - Written incident report identifies root cause
   - Label with confidence=0.95+

2. **Automatic Pattern Matching** (Good)
   - Correlate with known-good incident templates
   - e.g., "If error rate spikes in payment and latency in order, payment is root"
   - Label with confidence=0.80-0.90

3. **Distributed Tracing** (Emerging)
   - RPC trace analysis shows where requests originate failures
   - Jaeger spans reveal error propagation
   - Label with confidence=0.85-0.95

4. **Time-Series Analysis** (Heuristic)
   - Use onset time + severity to guess root cause
   - Works well for clear cascades, fails for simultaneous failures
   - Label with confidence=0.60-0.75

5. **Crowdsourced Review** (Affordable)
   - Human labelers review incidents
   - Vote on most likely root cause
   - Label with majority confidence

### Example: Production Labeling
```json
{
    "incident_id": "prod_2026_03_28_incident_1042",
    "service": "payment-service",
    "label": 1,
    "label_confidence": 0.92,
    "labeling_method": "distributed_trace_analysis",
    "labeling_rationale": {
        "method": "jaeger_rpc_analysis",
        "reasoning": "Jaeger spans show error originating in payment-service/charge endpoint, propagating to order-service after 2s",
        "sources": [
            "incident_postmortem.md",
            "jaeger_trace_id: 6d3cb26fb2ef440",
            "datadog_dashboard_snapshot: 2026-03-28T11:15:00Z"
        ]
    }
}
```

---

## Theoretical Justification

### Why This Labeling Works

1. **Temporal Primacy is Reliable**
   - Root causes ALWAYS deviate first (by definition)
   - Propagation introduces lag (network, queueing, retries)
   - No other heuristic captures cascade timing as cleanly

2. **Dependency Graph Validation**
   - If A depends on B and both have anomalies, B is likely root
   - Removes ambiguity in simultaneous failures
   - Aligns with system architecture

3. **Synthetic Data Advantage**
   - We CONTROL failure injection points
   - Can label data 100% accurately (not guessing)
   - Can generate diverse edge cases systematically
   - Trains classifier on clean, unambiguous examples

4. **Class Imbalance is Natural**
   - 1 root cause per incident, N-1 secondary services
   - Imbalanced training data matches real-world distribution
   - Classifier learns this naturally; no need to oversample
   - `class_weight='balanced'` handles it correctly

### Why Synthetic Data > Production Data for Init Training

| Aspect | Synthetic | Production |
|---|---|---|
| **Labeling accuracy** | 100% known | 60-80% estimated |
| **Edge case coverage** | Designed (7 types x shapes) | Random, sparse |
| **Volume** | 200-1000 examples | Weeks/months to collect |
| **Bias** | Controlled | Unknown biases |
| **Time to train** | Hours | Weeks |

**Recommendation:** 
1. Train initial model on synthetic data (hours)
2. Deploy model to production
3. Continuously collect real incidents
4. Fine-tune model on production data (monthly)

---

## Validation Strategy

### Testing the Labeler

```python
# For each scenario, verify labels make sense
scenario = db_failure_scenario_slow_ramp()

# Expected:
assert scenario.root_cause_service == "db"
assert has_label(scenario, service="db", label=1)
assert all(has_label(scenario, service=s, label=0) 
           for s in ["catalog-service", "order-service", "payment-service"])

# Check timing was captured
assert get_rationale(scenario, "catalog-service")["time_lag_seconds"] > 0

# Check confidence scores make sense
assert get_confidence(scenario, "db") > 0.95
assert 0.75 < get_confidence(scenario, "catalog-service") < 0.98
```

### Testing the Model

```python
# Train on synthetic data
model = LogisticRegression(class_weight='balanced')
model.fit(X_train_synthetic, y_train_synthetic)

# Evaluate on test split
auc = roc_auc_score(y_test_synthetic, model.predict_proba(X_test_synthetic)[:, 1])
assert auc > 0.85, f"Synthetic test AUC too low: {auc}"

# Verify it learns the patterns
for scenario_type in [db_failure, redis_failure, auth_overload]:
    X = build_features(scenario_type())
    probs = model.predict_proba(X)
    assert is_high_confidence(probs), f"Model uncertain on {scenario_type}"
```

---

## Summary

**The Labeling Strategy:**
1. Use TEMPORAL PRIMACY (who failed first?) as primary signal
2. Validate with DEPENDENCY GRAPH (who depends on whom?)
3. Store TRANSPARENT RATIONALE (explain every label)
4. Accept NATURAL CLASS IMBALANCE (1 root, N-1 affected)
5. Use SYNTHETIC DATA for initial training (precise labels, diverse cases)

**Why It Works:**
- Mirrors how humans identify root causes
- Leverages system architecture knowledge
- Produces high-quality training data
- Scales to 200+ diverse scenarios

**Next Steps:**
```bash
cd d:\Verbatim
python rca/generate_synthetic_training_data.py --scenarios 200
python rca/train_ml_ranker.py --input training_data/training_examples_synthetic.jsonl
```
