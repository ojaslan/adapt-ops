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


def slow_builds():
    """Build time regression scenario."""
    return PipelineMetrics(
        timestamp=time.time(),
        build_duration_secs=random.gauss(500, 80),
        test_pass_rate=random.uniform(0.75, 0.90),
        failure_rate=random.uniform(0.05, 0.15),
        queue_depth=random.randint(8, 15),
        cpu_utilization=random.uniform(0.60, 0.80),
        memory_utilization=random.uniform(0.55, 0.75),
        deploy_success_rate=random.uniform(0.70, 0.85),
        flaky_test_count=random.randint(1, 3),
        retry_count=random.randint(0, 2)
    )


def run(rounds=250):
    print("=" * 70)
    print("  ADAPT-OPS — Self-Healing Pipeline Simulator")
    print("=" * 70)

    engine = AdaptOpsOrchestrator(cooldown_secs=0.0, min_severity=2)

    scenarios = [
        ("NORMAL",    normal_metrics,     0.60),
        ("FAILURE",   failure_spike,      0.12),
        ("RESOURCE",  resource_exhaustion, 0.10),
        ("FLAKY",     flaky_surge,        0.10),
        ("SLOW",      slow_builds,        0.08),
    ]

    decision_count = 0
    success_count = 0

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
            decision_count += 1
            is_success = decision.outcome and decision.outcome.success > 0.5
            if is_success:
                success_count += 1
            
            icon = "✓" if is_success else "✗"
            reward = decision.outcome.reward if decision.outcome else 0
            print(
                f"  [{i:3d}] {icon}  "
                f"{decision.anomaly.anomaly_type.value:<28} "
                f"→  {decision.selected_action.value:<25} "
                f"reward={reward:.3f}"
            )

    # Final summary
    health = engine.get_health()
    mab    = health["mab_summary"]

    print()
    print("=" * 70)
    print("  RESULTS — WHAT THE SYSTEM LEARNED:")
    print("=" * 70)
    print(f"  Total rounds          : {rounds}")
    print(f"  Metrics processed     : {health['metrics_processed']}")
    print(f"  Anomalies detected    : {health['anomalies_detected']}")
    print(f"  Healings triggered    : {health['healings_triggered']}")
    print(f"  Successful healings   : {health['successful_healings']}")
    print(f"  Overall success rate  : {health['heal_success_rate']:.1%}")
    print(f"  Uptime                : {health['uptime_secs']}s")
    print()
    print("  TOP PERFORMING ACTIONS (by avg reward):")
    print()

    arms = sorted(mab["arms"], key=lambda x: x["avg_reward"], reverse=True)
    for rank, arm in enumerate(arms, 1):
        bar = "█" * int(arm["avg_reward"] * 25)
        print(f"  {rank}. {arm['action']:<30} avg={arm['avg_reward']:.3f}  pulls={arm['pulls']:<4}  {bar}")

    print()
    print("=" * 70)
    print(f"  ✓ Simulation complete. MAB learned from {decision_count} decisions.")
    print("=" * 70)


if __name__ == "__main__":
    run(rounds=250)