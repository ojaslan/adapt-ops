# ADAPT-OPS Architecture

Complete technical architecture of the ADAPT-OPS self-healing pipeline optimizer.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  CI/CD Pipeline Metrics                                         │
│  (GitHub Actions, Jenkins, GitLab, etc.)                       │
│           ↓                                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         ADAPT-OPS API Server (FastAPI)                  │  │
│  │                                                          │  │
│  │  POST /ingest ← Pipeline metrics arrive here           │  │
│  │        ↓                                                │  │
│  │  ┌────────────────────────────────────────────────┐    │  │
│  │  │  Anomaly Detection Module                      │    │  │
│  │  │  ─────────────────────────────────────────    │    │  │
│  │  │  • Z-score based statistical detection        │    │  │
│  │  │  • Multi-window historical analysis           │    │  │
│  │  │  • Classifies 5 anomaly types                 │    │  │
│  │  └────────────────────────────────────────────────┘    │  │
│  │        ↓ (if anomaly detected)                         │  │
│  │  ┌────────────────────────────────────────────────┐    │  │
│  │  │  Decision Engine (LinUCB Bandit)              │    │  │
│  │  │  ─────────────────────────────────────────   │    │  │
│  │  │  • Context extraction (16-dim vector)         │    │  │
│  │  │  • 7 healing action arms                      │    │  │
│  │  │  • UCB score calculation                      │    │  │
│  │  │  • Context-aware action selection             │    │  │
│  │  └────────────────────────────────────────────────┘    │  │
│  │        ↓ (selected action)                            │  │
│  │  ┌────────────────────────────────────────────────┐    │  │
│  │  │  Healing Executor (Simulated)                 │    │  │
│  │  │  ─────────────────────────────────────────   │    │  │
│  │  │  • Simulates action outcome                   │    │  │
│  │  │  • Calculates reward (success + time + cost)  │    │  │
│  │  │  • [TODO: Real GitHub Actions API integration]     │    │  │
│  │  └────────────────────────────────────────────────┘    │  │
│  │        ↓ (outcome)                                     │  │
│  │  ┌────────────────────────────────────────────────┐    │  │
│  │  │  Learning Module                              │    │  │
│  │  │  ─────────────────────────────────────────   │    │  │
│  │  │  • Update bandit arm weights                  │    │  │
│  │  │  • Record decision & outcome                 │    │  │
│  │  │  • Persist state to disk                     │    │  │
│  │  └────────────────────────────────────────────────┘    │  │
│  │        ↓                                                │  │
│  │  Response: Healing decision sent back to client        │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  GET /system/health ← Dashboard queries                      │
│  GET /mab/rankings ← Check current action rankings           │
│  GET /anomalies ← View recent anomalies                      │
│  GET /decisions ← View recent decisions                      │
│                                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Anomaly Detection (`core/anomaly/detector.py`)

**Purpose:** Detect pipeline anomalies in real-time

**Algorithm:** Z-score based statistical analysis

**Detects:**
- Build failure spike (failure_rate > 40% OR z_score > 2.5)
- Test flakiness surge (flaky_tests > 5 OR z_score > 2.5)
- Build time regression (z_score > 3.0)
- Resource exhaustion (CPU > 90% OR MEM > 85%)
- Queue overflow (queue_depth > 20 OR z_score > 2.5)

**Key Classes:**
- `PipelineMetrics` - 9-dimensional metric vector
- `AnomalyEvent` - Classified anomaly with severity
- `PipelineAnomalyDetector` - Detection engine
- `ZScoreDetector` - Per-metric Z-score tracker

**Severity Levels:**
- LOW (1) - Informational only
- MEDIUM (2) - May need attention
- HIGH (3) - Should be addressed
- CRITICAL (4) - Immediate action required

### 2. Decision Engine (`core/bandit/linucb.py`)

**Purpose:** Select optimal healing action using Contextual Multi-Armed Bandit

**Algorithm:** LinUCB (Linear Upper Confidence Bound)

