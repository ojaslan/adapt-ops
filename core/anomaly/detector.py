import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
from enum import Enum
from collections import deque
import logging
import time

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    BUILD_FAILURE_SPIKE   = "build_failure_spike"
    BUILD_TIME_REGRESSION = "build_time_regression"
    TEST_FLAKINESS_SURGE  = "test_flakiness_surge"
    RESOURCE_EXHAUSTION   = "resource_exhaustion"
    QUEUE_OVERFLOW        = "queue_overflow"
    UNKNOWN               = "unknown"


class AnomalySeverity(Enum):
    LOW      = 1
    MEDIUM   = 2
    HIGH     = 3
    CRITICAL = 4


@dataclass
class PipelineMetrics:
    timestamp: float
    build_duration_secs: float
    test_pass_rate: float
    failure_rate: float
    queue_depth: int
    cpu_utilization: float
    memory_utilization: float
    deploy_success_rate: float
    flaky_test_count: int
    retry_count: int

    def to_vector(self) -> np.ndarray:
        return np.array([
            self.build_duration_secs,
            self.test_pass_rate,
            self.failure_rate,
            self.queue_depth,
            self.cpu_utilization,
            self.memory_utilization,
            self.deploy_success_rate,
            self.flaky_test_count,
            self.retry_count
        ], dtype=np.float64)


@dataclass
class AnomalyEvent:
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    score: float
    affected_metrics: List[str]
    raw_metrics: PipelineMetrics
    description: str
    recommended_urgency: str

    @property
    def should_trigger_healing(self) -> bool:
        return self.severity.value >= AnomalySeverity.MEDIUM.value

    def to_dict(self) -> Dict:
        return {
            "type": self.anomaly_type.value,
            "severity": self.severity.name,
            "score": round(self.score, 4),
            "affected_metrics": self.affected_metrics,
            "description": self.description,
            "urgency": self.recommended_urgency
        }


class ZScoreDetector:
    def __init__(self, window: int = 30):
        self.window = window
        self.history: deque = deque(maxlen=window)

    def update(self, value: float) -> float:
        self.history.append(value)
        if len(self.history) < 5:
            return 0.0
        arr = np.array(self.history)
        mean, std = arr.mean(), arr.std()
        if std < 1e-6:
            return 0.0
        return float(abs(value - mean) / std)


class AnomalyDetector:
    def __init__(self):
        self.zscore = {
            "build_duration": ZScoreDetector(window=30),
            "failure_rate":   ZScoreDetector(window=30),
            "flaky_tests":    ZScoreDetector(window=30),
            "queue_depth":    ZScoreDetector(window=20),
            "cpu":            ZScoreDetector(window=20),
        }
        self.history: deque = deque(maxlen=500)
        self.event_history: List[AnomalyEvent] = []

    def analyze(self, metrics: PipelineMetrics) -> Optional[AnomalyEvent]:
        self.history.append(metrics)

        z_build = self.zscore["build_duration"].update(metrics.build_duration_secs)
        z_fail  = self.zscore["failure_rate"].update(metrics.failure_rate)
        z_flaky = self.zscore["flaky_tests"].update(metrics.flaky_test_count)
        z_queue = self.zscore["queue_depth"].update(metrics.queue_depth)
        z_cpu   = self.zscore["cpu"].update(metrics.cpu_utilization)

        anomaly_type, severity, affected, description = self._classify(
            metrics, z_build, z_fail, z_flaky, z_queue, z_cpu
        )

        max_z = max(z_build, z_fail, z_flaky, z_queue, z_cpu)
        score = float(np.clip(max_z / 4.0, 0, 1))

        if anomaly_type == AnomalyType.UNKNOWN and score < 0.45:
            return None

        urgency = "immediate" if severity.value >= 3 else "next_run"
        event = AnomalyEvent(
            anomaly_type=anomaly_type,
            severity=severity,
            score=score,
            affected_metrics=affected,
            raw_metrics=metrics,
            description=description,
            recommended_urgency=urgency
        )

        self.event_history.append(event)
        logger.warning(f"ANOMALY: {anomaly_type.value} | {severity.name} | score={score:.3f}")
        return event

    def _classify(
        self, m: PipelineMetrics,
        z_build, z_fail, z_flaky, z_queue, z_cpu
    ) -> Tuple[AnomalyType, AnomalySeverity, List[str], str]:

        if m.failure_rate > 0.4 or z_fail > 2.5:
            sev = AnomalySeverity.CRITICAL if m.failure_rate > 0.7 else AnomalySeverity.HIGH
            return (AnomalyType.BUILD_FAILURE_SPIKE, sev,
                    ["failure_rate"], f"Failure rate {m.failure_rate:.1%}")

        if z_build > 3.0:
            sev = AnomalySeverity.HIGH if z_build > 4.0 else AnomalySeverity.MEDIUM
            return (AnomalyType.BUILD_TIME_REGRESSION, sev,
                    ["build_duration_secs"], f"Build time spike (z={z_build:.1f})")

        if m.flaky_test_count > 5 or z_flaky > 2.5:
            return (AnomalyType.TEST_FLAKINESS_SURGE, AnomalySeverity.MEDIUM,
                    ["flaky_test_count"], f"{m.flaky_test_count} flaky tests")

        if m.cpu_utilization > 0.9 or m.memory_utilization > 0.85:
            return (AnomalyType.RESOURCE_EXHAUSTION, AnomalySeverity.HIGH,
                    ["cpu_utilization", "memory_utilization"],
                    f"CPU={m.cpu_utilization:.0%} MEM={m.memory_utilization:.0%}")

        if m.queue_depth > 20 or z_queue > 2.5:
            return (AnomalyType.QUEUE_OVERFLOW, AnomalySeverity.MEDIUM,
                    ["queue_depth"], f"Queue depth {m.queue_depth}")

        return (AnomalyType.UNKNOWN, AnomalySeverity.LOW, [], "No clear classification")

    def get_recent_events(self, n: int = 10) -> List[Dict]:
        return [
            {
                "type": e.anomaly_type.value,
                "severity": e.severity.name,
                "score": round(e.score, 3),
                "description": e.description,
                "urgency": e.recommended_urgency
            }
            for e in self.event_history[-n:]
        ]