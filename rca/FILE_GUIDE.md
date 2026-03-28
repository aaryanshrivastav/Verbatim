"""FILE GUIDE: RCA Pipeline Navigation by Use Case"""

# RCA File Guide — Find What You Need

## Common Use Cases

### 🚀 "I want to get RCA running NOW"
1. [QUICKSTART.md](./QUICKSTART.md) ← Start here (5 min)
2. Run: `python -m rca.training`
3. Run: `python -m rca.example`
4. Done ✓

---

### 📖 "I want to understand the architecture"
1. Read: [README.md](./README.md) (Architecture section)
2. Review diagram: 7-module pipeline flow
3. Skim: [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md) (Section: 7-Module Pipeline)
4. Understanding: Complete ✓

---

### 🔧 "I need to set up RCA in my project"
1. [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md) ← Setup instructions
2. Follow: Steps 1–6 (Install → Train → Test → Integrate)
3. Check: Configuration section (env vars)
4. Setup: Complete ✓

---

### 🤖 "I want to use RCA in Python code"
1. Review: [models.py](./models.py) (Incident, RCAOutput contracts)
2. See: [example.py](./example.py) (Synthetic example)
3. Call: `RCAPipeline().analyze(incident)`
4. Integration: Complete ✓

---

### 🌐 "I want to expose RCA as HTTP API"
1. Run: `python -m rca.api --host 0.0.0.0 --port 8001`
2. POST to: `/analyze` endpoint
3. See: [api.py](./api.py) for details
4. API: Ready ✓

---

### 🔍 "I want to debug why RCA gives wrong answer"
1. Check: [README.md](./README.md) (Tuning Guide section)
2. Review: Evidence (Prometheus/Jaeger/Loki data)
3. Adjust: Config thresholds in [config.py](./config.py)
4. Retrain: `python -m rca.training` with new data
5. Debug: Complete ✓

---

### 📊 "I want to train a better ML model"
1. Review: [ml_ranker.py](./ml_ranker.py) (Module D)
2. Study: [training.py](./training.py) (offline training loop)
3. Collect: Production incidents with labels
4. Retrain: `python -m rca.training` or custom script
5. Deploy: Replace `rca/models/rca_model.pkl`
6. Training: Complete ✓

---

### 🧪 "I want to write tests"
1. See: [tests.py](./tests.py) (existing tests)
2. Patterns: Pytest fixtures, assertions
3. Modules: Each has public interface
4. Write: Your test cases
5. Run: `pytest rca/tests.py -v`
6. Testing: Complete ✓

---

### 🔗 "I want to integrate RCA with Part 2 (Detection)"
1. Read: [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md) (Section: Integration with Part 2)
2. Contract: Incident (input) → RCAOutput (output)
3. Code: Example in section
4. Connect: Feed Detection incidents to RCA
5. Integration: Complete ✓

---

### 📈 "I want to monitor RCA performance"
1. Metrics: Accuracy (% correct root causes)
2. Metrics: Confidence distribution (high/medium/low)
3. Metrics: Latency (time per incident)
4. See: [README.md](./README.md) (Advanced: ML Training Loop)
5. Monitoring: Set up ✓

---

### ⚙️ "I need to configure something"
1. File: [config.py](./config.py) ← All configuration
2. Settings: 14+ env vars (defaults provided)
3. Overrides: Service maps, thresholds, model path
4. Docs: [README.md](./README.md) (Configuration section)
5. Configuration: Updated ✓

---

## File Reference

### Core Pipeline

| File | Lines | Purpose |
|------|-------|---------|
| [core.py](./core.py) | 210 | Main orchestrator (RCAPipeline class) |
| [models.py](./models.py) | 180 | Pydantic data models |
| [config.py](./config.py) | 190 | Configuration + env vars |

### Modules A–G

| Module | File | Lines | Purpose |
|--------|------|-------|---------|
| A | [trace_graph_builder.py](./trace_graph_builder.py) | 180 | Query Jaeger, compute trace metrics |
| B | [candidate_extractor.py](./candidate_extractor.py) | 110 | Filter to high-probability candidates |
| C | [feature_builder.py](./feature_builder.py) | 90 | Build feature vectors |
| D | [ml_ranker.py](./ml_ranker.py) | 210 | ML scoring + fallback |
| E | [root_cause_selector.py](./root_cause_selector.py) | 90 | Select winner + confidence |
| F | [state_vector.py](./state_vector.py) | 70 | Build state vector for RL |
| G | [evidence_assembler.py](./evidence_assembler.py) | 220 | Gather evidence from 3 sources |

### Infrastructure

| File | Lines | Purpose |
|------|-------|---------|
| [ring_buffer.py](./ring_buffer.py) | 90 | Ring buffer for baselines (O(1) push) |
| [clients/jaeger_client.py](./clients/jaeger_client.py) | 250 | Jaeger HTTP API |
| [clients/prometheus_client.py](./clients/prometheus_client.py) | 200 | Prometheus HTTP API |
| [clients/loki_client.py](./clients/loki_client.py) | 180 | Loki HTTP API |

### Support

| File | Lines | Purpose |
|------|-------|---------|
| [training.py](./training.py) | 140 | Offline ML training |
| [example.py](./example.py) | 100 | Synthetic example |
| [api.py](./api.py) | 110 | FastAPI HTTP server (optional) |
| [tests.py](./tests.py) | 200 | Unit tests |

