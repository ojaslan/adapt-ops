import random
import time
import numpy as np
from core.anomaly.detector import PipelineMetrics
from core.healer.orchestrator import AdaptOpsOrchestrator


def normal_metrics():
    return PipelineMetrics(
        timestamp=time.time(),
        build_duration_secs=random.gauss(180, 20),
        test_pass_rate=random.uniform(0.92, 0.99),
        failure_rate=random.uniform(0.02, 0.08),
        queue_depth=random.randint(0, 5),
        cpu_utilization=random.uniform(0.3, 0.6),
        memory_utilization=random.uniform(0.4, 0.65),
        deploy_success_rate=random.uniform(0.94, 0.99),
        flaky_test_count=random.randint(0, 2),
        retry_count=random.randint(0, 1)
    )


def failure_spike():
    return PipelineMetrics(
        timestamp=time.time(),
        build_duration_secs=random.gauss(320, 40),
        test_pass_rate=random.uniform(0.3, 0.6),
        failure_rate=random.uniform(0.5, 0.85),
        queue_depth=random.randint(10, 25),
        cpu_utilization=random.uniform(0.7, 0.95),
        memory_utilization=random.uniform(0.6, 0.85),
        deploy_success_rate=random.uniform(0.1, 0.4),
        flaky_test_count=random.randint(5, 15),
        retry_count=random.randint(3, 8)
    )


def resource_exhaustion():
    return PipelineMetrics(
        timestamp=time.time(),
        build_duration_secs=random.gauss(450, 60),
        test_pass_rate=random.uniform(0.7, 0.85),
        failure_rate=random.uniform(0.15, 0.35),
        queue_depth=random.randint(15, 30),
        cpu_utilization=random.uniform(0.88, 0.98),
        memory_utilization=random.uniform(0.85, 0.97),
        deploy_success_rate=random.uniform(0.5, 0.7),
        flaky_test_count=random.randint(2, 6),
        retry_count=random.randint(1, 4)
    )


def flaky_surge():
    return PipelineMetrics(
        timestamp=time.time(),
        build_duration_secs=random.gauss(220, 30),
        test_pass_rate=random.uniform(0.5, 0.72),
        failure_rate=random.uniform(0.1, 0.25),
        queue_depth=random.randint(3, 10),
        cpu_utilization=random.uniform(0.4, 0.65),
        memory_utilization=random.uniform(0.45, 0.7),
        deploy_success_rate=random.uniform(0.6, 0.8),
        flaky_test_count=random.randint(8, 20),
        retry_count=random.randint(2, 6)
    )


def run(rounds=200):
    print("=" * 60)
    print("  ADAPT-OPS — Self-Healing Pipeline Simulator")
    print("=" * 60)

    engine = AdaptOpsOrchestrator(cooldown_secs=0.0, min_severity=2)

    scenarios = [
        ("NORMAL",    normal_metrics,     0.65),
        ("FAILURE",   failure_spike,      0.12),
        ("RESOURCE",  resource_exhaustion, 0.12),
        ("FLAKY",     flaky_surge,        0.11),
    ]

    for i in range(rounds):
        names, funcs, weights = zip(*scenarios)

        # Warmup: first 40 rounds normal only
        if i < 40:
            m = normal_metrics()
        else:
            func = random.choices(funcs, weights=weights)[0]
            m = func()

        decision = engine.ingest(m)

        if decision and i >= 40:
            icon = "✓" if decision.outcome and decision.outcome.success > 0.5 else "✗"
            print(
                f"  [{i:3d}] {icon}  "
                f"{decision.anomaly.anomaly_type.value:<28}"
                f"→  {decision.selected_action.value:<30}"
                f"reward={decision.outcome.reward:.3f}"
            )

    # Final summary
    health = engine.get_health()
    mab    = health["mab_summary"]

    print()
    print("=" * 60)
    print("  RESULTS — WHAT THE SYSTEM LEARNED:")
    print("=" * 60)
    print(f"  Metrics processed  : {health['metrics_processed']}")
    print(f"  Anomalies detected : {health['anomalies_detected']}")
    print(f"  Healings triggered : {health['healings_triggered']}")
    print(f"  Success rate       : {health['heal_success_rate']:.1%}")
    print()
    print("  ACTION RANKINGS (best → worst):")
    print()

    arms = sorted(mab["arms"], key=lambda x: x["avg_reward"], reverse=True)
    for rank, arm in enumerate(arms, 1):
        bar = "█" * int(arm["avg_reward"] * 20)
        print(f"  {rank}. {arm['action']:<30} avg={arm['avg_reward']:.3f}  {bar}")

    print()
    print("=" * 60)


if __name__ == "__main__":
    run(rounds=200)