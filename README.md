# ADAPT-OPS ⚡

**Adaptive DevOps Pipeline Optimizer using Contextual Multi-Armed Bandit**

ADAPT-OPS watches your CI/CD pipeline in real-time, detects anomalies, and automatically heals failures — without any human intervention.

No rules. No hardcoding. It learns what works for *your* pipeline.

---

## How it works

```
Pipeline runs → Metrics collected → Anomaly detected → MAB selects best action → Heals → Learns from outcome
```

The brain is a **LinUCB Contextual Bandit** — it picks the best healing action based on the current pipeline context and gets smarter with every run.

---

## Healing actions

| Action | When it triggers |
|--------|-----------------|
| `retry_failed_step` | Build failure spike |
| `rollback_deployment` | Critical failure |
| `prune_flaky_tests` | Test flakiness surge |
| `scale_resources` | Resource exhaustion |
| `cache_dependencies` | Slow build times |
| `parallelize_jobs` | Queue overflow |
| `skip_redundant_checks` | Peak hour slowdowns |

---

## Quickstart

**1. Clone and install**
```bash
git clone https://github.com/ojaslan/adapt-ops.git
cd adapt-ops
python -m venv venv
venv\Scripts\activate        # Windows
pip install fastapi uvicorn numpy
```

**2. Run simulation — watch it learn**
```bash
python simulate.py
```

**3. Start the API server**
```bash
uvicorn api.main:app --reload
```

**4. Send a pipeline failure**
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
    "anomaly_type": "build_failure_spike",
    "severity": "CRITICAL",
    "action": "rollback_deployment",
    "status": "success",
    "reward": 0.706
  }
}
```

---

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/ingest` | Send pipeline metrics |
| `GET` | `/system/health` | Full system stats |
| `GET` | `/anomalies` | Recent anomalies |
| `GET` | `/decisions` | Recent healing decisions |
| `GET` | `/docs` | Interactive API docs |

---

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