import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class HealingAction(Enum):
    RETRY_FAILED_STEP     = "retry_failed_step"
    SCALE_RESOURCES       = "scale_resources"
    PRUNE_FLAKY_TESTS     = "prune_flaky_tests"
    ROLLBACK_DEPLOYMENT   = "rollback_deployment"
    PARALLELIZE_JOBS      = "parallelize_jobs"
    CACHE_DEPENDENCIES    = "cache_dependencies"
    SKIP_REDUNDANT_CHECKS = "skip_redundant_checks"


@dataclass
class PipelineContext:
    failure_rate_7d: float
    avg_build_time_mins: float
    flaky_test_ratio: float
    queue_depth: float
    hour_of_day: float
    is_peak_hours: float
    days_since_last_deploy: float
    anomaly_score: float
    anomaly_type_build: float
    anomaly_type_test: float
    anomaly_type_deploy: float
    anomaly_type_resource: float
    commit_frequency: float
    team_size_bucket: float
    branch_is_main: float

    def to_vector(self) -> np.ndarray:
        return np.array([
            1.0,
            self.failure_rate_7d,
            self.avg_build_time_mins,
            self.flaky_test_ratio,
            self.queue_depth,
            self.hour_of_day,
            self.is_peak_hours,
            self.days_since_last_deploy,
            self.anomaly_score,
            self.anomaly_type_build,
            self.anomaly_type_test,
            self.anomaly_type_deploy,
            self.anomaly_type_resource,
            self.commit_frequency,
            self.team_size_bucket,
            self.branch_is_main,
        ], dtype=np.float64)


@dataclass
class ActionOutcome:
    action: HealingAction
    context: PipelineContext
    success: float
    time_improvement: float
    cost_efficiency: float

    @property
    def reward(self) -> float:
        return (
            0.60 * self.success +
            0.25 * self.time_improvement +
            0.15 * self.cost_efficiency
        )


class LinUCBArm:
    def __init__(self, action: HealingAction, context_dim: int = 16, alpha: float = 1.0):
        self.action = action
        self.d = context_dim
        self.alpha = alpha
        self.A = np.eye(self.d, dtype=np.float64)
        self.b = np.zeros(self.d, dtype=np.float64)
        self.n_pulls = 0
        self.total_reward = 0.0

    def ucb_score(self, x: np.ndarray) -> float:
        A_inv = np.linalg.inv(self.A)
        theta = A_inv @ self.b
        exploit = theta @ x
        explore = self.alpha * np.sqrt(x @ A_inv @ x)
        return exploit + explore

    def update(self, x: np.ndarray, reward: float):
        self.A += np.outer(x, x)
        self.b += reward * x
        self.n_pulls += 1
        self.total_reward += reward

    def avg_reward(self) -> float:
        return self.total_reward / max(1, self.n_pulls)

    def to_dict(self) -> Dict:
        return {
            "action": self.action.value,
            "A": self.A.tolist(),
            "b": self.b.tolist(),
            "n_pulls": self.n_pulls,
            "total_reward": self.total_reward,
            "alpha": self.alpha
        }

    @classmethod
    def from_dict(cls, data: Dict, context_dim: int) -> "LinUCBArm":
        arm = cls(HealingAction(data["action"]), context_dim, data["alpha"])
        arm.A = np.array(data["A"])
        arm.b = np.array(data["b"])
        arm.n_pulls = data["n_pulls"]
        arm.total_reward = data["total_reward"]
        return arm


class AdaptOpsMAB:
    def __init__(self, alpha: float = 1.0, context_dim: int = 16):
        self.alpha = alpha
        self.context_dim = context_dim
        self.arms: Dict[HealingAction, LinUCBArm] = {
            action: LinUCBArm(action, context_dim, alpha)
            for action in HealingAction
        }
        self.decision_count = 0

    def select_action(self, context: PipelineContext) -> HealingAction:
        x = context.to_vector()
        best = max(self.arms.items(), key=lambda item: item[1].ucb_score(x))
        self.decision_count += 1
        logger.info(f"Selected: {best[0].value}")
        return best[0]

    def record_outcome(self, outcome: ActionOutcome):
        x = outcome.context.to_vector()
        self.arms[outcome.action].update(x, outcome.reward)
        logger.info(f"Updated: {outcome.action.value} | reward={outcome.reward:.3f}")

    def get_rankings(self, context: PipelineContext) -> List[Dict]:
        x = context.to_vector()
        rankings = [
            {
                "action": action.value,
                "ucb_score": round(float(arm.ucb_score(x)), 4),
                "avg_reward": round(arm.avg_reward(), 4),
                "pulls": arm.n_pulls
            }
            for action, arm in self.arms.items()
        ]
        return sorted(rankings, key=lambda r: r["ucb_score"], reverse=True)

    def get_summary(self) -> Dict:
        return {
            "total_decisions": self.decision_count,
            "arms": [
                {
                    "action": a.value,
                    "pulls": arm.n_pulls,
                    "avg_reward": round(arm.avg_reward(), 4)
                }
                for a, arm in self.arms.items()
            ]
        }

    def save(self, path: str):
        state = {
            "alpha": self.alpha,
            "context_dim": self.context_dim,
            "arms": {
                a.value: arm.to_dict()
                for a, arm in self.arms.items()
            },
            "decision_count": self.decision_count
        }
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
        logger.info(f"Saved to {path}")

    @classmethod
    def load(cls, path: str) -> "AdaptOpsMAB":
        with open(path) as f:
            state = json.load(f)
        mab = cls(alpha=state["alpha"], context_dim=state["context_dim"])
        mab.decision_count = state["decision_count"]
        for action_val, arm_data in state["arms"].items():
            action = HealingAction(action_val)
            mab.arms[action] = LinUCBArm.from_dict(arm_data, state["context_dim"])
        logger.info(f"Loaded from {path}")
        return mab