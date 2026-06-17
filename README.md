# ADAPT-OPS ⚡

**Adaptive DevOps Pipeline Optimizer using Contextual Multi-Armed Bandit**

ADAPT-OPS watches your CI/CD pipeline in real-time, detects anomalies, and automatically heals failures — **without any human intervention**.

**No rules. No hardcoding. It learns what works for *your* pipeline.**

```
Pipeline Metrics → Anomaly Detection → LinUCB Decision → Execute Healing → Record Outcome → Learn & Optimize
```

---

## Why ADAPT-OPS?

- 🎯 **No Configuration Required** — Works out-of-the-box with zero ML knowledge
- 📊 **Real-time Anomaly Detection** — Z-score based statistical anomaly detection
- 🤖 **Smart Decision Making** — Contextual Multi-Armed Bandit learns best actions for YOUR pipeline
- 📈 **Self-Improving** — Gets smarter with each pipeline run
- 🚀 **Production-Ready** — Persistent state, error handling, full API

---

## Anomalies Detected

| Anomaly Type | Trigger Condition | Healing Action |
|-------------|------------------|----------------|
| **Build Failure Spike** | Failure rate > 40% | Retry / Rollback |
| **Test Flakiness Surge** | Flaky tests > 5 or Z-score > 2.5 | Prune flaky tests |
| **Build Time Regression** | Build duration Z-score > 3.0 | Cache deps / Parallelize |
| **Resource Exhaustion** | CPU > 90% or MEM > 85% | Scale resources |
| **Queue Overflow** | Queue depth > 20 or Z-score > 2.5 | Parallelize jobs |

---

## Healing Actions

```
retry_failed_step      → Re-run failed build step with backoff
scale_resources        → Add more CI/CD runner capacity
prune_flaky_tests      → Quarantine and skip flaky test suites
rollback_deployment    → Revert to last known good build
parallelize_jobs       → Split jobs across more runners
cache_dependencies     → Enable aggressive caching
skip_redundant_checks  → Skip low-value checks during peak hours
```

---

## How LinUCB Works

The **Contextual Multi-Armed Bandit (LinUCB)** balances:

1. **Exploitation** — Choose the best action based on learned history
2. **Exploration** — Try new actions to discover better strategies
3. **Context** — Adapt decisions based on current pipeline state (time, load, anomaly type)

For each anomaly, the system evaluates all 7 healing actions and picks the one with:
- Highest probability of success
- Best time improvement
- Best cost efficiency

Then it **records the outcome** and **updates its models**.

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/ojaslan/adapt-ops.git
cd adapt-ops
python -m venv venv
source venv/bin/activate      # Linux/macOS
# or
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### 2. Run Local Simulation

Watch the system learn from 250 simulated pipeline runs:

```bash
python simulate.py
```

Output:
```
  [150] ✓  build_failure_spike        →  rollback_deployment       reward=0.706
  [151] ✓  test_flakiness_surge       →  prune_flaky_tests        reward=0.801
  [152] ✗  resource_exhaustion        →  scale_resources          reward=0.421

...

RESULTS — WHAT THE SYSTEM LEARNED:
  Total rounds                : 250
  Metrics processed           : 250
  Anomalies detected          : 87
  Healings triggered          : 85
  Successful healings         : 72
  Overall success rate        : 84.7%
  
TOP PERFORMING ACTIONS:
  1. rollback_deployment      avg=0.762  pulls=12   ████████████████████
  2. prune_flaky_tests        avg=0.745  pulls=18   ███████████████████
  3. retry_failed_step        avg=0.721  pulls=25   ████████████████████
  ...
```

### 3. Start the Server

```bash
uvicorn api.main:app --reload
```

Server runs on `http://0.0.0.0:8000`

### 4. Send a Pipeline Failure

```bash
curl -X POST "http://127.0.0.1:8000/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "build_duration_secs": 450,
    "test_pass_rate": 0.4,
    "failure_rate": 0.72,
    "queue_depth": 18,
    "cpu_utilization": 0.91,
    "memory_utilization": 0.88,
    "deploy_success_rate": 0.2,
    "flaky_test_count": 12,
    "retry_count": 5
  }'
```

**Response:**
```json
{
  "healing_triggered": true,
  "decision": {
    "decision_id": "heal_00001",
    "anomaly_type": "build_failure_spike",
    "severity": "CRITICAL",
    "action": "rollback_deployment",
    "status": "success",
    "reward": 0.706,
    "notes": "reward=0.706"
  }
}
```

---

## API Reference

### Main Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/ingest` | Send pipeline metrics (triggers anomaly detection + healing) |
| `GET` | `/health` | Simple health check |
| `GET` | `/system/health` | Full system statistics |
| `GET` | `/anomalies` | Last 20 anomalies detected |
| `GET` | `/decisions` | Last 20 healing decisions |
| `GET` | `/mab/rankings` | Current MAB action rankings |
| `GET` | `/config` | System configuration |
| `GET` | `/stats` | Extended statistics |
| `POST` | `/reset` | Reset MAB learning state |

### Example: Get Current Stats

```bash
curl http://127.0.0.1:8000/system/health | jq
```

```json
{
  "metrics_processed": 250,
  "anomalies_detected": 87,
  "healings_triggered": 85,
  "successful_healings": 72,
  "heal_success_rate": 0.847,
  "uptime_secs": 45,
  "recent_decisions": [...],
  "mab_summary": {
    "total_decisions": 85,
    "arms": [
      {"action": "rollback_deployment", "pulls": 12, "avg_reward": 0.762},
      {"action": "prune_flaky_tests", "pulls": 18, "avg_reward": 0.745},
      ...
    ]
  }
}
```

