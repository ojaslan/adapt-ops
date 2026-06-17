"""
Test suite for ADAPT-OPS core components.

Run with: python -m pytest tests/ -v
"""

import pytest
import numpy as np
from core.anomaly.detector import (
    PipelineMetrics, 
    PipelineAnomalyDetector, 
    AnomalyType,
    AnomalySeverity
)
from core.bandit.linucb import (
    AdaptOpsMAB,
    PipelineContext,
    ActionOutcome,
    HealingAction
)
from core.healer.orchestrator import AdaptOpsOrchestrator
import time


class TestAnomalyDetector:
    """Test anomaly detection."""

    def test_normal_metrics_no_anomaly(self):
        """Normal metrics should not trigger anomaly."""
        detector = PipelineAnomalyDetector()
        
        for _ in range(50):
            m = PipelineMetrics(
                timestamp=time.time(),
                build_duration_secs=180,
                test_pass_rate=0.95,
                failure_rate=0.05,
                queue_depth=2,
                cpu_utilization=0.5,
                memory_utilization=0.5,
                deploy_success_rate=0.95,
                flaky_test_count=0,
                retry_count=0
            )
            event = detector.analyze(m)
            assert event is None or event.severity.value < 2

    def test_failure_spike_detection(self):
        """High failure rate should trigger anomaly."""
        detector = PipelineAnomalyDetector()
        
        # Warmup with normal metrics
        for _ in range(30):
            m = PipelineMetrics(
                timestamp=time.time(),
                build_duration_secs=180,
                test_pass_rate=0.95,
                failure_rate=0.05,
                queue_depth=2,
                cpu_utilization=0.5,
                memory_utilization=0.5,
                deploy_success_rate=0.95,
                flaky_test_count=0,
                retry_count=0
            )
            detector.analyze(m)
        
        # Inject failure spike
        m = PipelineMetrics(
            timestamp=time.time(),
            build_duration_secs=180,
            test_pass_rate=0.3,
            failure_rate=0.75,
            queue_depth=2,
            cpu_utilization=0.5,
            memory_utilization=0.5,
            deploy_success_rate=0.1,
            flaky_test_count=2,
            retry_count=3
        )
        event = detector.analyze(m)
        
        assert event is not None
        assert event.anomaly_type == AnomalyType.BUILD_FAILURE_SPIKE
        assert event.severity == AnomalySeverity.CRITICAL

    def test_resource_exhaustion_detection(self):
        """High CPU/Memory should trigger anomaly."""
        detector = PipelineAnomalyDetector()
        
        # Warmup
        for _ in range(30):
            m = PipelineMetrics(
                timestamp=time.time(),
                build_duration_secs=180,
                test_pass_rate=0.95,
                failure_rate=0.05,
                queue_depth=2,
                cpu_utilization=0.5,
                memory_utilization=0.5,
                deploy_success_rate=0.95,
                flaky_test_count=0,
                retry_count=0
            )
            detector.analyze(m)
        
        # High resource usage
        m = PipelineMetrics(
            timestamp=time.time(),
            build_duration_secs=180,
            test_pass_rate=0.80,
            failure_rate=0.10,
            queue_depth=2,
            cpu_utilization=0.95,
            memory_utilization=0.92,
            deploy_success_rate=0.75,
            flaky_test_count=2,
            retry_count=1
        )
        event = detector.analyze(m)
        
        assert event is not None
        assert event.anomaly_type == AnomalyType.RESOURCE_EXHAUSTION
        assert event.severity.value >= 2


class TestLinUCB:
    """Test Contextual Multi-Armed Bandit."""

    def test_arm_ucb_score(self):
        """UCB score should increase with success."""
        from core.bandit.linucb import LinUCBArm
        
        arm = LinUCBArm(HealingAction.RETRY_FAILED_STEP)
        context = np.ones(16)
        
        # Initial UCB score
        score1 = arm.ucb_score(context)
        assert score1 > 0
        
        # After success
        arm.update(context, reward=0.8)
        score2 = arm.ucb_score(context)
        
        # Score should reflect the success
        assert arm.n_pulls == 1
        assert arm.total_reward == 0.8

    def test_mab_action_selection(self):
        """MAB should select actions."""
        mab = AdaptOpsMAB()
        context = PipelineContext(
            failure_rate_7d=0.5,
            avg_build_time_mins=0.5,
            flaky_test_ratio=0.5,
            queue_depth=0.5,
            hour_of_day=0.5,
            is_peak_hours=1.0,
            days_since_last_deploy=0.3,
            anomaly_score=0.7,
            anomaly_type_build=1.0,
            anomaly_type_test=0.0,
            anomaly_type_deploy=0.0,
            anomaly_type_resource=0.0,
            commit_frequency=0.5,
            team_size_bucket=0.33,
            branch_is_main=0.0
        )
        
        action = mab.select_action(context)
        assert isinstance(action, HealingAction)

    def test_mab_learning(self):
        """MAB should learn from outcomes."""
        mab = AdaptOpsMAB()
        context = PipelineContext(
            failure_rate_7d=0.5,
            avg_build_time_mins=0.5,
            flaky_test_ratio=0.5,
            queue_depth=0.5,
            hour_of_day=0.5,
            is_peak_hours=1.0,
            days_since_last_deploy=0.3,
            anomaly_score=0.7,
            anomaly_type_build=1.0,
            anomaly_type_test=0.0,
            anomaly_type_deploy=0.0,
            anomaly_type_resource=0.0,
            commit_frequency=0.5,
            team_size_bucket=0.33,
            branch_is_main=0.0
        )
        
        # Record some outcomes
        for _ in range(5):
            outcome = ActionOutcome(
                action=HealingAction.RETRY_FAILED_STEP,
                context=context,
                success=0.8,
                time_improvement=0.3,
                cost_efficiency=0.5
            )
            mab.record_outcome(outcome)
        
        # Retry should have high average reward now
        summary = mab.get_summary()
        retry_arm = next(
            a for a in summary["arms"] 
            if a["action"] == HealingAction.RETRY_FAILED_STEP.value
        )
        assert retry_arm["pulls"] == 5
        assert retry_arm["avg_reward"] > 0.5