**How it works:**
```
For each action arm:
  UCB_score = exploit + explore
  exploit = θ^T * x     (learned preference)
  explore = α * √(x^T * A^(-1) * x)  (uncertainty)

Select arm with highest UCB score
```

**Components:**
- `LinUCBArm` - Individual action arm with:
  - Design matrix A (16×16)
  - Reward vector b (16×1)
  - Regression weights θ = A^(-1) * b
  - Pull count and total reward

- `AdaptOpsMAB` - Bandit controller with:
  - 7 arms (one per healing action)
  - Context-aware decision making
  - Learning from outcomes
  - State persistence

**Reward Calculation:**
```
reward = 0.60 * success + 0.25 * time_improvement + 0.15 * cost_efficiency
```

### 3. Healer/Orchestrator (`core/healer/orchestrator.py`)

**Purpose:** Orchestrate the full decision-making pipeline

**Workflow:**
1. **Ingest** metrics
2. **Detect** anomalies
3. **Check severity** (skip if below threshold)
4. **Check cooldown** (prevent thrashing)
5. **Build context** vector
6. **Select action** via LinUCB
7. **Execute** healing (simulated)
8. **Record outcome** and update learning
9. **Persist** state

**Key Classes:**
- `AdaptOpsOrchestrator` - Main orchestrator
- `HealingDecision` - Decision record
- `HealingStatus` - Decision lifecycle tracking

**Cooldown Mechanism:**
Prevents repeated healing for the same issue within N seconds

### 4. API Server (`api/main.py`)

**Framework:** FastAPI

**Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/ingest` | Main entry point for metrics |
| GET | `/health` | Simple health check |
| GET | `/system/health` | Full system statistics |
| GET | `/anomalies` | Recent anomalies |
| GET | `/decisions` | Recent healing decisions |
| GET | `/mab/rankings` | Current action rankings |
| GET | `/config` | Configuration |
| GET | `/stats` | Extended stats |
| POST | `/reset` | Reset learning |

---

## Data Flow

### Ingest Flow

```
POST /ingest
  ↓
PipelineMetrics (validated by Pydantic)
  ↓
anomaly_detector.analyze(metrics)
  ↓
if anomaly AND severity >= min_severity AND cooldown passed:
  ↓
  build_context(metrics, anomaly)
  ↓
  mab.select_action(context)
  ↓
  execute_action(action, context)  [simulated]
  ↓
  update_mab(outcome)
  ↓
  save_state()  [if persistence enabled]
  ↓
  return decision
else:
  return None (no healing needed)
