import time
import logging
import uuid
import numpy as np
from dataclasses import dataclass
from typing import Optional, List, Dict
from enum import Enum

from core.bandit.linucb import AdaptOpsMAB, PipelineContext, ActionOutcome, HealingAction
from core.anomaly.detector import PipelineAnomalyDetector, PipelineMetrics, AnomalyEvent
import config

logger = logging.getLogger(__name__)


class HealingStatus(Enum):
    PENDING   = "pending"
    EXECUTING = "executing"
    SUCCESS   = "success"
    FAILED    = "failed"


@dataclass
class HealingDecision:
    decision_id: str
    anomaly: AnomalyEvent
    context: PipelineContext
    selected_action: HealingAction
    status: HealingStatus = HealingStatus.PENDING
    outcome: Optional[ActionOutcome] = None
    notes: str = ""

    def to_dict(self) -> Dict:
        return {
            "decision_id": self.decision_id,
            "anomaly_type": self.anomaly.anomaly_type.value,
            "severity": self.anomaly.severity.name,
            "action": self.selected_action.value,
            "status": self.status.value,
            "reward": round(self.outcome.reward, 3) if self.outcome else None,
            "notes": self.notes
        }


def simulate_executor(action: HealingAction, context: PipelineContext) -> ActionOutcome:
    """
    Simulated executor — replace this later with real GitHub Actions API calls.
    """
    import numpy as np

    base_success = {
        HealingAction.RETRY_FAILED_STEP:     0.72,
        HealingAction.SCALE_RESOURCES:       0.65,
        HealingAction.PRUNE_FLAKY_TESTS:     0.80,
        HealingAction.ROLLBACK_DEPLOYMENT:   0.90,
        HealingAction.PARALLELIZE_JOBS:      0.60,
        HealingAction.CACHE_DEPENDENCIES:    0.75,
        HealingAction.SKIP_REDUNDANT_CHECKS: 0.55,
    }.get(action, 0.5)

    prob = float(np.clip(base_success - 0.15 * context.failure_rate_7d, 0.1, 0.95))
    success = float(np.random.random() < prob)
    time_improvement = float(np.clip(np.random.normal(0.3, 0.15), 0, 0.8)) * success
    cost_efficiency  = float(np.clip(np.random.normal(0.5, 0.2), 0.1, 0.9))

    return ActionOutcome(
        action=action,
        context=context,
        success=success,
        time_improvement=time_improvement,
        cost_efficiency=cost_efficiency
    )