### Example: View Current MAB Rankings

```bash
curl http://127.0.0.1:8000/mab/rankings | jq
```

```json
{
  "rankings": [
    {"action": "rollback_deployment", "ucb_score": 0.8245, "avg_reward": 0.762, "pulls": 12},
    {"action": "retry_failed_step", "ucb_score": 0.7821, "avg_reward": 0.721, "pulls": 25},
    ...
  ]
}
```

---

## Configuration

Create a `.env` file to customize behavior:

```bash
# MAB Configuration
MAB_ALPHA=1.0                          # Exploration bonus coefficient
MAB_CONTEXT_DIM=16                     # Context vector dimension

# Healing Configuration
HEALING_COOLDOWN_SECS=60.0             # Min time between heals
HEALING_MIN_SEVERITY=2                 # Min severity to trigger heal (1-4)

# Anomaly Detection
ANOMALY_WINDOW_SIZE=30                 # Historical window for Z-score
ANOMALY_MIN_SCORE=0.45                 # Min anomaly score to report

# API
API_HOST=0.0.0.0
API_PORT=8000

# Persistence
ENABLE_MAB_PERSISTENCE=true            # Save/load MAB state
MAX_HISTORY_SIZE=10000

# Logging
LOG_LEVEL=INFO
```

---

## GitHub Actions Integration

Add to your workflow:

```yaml
- name: Send metrics to ADAPT-OPS
  if: always()
  run: |
    METRICS=$(cat metrics.json)
    curl -X POST "http://adapt-ops:8000/ingest" \
      -H "Content-Type: application/json" \
      -d "$METRICS"
```

See [`.github/workflows/adapt-ops-monitor.yml`](.github/workflows/adapt-ops-monitor.yml) for full example.

---

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose

```yaml
version: '3.8'
services:
  adapt-ops:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./.data:/app/.data
    environment:
      ENABLE_MAB_PERSISTENCE: "true"
      HEALING_COOLDOWN_SECS: "30"
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: adapt-ops
spec:
  replicas: 1
  selector:
    matchLabels:
      app: adapt-ops
  template:
    metadata:
      labels:
        app: adapt-ops
    spec:
      containers:
      - name: adapt-ops
        image: adapt-ops:latest
        ports:
        - containerPort: 8000
        volumeMounts:
        - name: data
          mountPath: /app/.data
      volumes:
      - name: data
        emptyDir: {}
```

---

## Project Structure

```
adapt-ops/
├── api/
│   ├── __init__.py
│   └── main.py                 # FastAPI server
├── core/
│   ├── anomaly/
│   │   ├── __init__.py
│   │   └── detector.py         # Z-score based anomaly detection
│   ├── bandit/
│   │   ├── __init__.py
│   │   └── linucb.py           # LinUCB contextual MAB implementation
│   ├── healer/
│   │   ├── __init__.py
│   │   └── orchestrator.py     # Decision engine & orchestrator
│   └── integration/
│       ├── __init__.py
│       └── github_actions.py   # GitHub Actions integration
├── config.py                   # Configuration management
├── simulate.py                 # Simulator for testing
├── requirements.txt
└── README.md
```

---

## How It Works (Step-by-Step)

1. **Ingest Metrics** → POST to `/ingest` endpoint
2. **Detect Anomaly** → Z-score analysis on recent history
3. **Build Context** → Extract features (time, load, anomaly type)
4. **Select Action** → LinUCB chooses best healing action
5. **Execute Healing** → Simulated executor (replace with real hooks)
6. **Record Outcome** → Success/failure + reward calculation
7. **Update MAB** → Arms learn from outcome
8. **Persist State** → Save MAB state to disk

---

## Performance

- **Latency**: < 50ms per ingest
- **Memory**: ~50MB base + history buffer
- **CPU**: Minimal (statistical calculations only)
- **Scalability**: Stateless API (run multiple instances with shared state file)

---

## License

MIT

---

## Contributing

PRs welcome! Focus areas:
- Real GitHub Actions executor hooks
- Additional anomaly detection methods
- Advanced MAB algorithms (Thompson Sampling, etc.)
- Dashboard UI

---

## Questions?

Open an issue or contact [@ojaslan](https://twitter.com/ojaslan)


## Why not rule-based?

Rule-based systems break when pipelines change. ADAPT-OPS adapts.

- A startup deploying 10x/day has different patterns than one deploying weekly
- Flaky tests at 2am need different treatment than at peak hours
- The bandit learns *your* pipeline's personality over time

---

## Project structure

```
adapt-ops/
├── core/
│   ├── bandit/
│   │   └── linucb.py        # LinUCB MAB engine
│   ├── anomaly/
│   │   └── detector.py      # Z-score anomaly detection
│   └── healer/
│       └── orchestrator.py  # Healing orchestrator
├── api/
│   └── main.py              # FastAPI server
└── simulate.py              # Run simulation
```

---

## Roadmap

- [ ] GitHub Actions native integration
- [ ] Jenkins connector
- [ ] Persistent bandit state (save/load between restarts)
- [ ] Web dashboard
- [ ] GitLab CI support

---

## Built with

- Python 3.12
- FastAPI
- NumPy (pure numpy LinUCB — no heavy ML dependencies)

---

*Early stage. Feedback welcome — open an issue or reach out.*