```

### Decision Context (16-dimensional)

```python
[
  1.0,                           # Bias term
  failure_rate_7d,               # 7-day failure rate
  avg_build_time_mins,           # Average build duration
  flaky_test_ratio,              # Flaky tests ratio
  queue_depth,                   # Builds in queue
  hour_of_day,                   # Time of day (0-1)
  is_peak_hours,                 # Binary: 9-18 UTC
  days_since_last_deploy,        # Deployment recency
  anomaly_score,                 # Anomaly severity (0-1)
  anomaly_type_build,            # Binary: build failure
  anomaly_type_test,             # Binary: test flakiness
  anomaly_type_deploy,           # Binary: deployment issue
  anomaly_type_resource,         # Binary: resource exhaustion
  commit_frequency,              # Commits per day
  team_size_bucket,              # Team size category
  branch_is_main,                # Binary: on main branch
]
```

---

## Healing Actions

### 1. Retry Failed Step
- **When:** Build failures
- **How:** Re-run failed step with exponential backoff
- **Success Rate:** ~72% (baseline)

### 2. Scale Resources
- **When:** Resource exhaustion (CPU/Memory high)
- **How:** Add more CI/CD runners
- **Success Rate:** ~65%

### 3. Prune Flaky Tests
- **When:** Test flakiness surge
- **How:** Quarantine and skip flaky tests
- **Success Rate:** ~80%

### 4. Rollback Deployment
- **When:** Critical deployment failures
- **How:** Revert to last known-good commit
- **Success Rate:** ~90%

### 5. Parallelize Jobs
- **When:** Queue overflow
- **How:** Split jobs across more runners
- **Success Rate:** ~60%

### 6. Cache Dependencies
- **When:** Slow build times
- **How:** Enable aggressive dependency caching
- **Success Rate:** ~75%

### 7. Skip Redundant Checks
- **When:** Peak hour slowdowns
- **How:** Skip low-value checks during peak
- **Success Rate:** ~55%

---

## State Persistence

### MAB State File (`.data/mab_state.json`)

```json
{
  "alpha": 1.0,
  "context_dim": 16,
  "decision_count": 250,
  "arms": {
    "retry_failed_step": {
      "action": "retry_failed_step",
      "A": [[...16x16 matrix...]],
      "b": [...16 element vector...],
      "n_pulls": 25,
      "total_reward": 18.025,
      "alpha": 1.0
    },
    ...
  }
}
```

**Load/Save:**
- Auto-loads on startup if `ENABLE_MAB_PERSISTENCE=true`
- Auto-saves after each healing decision
- Can be reset with `POST /reset`

---

## Performance Characteristics

### Latency
- Ingest → Anomaly detection: ~5ms
- Anomaly → Decision: ~10ms
- Decision → Execution: ~20ms
- **Total:** < 50ms per request

### Memory
- Base: ~50MB
- Per 1000 metrics: +5MB
- Default max history: 10,000 metrics (~50MB)

### CPU
- Z-score calculation: O(n) per metric
- LinUCB decision: O(d²) where d=16, ~256 ops
- Negligible CPU utilization

---

## Configuration

See `config.py` for full reference

**Key Parameters:**
- `MAB_ALPHA` - Exploration bonus (default: 1.0)
- `HEALING_COOLDOWN_SECS` - Min time between heals (default: 60)
- `HEALING_MIN_SEVERITY` - Min severity to trigger (default: 2)
- `ANOMALY_WINDOW_SIZE` - Historical window (default: 30)
- `ENABLE_MAB_PERSISTENCE` - Save state (default: true)

---

## Extension Points

### 1. Real Healing Executor
Replace `simulate_executor()` in orchestrator.py with:
- GitHub Actions API calls
- Jenkins API integration
- GitLab CI API integration

### 2. Additional Anomaly Types
Extend `AnomalyType` enum and add detection logic

### 3. Advanced MAB Algorithms
Replace LinUCB with:
- Thompson Sampling
- Contextual Thompson Sampling
- Neural Contextual Bandits

### 4. Dashboard
Build web UI consuming:
- `/system/health`
- `/mab/rankings`
- `/decisions`
- `/anomalies`

### 5. Metrics Export
Add Prometheus `/metrics` endpoint for:
- Prometheus scraping
- DataDog integration
- CloudWatch integration

---

## Testing

Run full test suite:

```bash
pytest tests/ -v
```

Test coverage:
- Anomaly detection
- MAB decision making
- Orchestrator workflow
- Integration tests

---

## Future Enhancements

1. **Multi-Pipeline Support** - Per-pipeline MAB models
2. **Contextual Features** - Team, repo, branch specific learning
3. **Feedback Loop** - Human approval of healing actions
4. **Webhooks** - GitHub/GitLab webhook triggers
5. **Dashboard** - Real-time visualization
6. **Advanced MAB** - Thompson Sampling, Neural networks
7. **Explainability** - Why action X was selected
8. **Cost Optimization** - Factor in runner costs

---

## Glossary

- **Arm** - One of 7 healing actions in the bandit
- **Context** - 16-dimensional feature vector for current state
- **Exploit** - Use best known action
- **Explore** - Try uncertain actions to learn
- **LinUCB** - Linear Upper Confidence Bound algorithm
- **MAB** - Multi-Armed Bandit
- **Reward** - Quality score of healing outcome (0-1)
- **UCB Score** - Upper Confidence Bound for action
- **Z-score** - Statistical measure of deviation from mean
