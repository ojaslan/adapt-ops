"""
Complete ADAPT-OPS API with all endpoints.
"""

import time
import logging
import hmac
import hashlib
import json
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import atexit

from core.anomaly.detector import PipelineMetrics
from core.healer.orchestrator import AdaptOpsOrchestrator
from core.persistence import MetricStore, AnomalyStore, HealingStore
import config

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ADAPT-OPS API",
    description="Adaptive DevOps Pipeline Optimizer — Self-Healing Engine",
    version="0.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core engine
engine = AdaptOpsOrchestrator(
    cooldown_secs=config.HEALING_COOLDOWN_SECS,
    min_severity=config.HEALING_MIN_SEVERITY
)

# Persistence stores
metric_store = MetricStore()
anomaly_store = AnomalyStore()
healing_store = HealingStore()

def shutdown_engine():
    engine.shutdown()

atexit.register(shutdown_engine)


# ── Request Models ──────────────────────────────────────────

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


class GitHubWebhookPayload(BaseModel):
    """GitHub Actions workflow_run webhook payload."""
    action: str
    workflow_run: Dict[str, Any]
    repository: Optional[Dict[str, Any]] = None


class ManualHealingRequest(BaseModel):
    """Manual healing trigger."""
    anomaly_type: str
    action: str
    context: Optional[Dict[str, Any]] = None


class ConfigUpdate(BaseModel):
    """Update engine configuration."""
    mab_alpha: Optional[float] = None
    cooldown_secs: Optional[float] = None
    min_severity: Optional[int] = None


# ── Core Routes ──────────────────────────────────────────

@app.get("/")
def root():
    return {
        "name": "ADAPT-OPS",
        "version": "0.2.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "timestamp": time.time(),
        "engine_status": "ready"
    }


# ── Metrics Ingestion ────────────────────────────────────