class TestOrchestrator:
    """Test the main orchestrator."""

    def test_ingest_normal_metrics(self):
        """Normal metrics should not trigger healing."""
        engine = AdaptOpsOrchestrator(cooldown_secs=0)
        
        for _ in range(50):
            m = PipelineMetrics(
                timestamp=time.time(),
                build_duration_secs=180,
                test_pass_rate=0.95,
                failure_rate=0.05,
                queue_depth=2,
                cpu_utilization=0.5,
                memory_utilization=0.5,
                deploy_success_rate=0.95,
                flaky_test_count=0,
                retry_count=0
            )
            decision = engine.ingest(m)
            assert decision is None or not decision

    def test_ingest_anomaly(self):
        """Anomaly should trigger healing decision."""
        engine = AdaptOpsOrchestrator(cooldown_secs=0, min_severity=2)
        
        # Warmup
        for _ in range(40):
            m = PipelineMetrics(
                timestamp=time.time(),
                build_duration_secs=180,
                test_pass_rate=0.95,
                failure_rate=0.05,
                queue_depth=2,
                cpu_utilization=0.5,
                memory_utilization=0.5,
                deploy_success_rate=0.95,
                flaky_test_count=0,
                retry_count=0
            )
            engine.ingest(m)
        
        # Anomaly
        m = PipelineMetrics(
            timestamp=time.time(),
            build_duration_secs=180,
            test_pass_rate=0.3,
            failure_rate=0.75,
            queue_depth=2,
            cpu_utilization=0.5,
            memory_utilization=0.5,
            deploy_success_rate=0.1,
            flaky_test_count=2,
            retry_count=3
        )
        decision = engine.ingest(m)
        
        assert decision is not None
        assert decision.selected_action in HealingAction
        assert decision.outcome is not None

    def test_health_stats(self):
        """Health endpoint should return valid stats."""
        engine = AdaptOpsOrchestrator()
        
        health = engine.get_health()
        
        assert "metrics_processed" in health
        assert "anomalies_detected" in health
        assert "healings_triggered" in health
        assert "heal_success_rate" in health
        assert health["metrics_processed"] >= 0
        assert 0 <= health["heal_success_rate"] <= 1


@pytest.mark.integration
class TestIntegration:
    """Integration tests."""

    def test_full_workflow(self):
        """Test complete workflow: detect → decide → heal → learn."""
        engine = AdaptOpsOrchestrator(cooldown_secs=0)
        
        # Simulate 100 pipeline runs
        failures = 0
        healed = 0
        
        for i in range(100):
            if i < 40:
                # Normal
                m = PipelineMetrics(
                    timestamp=time.time(),
                    build_duration_secs=np.random.normal(180, 20),
                    test_pass_rate=np.random.uniform(0.92, 0.99),
                    failure_rate=np.random.uniform(0.02, 0.08),
                    queue_depth=int(np.random.uniform(0, 5)),
                    cpu_utilization=np.random.uniform(0.3, 0.6),
                    memory_utilization=np.random.uniform(0.4, 0.65),
                    deploy_success_rate=np.random.uniform(0.94, 0.99),
                    flaky_test_count=int(np.random.uniform(0, 2)),
                    retry_count=int(np.random.uniform(0, 1))
                )
            else:
                # 20% failures
                if np.random.random() < 0.2:
                    failures += 1
                    m = PipelineMetrics(
                        timestamp=time.time(),
                        build_duration_secs=np.random.normal(320, 40),
                        test_pass_rate=np.random.uniform(0.3, 0.6),
                        failure_rate=np.random.uniform(0.5, 0.85),
                        queue_depth=int(np.random.uniform(10, 25)),
                        cpu_utilization=np.random.uniform(0.7, 0.95),
                        memory_utilization=np.random.uniform(0.6, 0.85),
                        deploy_success_rate=np.random.uniform(0.1, 0.4),
                        flaky_test_count=int(np.random.uniform(5, 15)),
                        retry_count=int(np.random.uniform(3, 8))
                    )
                else:
                    m = PipelineMetrics(
                        timestamp=time.time(),
                        build_duration_secs=np.random.normal(180, 20),
                        test_pass_rate=np.random.uniform(0.92, 0.99),
                        failure_rate=np.random.uniform(0.02, 0.08),
                        queue_depth=int(np.random.uniform(0, 5)),
                        cpu_utilization=np.random.uniform(0.3, 0.6),
                        memory_utilization=np.random.uniform(0.4, 0.65),
                        deploy_success_rate=np.random.uniform(0.94, 0.99),
                        flaky_test_count=int(np.random.uniform(0, 2)),
                        retry_count=int(np.random.uniform(0, 1))
                    )
            
            decision = engine.ingest(m)
            if decision:
                healed += 1
        
        health = engine.get_health()
        
        # Verify statistics
        assert health["metrics_processed"] == 100
        assert health["anomalies_detected"] > 0
        assert health["healings_triggered"] > 0
        assert healed == health["healings_triggered"]
