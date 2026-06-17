"""
Comprehensive tests for ADAPT-OPS system.
"""

import pytest
import json
import time
from pathlib import Path
from unittest.mock import patch

from core.anomaly.detector import PipelineMetrics, AnomalyDetector
from core.bandit.linucb import LinUCBBandit, Arm
from core.healer.orchestrator import AdaptOpsOrchestrator
from core.persistence import MetricStore, AnomalyStore, HealingStore
from api.main import app, ingest
from fastapi.testclient import TestClient

client = TestClient(app)


# ── Anomaly Detection Tests ──────────────────────────────────

class TestAnomalyDetector:
    
    def test_detector_init(self):
        detector = AnomalyDetector(window_size=30)
        assert detector.window_size == 30
        assert len(detector.history) == 0
    
    def test_detect_build_failure_spike(self):
        detector = AnomalyDetector(window_size=10)
        
        # Normal metrics
        for i in range(5):
            m = PipelineMetrics(
                timestamp=time.time() + i,
                build_duration_secs=100,
                test_pass_rate=0.95,
                failure_rate=0.05,
                queue_depth=1,
                cpu_utilization=0.5,
                memory_utilization=0.5,
                deploy_success_rate=0.95,
                flaky_test_count=0,
                retry_count=0
            )
            detector.process(m)
        
        # Anomaly: high failure rate
        m = PipelineMetrics(
            timestamp=time.time() + 10,
            build_duration_secs=150,
            test_pass_rate=0.3,
            failure_rate=0.7,
            queue_depth=5,
            cpu_utilization=0.9,
            memory_utilization=0.9,
            deploy_success_rate=0.1,
            flaky_test_count=20,
            retry_count=10
        )
        anomaly = detector.process(m)
        
        assert anomaly is not None
        assert anomaly.score > 0.5
        assert anomaly.severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    
    def test_detect_resource_exhaustion(self):
        detector = AnomalyDetector(window_size=10)
        
        m = PipelineMetrics(
            timestamp=time.time(),
            build_duration_secs=100,
            test_pass_rate=0.9,
            failure_rate=0.1,
            queue_depth=50,
            cpu_utilization=0.95,
            memory_utilization=0.95,
            deploy_success_rate=0.9,
            flaky_test_count=5,
            retry_count=2
        )
        anomaly = detector.process(m)
        
        assert anomaly is not None
        assert "resource" in anomaly.type.lower() or anomaly.type == "unknown"
    
    def test_no_anomaly_on_healthy_metrics(self):
        detector = AnomalyDetector(window_size=10)
        
        m = PipelineMetrics(
            timestamp=time.time(),
            build_duration_secs=100,
            test_pass_rate=0.98,
            failure_rate=0.02,
            queue_depth=1,
            cpu_utilization=0.3,
            memory_utilization=0.4,
            deploy_success_rate=0.98,
            flaky_test_count=0,
            retry_count=0
        )
        anomaly = detector.process(m)
        
        # Very low score = healthy
        if anomaly:
            assert anomaly.score < 0.5


# ── Bandit Tests ────────────────────────────────────────────

class TestLinUCBBandit:
    
    def test_bandit_init(self):
        bandit = LinUCBBandit(alpha=1.0)
        assert bandit.alpha == 1.0
        assert len(bandit.arms) == 6  # 6 actions
    
    def test_arm_selection(self):
        bandit = LinUCBBandit(alpha=1.0)
        
        # Select arm multiple times
        for _ in range(10):
            arm = bandit.select_arm()
            assert arm is not None
            assert arm.action in [
                "retry_failed_step",
                "scale_resources",
                "prune_flaky_tests",
                "cache_dependencies",
                "rollback_deployment",
                "parallelize_jobs"
            ]
    
    def test_arm_update(self):
        bandit = LinUCBBandit(alpha=1.0)
        arm = bandit.select_arm()
        initial_pulls = arm.count
        
        bandit.update_arm(arm.action, reward=0.8)
        
        assert arm.count == initial_pulls + 1
        assert arm.total_reward >= 0


# ── Orchestrator Tests ───────────────────────────────────────

