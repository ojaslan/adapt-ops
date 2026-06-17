# ADAPT-OPS Quick Start Guide

Get ADAPT-OPS up and running in 5 minutes.

---

## Step 1: Clone & Install (1 minute)

```bash
git clone https://github.com/ojaslan/adapt-ops.git
cd adapt-ops

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
# or
venv\Scripts\activate            # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## Step 2: Run the Simulator (2 minutes)

Watch the system learn from 250 simulated pipeline runs:

```bash
python simulate.py
```

You'll see output like:

```
  [150] ✓  build_failure_spike        →  rollback_deployment       reward=0.706
  [151] ✓  test_flakiness_surge       →  prune_flaky_tests        reward=0.801
  [152] ✗  resource_exhaustion        →  scale_resources          reward=0.421
  
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
```

This shows:
- ✓ = successful healing
- ✗ = failed healing
- reward = how good the decision was

---

## Step 3: Start the API (1 minute)

In another terminal:

```bash
uvicorn api.main:app --reload
```

Server runs on `http://0.0.0.0:8000`

Check it's working:

```bash
curl http://127.0.0.1:8000/health
```

Response:
```json
{"status": "ok", "timestamp": 1699000000.123}
```

---

## Step 4: Send a Failure & Watch it Heal (1 minute)

Send a pipeline failure:

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

Response:
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

## Key API Endpoints

### Health Check
```bash
curl http://127.0.0.1:8000/health
```

### Send Pipeline Metrics (Main Endpoint)
```bash
curl -X POST http://127.0.0.1:8000/ingest -H "Content-Type: application/json" -d '{...}'
```

### System Status
```bash
curl http://127.0.0.1:8000/system/health | jq
```

### Recent Anomalies
```bash
curl http://127.0.0.1:8000/anomalies | jq
```

### Recent Healing Decisions
```bash
curl http://127.0.0.1:8000/decisions | jq
```

### Current MAB Rankings
```bash
curl http://127.0.0.1:8000/mab/rankings | jq
```

### System Configuration
```bash
curl http://127.0.0.1:8000/config | jq
```

---

## Understanding the Output

### Metrics to Send

```json
{
  "build_duration_secs": 180,         # How long the build takes
  "test_pass_rate": 0.95,              # Percentage of tests passing (0-1)
  "failure_rate": 0.05,                # Percentage of builds failing (0-1)
  "queue_depth": 2,                    # Number of builds waiting
  "cpu_utilization": 0.5,              # CPU usage percentage (0-1)
  "memory_utilization": 0.5,           # Memory usage percentage (0-1)
  "deploy_success_rate": 0.95,         # Percentage of successful deploys (0-1)
  "flaky_test_count": 0,               # Number of flaky tests
  "retry_count": 0                     # Number of retries needed
}
```

### Anomaly Types

- **build_failure_spike** - Too many builds failing
- **test_flakiness_surge** - Too many tests failing randomly
- **build_time_regression** - Builds taking longer than usual
- **resource_exhaustion** - CPU/Memory too high
- **queue_overflow** - Too many builds waiting

### Healing Actions

1. **retry_failed_step** - Re-run the build
2. **scale_resources** - Add more CI/CD runners
3. **prune_flaky_tests** - Skip unreliable tests
4. **rollback_deployment** - Revert to last working version
5. **parallelize_jobs** - Run jobs in parallel
6. **cache_dependencies** - Use caching
7. **skip_redundant_checks** - Skip unnecessary checks

---

## Next Steps

1. **Read the full README** for architecture details
2. **Check DEPLOYMENT.md** for production setup
3. **Review tests/** for code examples
4. **Integrate with GitHub Actions** (see `.github/workflows/`)

---

## Troubleshooting

### Port 8000 already in use?

```bash
# Use a different port
uvicorn api.main:app --port 8001 --reload
```

### ImportError: No module named 'core'

```bash
# Make sure you're in the right directory
cd adapt-ops
python -c "import sys; print(sys.path)"
```

### Need to reset the learning?

```bash
curl -X POST http://127.0.0.1:8000/reset
```

### Check API documentation

```bash
# Browser: http://127.0.0.1:8000/docs
# Or: http://127.0.0.1:8000/redoc
```

---

## Questions?

- Check README.md for detailed docs
- Check DEPLOYMENT.md for production setups
- Open an issue on GitHub