class AdaptOpsOrchestrator:
    def __init__(
        self,
        cooldown_secs: float = 60.0,
        min_severity: int = 2,
        mab_state_file: Optional[str] = None
    ):
        self.mab = AdaptOpsMAB(alpha=config.MAB_ALPHA, context_dim=config.MAB_CONTEXT_DIM)
        self.detector = PipelineAnomalyDetector()
        self.cooldown_secs = cooldown_secs
        self.min_severity = min_severity
        self.mab_state_file = mab_state_file or str(config.MAB_STATE_FILE)

        self.decision_log: List[HealingDecision] = []
        self.last_heal_time: float = 0.0
        self._counter: int = 0
        self._start_time: float = time.time()

        self.metrics_processed = 0
        self.anomalies_detected = 0
        self.healings_triggered = 0
        self.successful_healings = 0

        # Load MAB state if available
        if config.ENABLE_MAB_PERSISTENCE:
            self._load_mab_state()

        logger.info("AdaptOpsOrchestrator ready.")

    def ingest(self, metrics: PipelineMetrics) -> Optional[HealingDecision]:
        self.metrics_processed += 1

        event = self.detector.analyze(metrics)
        if event is None:
            return None

        self.anomalies_detected += 1

        if event.severity.value < self.min_severity:
            return None

        if time.time() - self.last_heal_time < self.cooldown_secs:
            logger.info("Cooldown active — skipping heal")
            return None

        context = self._build_context(metrics, event)
        action  = self.mab.select_action(context)

        self._counter += 1
        decision = HealingDecision(
            decision_id=f"heal_{self._counter:05d}",
            anomaly=event,
            context=context,
            selected_action=action,
            status=HealingStatus.EXECUTING
        )

        self.healings_triggered += 1
        self.last_heal_time = time.time()

        try:
            outcome = simulate_executor(action, context)
            decision.outcome = outcome
            decision.status = HealingStatus.SUCCESS if outcome.success > 0.5 else HealingStatus.FAILED
            decision.notes  = f"reward={outcome.reward:.3f}"

            if outcome.success > 0.5:
                self.successful_healings += 1

            self.mab.record_outcome(outcome)

        except Exception as e:
            decision.status = HealingStatus.FAILED
            decision.notes  = f"Error: {e}"
            logger.error(f"Execution failed: {e}")

        self.decision_log.append(decision)
        logger.info(f"{decision.decision_id} | {action.value} | {decision.status.value}")
        return decision

    def _build_context(self, m: PipelineMetrics, event: AnomalyEvent) -> PipelineContext:
        import time as t
        hour = t.localtime().tm_hour / 23.0
        peak = float(9 <= t.localtime().tm_hour <= 18)

        # Calculate 7-day failure rate from history
        failure_rate_7d = float(m.failure_rate)
        if len(self.detector.history) > 50:
            recent = list(self.detector.history)[-50:]
            failure_rate_7d = float(np.mean([x.failure_rate for x in recent]))

        return PipelineContext(
            failure_rate_7d        = float(np.clip(failure_rate_7d, 0, 1)),
            avg_build_time_mins    = float(np.clip(m.build_duration_secs / 600.0, 0, 1)),
            flaky_test_ratio       = float(np.clip(m.flaky_test_count / 20.0, 0, 1)),
            queue_depth            = float(np.clip(m.queue_depth / 30.0, 0, 1)),
            hour_of_day            = hour,
            is_peak_hours          = peak,
            days_since_last_deploy = 0.3,
            anomaly_score          = event.score,
            anomaly_type_build     = float(event.anomaly_type.value == "build_failure_spike"),
            anomaly_type_test      = float(event.anomaly_type.value == "test_flakiness_surge"),
            anomaly_type_deploy    = float(event.anomaly_type.value == "build_time_regression"),
            anomaly_type_resource  = float(event.anomaly_type.value == "resource_exhaustion"),
            commit_frequency       = 0.5,
            team_size_bucket       = 0.33,
            branch_is_main         = 0.0
        )

    def get_health(self) -> Dict:
        rate = self.successful_healings / max(1, self.healings_triggered)
        uptime_secs = time.time() - self._start_time
        return {
            "metrics_processed": self.metrics_processed,
            "anomalies_detected": self.anomalies_detected,
            "healings_triggered": self.healings_triggered,
            "successful_healings": self.successful_healings,
            "heal_success_rate": round(rate, 3),
            "uptime_secs": int(uptime_secs),
            "recent_decisions": [d.to_dict() for d in self.decision_log[-5:]],
            "mab_summary": self.mab.get_summary()
        }

    def _save_mab_state(self):
        """Persist MAB state to disk."""
        try:
            self.mab.save(self.mab_state_file)
            logger.info(f"MAB state saved to {self.mab_state_file}")
        except Exception as e:
            logger.error(f"Failed to save MAB state: {e}")

    def _load_mab_state(self):
        """Load MAB state from disk if exists."""
        try:
            import os
            if os.path.exists(self.mab_state_file):
                self.mab = AdaptOpsMAB.load(self.mab_state_file)
                logger.info(f"MAB state loaded from {self.mab_state_file}")
        except Exception as e:
            logger.warning(f"Failed to load MAB state: {e} — starting fresh")

    def shutdown(self):
        """Graceful shutdown."""
        if config.ENABLE_MAB_PERSISTENCE:
            self._save_mab_state()
        logger.info("AdaptOpsOrchestrator shut down gracefully")