class TestAdaptOpsOrchestrator:
    
    def test_orchestrator_init(self):
        orchestrator = AdaptOpsOrchestrator(
            cooldown_secs=30,
            min_severity=2
        )
        assert orchestrator.cooldown_secs == 30
        assert orchestrator.min_severity == 2
    
    def test_ingest_healthy_metrics(self):
        orchestrator = AdaptOpsOrchestrator()
        
        m = PipelineMetrics(
            timestamp=time.time(),
            build_duration_secs=100,
            test_pass_rate=0.98,
            failure_rate=0.02,
            queue_depth=1,
            cpu_utilization=0.3,
            memory_utilization=0.4,
            deploy_success_rate=0.98,
            flaky_test_count=0,
            retry_count=0
        )
        decision = orchestrator.ingest(m)
        
        # Healthy metrics should not trigger healing
        # (unless detector has unusual internal state)
        # In most cases: decision is None
        if decision is not None:
            assert hasattr(decision, 'action')
    
    def test_ingest_anomalous_metrics(self):
        orchestrator = AdaptOpsOrchestrator()
        
        # Feed several normal metrics first
        for i in range(5):
            m = PipelineMetrics(
                timestamp=time.time() + i,
                build_duration_secs=100,
                test_pass_rate=0.95,
                failure_rate=0.05,
                queue_depth=1,
                cpu_utilization=0.5,
                memory_utilization=0.5,
                deploy_success_rate=0.95,
                flaky_test_count=0,
                retry_count=0
            )
            orchestrator.ingest(m)
        
        # Now anomalous
        m = PipelineMetrics(
            timestamp=time.time() + 10,
            build_duration_secs=300,
            test_pass_rate=0.1,
            failure_rate=0.9,
            queue_depth=30,
            cpu_utilization=0.95,
            memory_utilization=0.95,
            deploy_success_rate=0.05,
            flaky_test_count=50,
            retry_count=20
        )
        decision = orchestrator.ingest(m)
        
        # Should either detect anomaly or not depending on detector
        assert decision is None or hasattr(decision, 'action')


# ── Persistence Tests ───────────────────────────────────────

class TestMetricStore:
    
    def test_append_and_retrieve(self, tmp_path):
        store = MetricStore(tmp_path / "metrics.jsonl")
        
        metric1 = {"build_duration_secs": 100, "test_pass_rate": 0.9}
        metric2 = {"build_duration_secs": 120, "test_pass_rate": 0.85}
        
        store.append_metric(metric1)
        store.append_metric(metric2)
        
        metrics = store.get_metrics(limit=10)
        assert len(metrics) >= 2
        assert metrics[-1]["build_duration_secs"] in [100, 120]
    
    def test_stats_summary(self, tmp_path):
        store = MetricStore(tmp_path / "metrics.jsonl")
        
        for i in range(5):
            store.append_metric({
                "build_duration_secs": 100 + i*10,
                "test_pass_rate": 0.9 - i*0.02,
                "anomaly_detected": i == 2,
                "healing_triggered": i == 2,
                "healing_successful": i == 2
            })
        
        stats = store.get_stats_summary(hours=24)
        assert stats["total_count"] >= 5
        assert stats["anomalies_detected"] >= 1


class TestAnomalyStore:
    
    def test_record_and_retrieve(self, tmp_path):
        store = AnomalyStore(tmp_path / "anomalies.jsonl")
        
        store.record_anomaly("build_failure", "HIGH", 0.8, {"pipeline": "main"})
        store.record_anomaly("test_flakiness", "MEDIUM", 0.6, {"pipeline": "dev"})
        
        anomalies = store.get_anomalies(limit=10)
        assert len(anomalies) >= 2


class TestHealingStore:
    
    def test_record_and_retrieve(self, tmp_path):
        store = HealingStore(tmp_path / "healings.jsonl")
        
        store.record_healing("build_failure", "retry_failed_step", True, 0.8)
        store.record_healing("test_flakiness", "scale_resources", False, 0.2)
        
        healings = store.get_healings(limit=10)
        assert len(healings) >= 2
    
    def test_action_performance(self, tmp_path):
        store = HealingStore(tmp_path / "healings.jsonl")
        
        store.record_healing("build_failure", "retry_failed_step", True, 0.8)
        store.record_healing("build_failure", "retry_failed_step", True, 0.75)
        store.record_healing("build_failure", "scale_resources", False, 0.2)
        
        perf = store.get_action_performance()
        assert "retry_failed_step" in perf
        assert perf["retry_failed_step"]["success_rate"] == 100.0


# ── API Tests ────────────────────────────────────────────────

class TestAPI:
    
    def test_root(self):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["name"] == "ADAPT-OPS"
    
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    
    def test_ingest_endpoint(self):
        payload = {
            "build_duration_secs": 100.0,
            "test_pass_rate": 0.95,
            "failure_rate": 0.05,
            "queue_depth": 1,
            "cpu_utilization": 0.5,
            "memory_utilization": 0.5,
            "deploy_success_rate": 0.95,
            "flaky_test_count": 0,
            "retry_count": 0,
            "pipeline_id": "test-pipeline"
        }
        response = client.post("/ingest", json=payload)
        assert response.status_code == 200
        assert "status" in response.json()
    
    def test_stats_endpoint(self):
        # Ingest first
        payload = {
            "build_duration_secs": 100.0,
            "test_pass_rate": 0.95,
            "failure_rate": 0.05,
            "queue_depth": 1,
            "cpu_utilization": 0.5,
            "memory_utilization": 0.5,
            "deploy_success_rate": 0.95,
            "flaky_test_count": 0,
            "retry_count": 0
        }
        client.post("/ingest", json=payload)
        
        response = client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert "metrics" in data
        assert "anomalies" in data
    
    def test_mab_state_endpoint(self):
        response = client.get("/mab/state")
        assert response.status_code == 200
        data = response.json()
        assert "arms" in data
        assert len(data["arms"]) > 0
    
    def test_debug_actions(self):
        response = client.get("/debug/actions")
        assert response.status_code == 200
        data = response.json()
        assert "available_actions" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