### Documentation

| File | Lines | Purpose |
|------|-------|---------|
| [README.md](./README.md) | 650 | Full reference (modules, tuning, troubleshooting) |
| [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md) | 450 | Setup + integration guide |
| [QUICKSTART.md](./QUICKSTART.md) | 150 | 5-minute quickstart |
| [COMPLETION_REPORT.md](./COMPLETION_REPORT.md) | 400 | What was implemented |
| [FILE_GUIDE.md](./FILE_GUIDE.md) | 300 | This file |

---

## Quick Import Reference

### Using RCA in Your Code

```python
# Main pipeline
from rca.core import RCAPipeline

# Data models
from rca.models import Incident, AnomalyDetail, RCAOutput

# Configuration
from rca.config import RCAConfig

# Example usage
pipeline = RCAPipeline()
rca_output = pipeline.analyze(incident)
```

### Testing

```python
import pytest
from rca.config import RCAConfig
from rca.candidate_extractor import CandidateExtractor
from rca.feature_builder import FeatureBuilder

config = RCAConfig()
extractor = CandidateExtractor(config)
# ... test code
```

---

## Code Organization Patterns

### Adding a New Module

1. Create `rca/new_module.py`
2. Define input/output (use Pydantic models)
3. Inherit/use RCAConfig
4. Call from `core.py` in pipeline order
5. Add tests in `tests.py`
6. Document in `README.md`

### Adding a New Client

1. Create `rca/clients/new_service_client.py`
2. HTTP requests with timeout/error handling
3. Return typed objects (not dicts)
4. Use in appropriate module (A–G)

### Updating Configuration

1. Add env var to `config.py`
2. Set default value
3. Document in `README.md` (Configuration section)
4. Use in relevant module

---

## Troubleshooting by File

| File | Common Issues |
|------|----------------|
| [core.py](./core.py) | Pipeline hangs → check module timeouts |
| [config.py](./config.py) | Wrong results → check thresholds |
| [trace_graph_builder.py](./trace_graph_builder.py) | No candidates → Jaeger not reachable? |
| [ml_ranker.py](./ml_ranker.py) | Low accuracy → retrain model |
| [evidence_assembler.py](./evidence_assembler.py) | Empty evidence → Prometheus/Loki labels |

---

## Performance by File

| File | Typical Latency |
|------|-----------------|
| User_input → [core.py](./core.py) | <1ms |
| [trace_graph_builder.py](./trace_graph_builder.py) | 150–500ms (Jaeger query) |
| [candidate_extractor.py](./candidate_extractor.py) | <5ms |
| [feature_builder.py](./feature_builder.py) | <5ms |
| [ml_ranker.py](./ml_ranker.py) | <20ms |
| [root_cause_selector.py](./root_cause_selector.py) | <1ms |
| [state_vector.py](./state_vector.py) | <1ms |
| [evidence_assembler.py](./evidence_assembler.py) | 100–300ms (external queries) |
| **Total** | **250–1000ms** |

Most time spent in Jaeger + evidence queries.

---

## Learning Path

### Level 1: Basic User (30 min)
1. [QUICKSTART.md](./QUICKSTART.md) (read)
2. [example.py](./example.py) (run)
3. Can run: `RCAPipeline.analyze(incident)`

### Level 2: Integration (1 hour)
1. [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md) (read)
2. [models.py](./models.py) (understand contracts)
3. [core.py](./core.py) (understand orchestration)
4. Can integrate with Part 2

### Level 3: Configuration (1–2 hours)
1. [README.md](./README.md) (full read)
2. [config.py](./config.py) (understand all options)
3. Deploy with custom thresholds
4. Can tune for your services

### Level 4: ML & Debugging (2–4 hours)
1. [training.py](./training.py) (understand training loop)
2. All module files (understand each A–G)
3. [tests.py](./tests.py) (understand testing)
4. Can retrain, debug, extend

### Level 5: Mastery (4+ hours)
1. All documentation + code
2. Can add new modules
3. Can optimize performance
4. Can contribute enhancements

---

## Version History

**March 28, 2026**: Initial implementation (v1.0)
- 7 modules (A–G) complete
- 21 files, 3,800+ lines code + docs
- 8+ unit tests
- Ready for production integration

---

## Getting Help

| Question | Answer Location |
|----------|-----------------|
| How do I start? | [QUICKSTART.md](./QUICKSTART.md) |
| How does it work? | [README.md](./README.md) (Architecture) |
| How do I set up? | [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md) |
| What was built? | [COMPLETION_REPORT.md](./COMPLETION_REPORT.md) |
| Where is X? | This file you're reading! 😊 |
| Code for feature X? | Search [core.py](./core.py) or module files |
| ML training? | [training.py](./training.py) |
| API? | [api.py](./api.py) |
| Tests? | [tests.py](./tests.py) |

---

**Q: Where should I start?**

**A**: Depends on your goal
- Just want to run it? → [QUICKSTART.md](./QUICKSTART.md)
- Want to integrate? → [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md)
- Want to understand? → [README.md](./README.md)

---

*Last updated: March 28, 2026*