@app.post("/ingest")
def ingest(payload: MetricsPayload):
    """
    Main endpoint — CI/CD tools POST pipeline metrics here.
    System auto-detects anomalies and triggers healing.
    """
    try:
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

        # Process through engine
        decision = engine.ingest(metrics)
        
        # Store metrics
        metric_dict = metrics.__dict__.copy()
        metric_dict['pipeline_id'] = payload.pipeline_id
        metric_dict['anomaly_detected'] = decision is not None
        
        if decision:
            metric_dict['anomaly_type'] = decision.anomaly_type
            metric_dict['healing_action'] = decision.action
            metric_dict['healing_triggered'] = True
            metric_dict['healing_successful'] = getattr(decision, 'success', False)
            
            # Record to stores
            anomaly_store.record_anomaly(
                anomaly_type=decision.anomaly_type,
                severity=decision.severity,
                score=decision.anomaly_score,
                context={'pipeline_id': payload.pipeline_id}
            )
            healing_store.record_healing(
                anomaly_type=decision.anomaly_type,
                action=decision.action,
                success=getattr(decision, 'success', False),
                reward=decision.reward
            )
        else:
            metric_dict['healing_triggered'] = False
        
        metric_store.append_metric(metric_dict)
        
        # Save MAB state
        if config.ENABLE_MAB_PERSISTENCE:
            engine._save_mab_state()

        response = {
            "status": "processed",
            "timestamp": time.time(),
            "pipeline_id": payload.pipeline_id
        }
        
        if decision:
            response["decision"] = {
                "anomaly": decision.anomaly_type,
                "severity": decision.severity,
                "action": decision.action,
                "reward": round(decision.reward, 3),
                "confidence": round(decision.anomaly_score, 3)
            }
        
        return response
        
    except Exception as e:
        logger.error(f"Error processing metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── GitHub Actions Integration ───────────────────────────

def verify_github_signature(request_body: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature."""
    if not config.GITHUB_WEBHOOK_SECRET:
        return True  # No verification if secret not set
    
    expected = "sha256=" + hmac.new(
        config.GITHUB_WEBHOOK_SECRET.encode(),
        request_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None)
):
    """
    GitHub Actions workflow_run webhook endpoint.
    Extracts metrics from workflow and triggers ADAPT-OPS.
    """
    try:
        body = await request.body()
        
        # Verify signature
        if x_hub_signature_256 and not verify_github_signature(body, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        payload = json.loads(body)
        
        if payload.get("action") != "completed":
            return {"status": "ignored", "reason": "not completed"}
        
        workflow_run = payload.get("workflow_run", {})
        run_id = workflow_run.get("id")
        repo_name = payload.get("repository", {}).get("full_name", "unknown")
        
        # Extract metrics from workflow
        build_duration = (workflow_run.get("updated_at") and 
                         workflow_run.get("run_started_at") and
                         (time.time() - time.mktime(time.strptime(
                             workflow_run.get("run_started_at"), "%Y-%m-%dT%H:%M:%SZ")))) or 0
        
        # Simplified metrics — in production, call GitHub API for detailed logs
        metrics = MetricsPayload(
            build_duration_secs=max(build_duration, 1),
            test_pass_rate=1.0 if workflow_run.get("conclusion") == "success" else 0.7,
            failure_rate=0.0 if workflow_run.get("conclusion") == "success" else 0.3,
            queue_depth=0,
            cpu_utilization=0.5,
            memory_utilization=0.6,
            deploy_success_rate=1.0 if workflow_run.get("conclusion") == "success" else 0.5,
            flaky_test_count=0,
            retry_count=workflow_run.get("run_attempt", 1) - 1,
            pipeline_id=f"github-{repo_name}-{run_id}"
        )
        
        return ingest(metrics)
        
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Statistics & Analytics ──────────────────────────────

@app.get("/stats")
def get_stats(hours: int = 24):
    """Overall system statistics."""
    return {
        "timestamp": time.time(),
        "metrics": metric_store.get_stats_summary(hours),
        "anomalies": anomaly_store.get_anomaly_stats(),
        "actions": healing_store.get_action_performance()
    }


@app.get("/metrics/recent")
def get_recent_metrics(limit: int = 50, hours: int = 24):
    """Fetch recent metrics."""
    metrics = metric_store.get_metrics(limit, hours)
    return {"count": len(metrics), "metrics": metrics}


@app.get("/anomalies")
def get_anomalies(
    limit: int = 50,
    anomaly_type: Optional[str] = None
):
    """Fetch recent anomalies."""
    anomalies = anomaly_store.get_anomalies(limit, anomaly_type)
    return {"count": len(anomalies), "anomalies": anomalies}


@app.get("/healings")
def get_healings(
    limit: int = 50,
    action: Optional[str] = None
):
    """Fetch recent healing attempts."""
    healings = healing_store.get_healings(limit, action)
    return {"count": len(healings), "healings": healings}


@app.get("/mab/state")
def get_mab_state():
    """Fetch current MAB state and arm estimates."""
    bandit = engine.bandit
    return {
        "round": engine.round,
        "total_actions": len(bandit.arms),
        "arms": [
            {
                "action": arm.action,
                "estimated_mean": round(arm.mu, 3),
                "pulls": arm.count,
                "successes": arm.successes
            }
            for arm in bandit.arms
        ]
    }


# ── Manual Control ───────────────────────────────────────

@app.post("/healing/manual")
def trigger_manual_healing(request: ManualHealingRequest):
    """Manually trigger healing action."""
    try:
        # Log the manual action
        healing_store.record_healing(
            anomaly_type=request.anomaly_type,
            action=request.action,
            success=True,
            reward=0.5,
            metadata={"manual": True, "context": request.context}
        )
        
        return {
            "status": "triggered",
            "action": request.action,
            "anomaly": request.anomaly_type
        }
    except Exception as e:
        logger.error(f"Manual healing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/config")
def update_config(update: ConfigUpdate):
    """Update runtime configuration."""
    if update.mab_alpha is not None:
        config.MAB_ALPHA = update.mab_alpha
    if update.cooldown_secs is not None:
        config.HEALING_COOLDOWN_SECS = update.cooldown_secs
    if update.min_severity is not None:
        config.HEALING_MIN_SEVERITY = update.min_severity
    
    return {
        "status": "updated",
        "config": {
            "mab_alpha": config.MAB_ALPHA,
            "cooldown_secs": config.HEALING_COOLDOWN_SECS,
            "min_severity": config.HEALING_MIN_SEVERITY
        }
    }


# ── Debug Routes ────────────────────────────────────────

@app.get("/debug/actions")
def debug_actions():
    """List all available healing actions."""
    return {
        "available_actions": [arm.action for arm in engine.bandit.arms],
        "total": len(engine.bandit.arms)
    }


@app.get("/debug/engine")
def debug_engine():
    """Engine state for debugging."""
    return {
        "round": engine.round,
        "last_decision": str(engine.last_decision) if engine.last_decision else None,
        "last_cooldown": engine.last_cooldown,
        "current_time": time.time()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT)
        engine._counter = 0
        return {"status": "reset", "message": "System reset to clean state"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))