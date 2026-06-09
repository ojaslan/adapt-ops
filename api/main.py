import time
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from core.anomaly.detector import PipelineMetrics
from core.healer.orchestrator import AdaptOpsOrchestrator

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="ADAPT-OPS API",
    description="Adaptive DevOps Pipeline Optimizer — Self-Healing Engine",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = AdaptOpsOrchestrator(cooldown_secs=10.0, min_severity=2)


# ── Request model ────────────────────────────────────────────

class MetricsPayload(BaseModel):
    build_duration_secs: float
    test_pass_rate: float
    failure_rate: float
    queue_depth: int
    cpu_utilization: float
    memory_utilization: float
    deploy_success_rate: float
    flaky_test_count: int
    retry_count: int
    pipeline_id: Optional[str] = "default"


# ── Routes ───────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "name": "ADAPT-OPS",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": time.time()}


@app.post("/ingest")
def ingest(payload: MetricsPayload):
    """
    Main endpoint — CI/CD tools POST pipeline metrics here.
    System auto-detects anomalies and triggers healing.
    """
    metrics = PipelineMetrics(
        timestamp=time.time(),
        build_duration_secs=payload.build_duration_secs,
        test_pass_rate=payload.test_pass_rate,
        failure_rate=payload.failure_rate,
        queue_depth=payload.queue_depth,
        cpu_utilization=payload.cpu_utilization,
        memory_utilization=payload.memory_utilization,
        deploy_success_rate=payload.deploy_success_rate,
        flaky_test_count=payload.flaky_test_count,
        retry_count=payload.retry_count
    )

    decision = engine.ingest(metrics)

    if decision is None:
        return {
            "healing_triggered": False,
            "message": "No anomaly detected — pipeline healthy"
        }

    return {
        "healing_triggered": True,
        "decision": decision.to_dict()
    }


@app.get("/system/health")
def system_health():
    """Full system stats — for dashboard."""
    return engine.get_health()


@app.get("/anomalies")
def recent_anomalies():
    """Last 20 anomalies detected."""
    return {"anomalies": engine.detector.get_recent_events(20)}


@app.get("/decisions")
def recent_decisions():
    """Last 20 healing decisions."""
    return {
        "decisions": [d.to_dict() for d in engine.decision_log[-20:]]
    }