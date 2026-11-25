from __future__ import annotations

from backend.warmlambda.core.config import SimConfig
from backend.warmlambda.core.metrics import compute_burst_metrics
from backend.warmlambda.core.simulator import (
    IntervalRecord,
    RequestRecord,
    SimResult,
)


def test_burst_metrics_detect_cold_starts_slo_and_readiness() -> None:
    cfg = SimConfig(duration_s=40, decision_interval_s=10, mean_exec_s=0.2)
    result = SimResult(
        requests=[
            RequestRecord(0, 15, 16, 16.6, True, False, 1.6),
            RequestRecord(1, 16, 16, 16.1, False, False, 0.1),
        ],
        intervals=[
            IntervalRecord(t=0, target=0, ready=0, busy=0, initializing=0,
                           queue_length=0, arrivals_in_window=0,
                           t_start=0, t_end=10, observed_requests=0),
            IntervalRecord(t=10, target=2, ready=1, busy=0, initializing=0,
                           queue_length=0, arrivals_in_window=2,
                           t_start=10, t_end=20, observed_requests=51,
                           cold_starts=1),
            IntervalRecord(t=20, target=0, ready=0, busy=0, initializing=0,
                           queue_length=0, arrivals_in_window=0,
                           t_start=20, t_end=30, observed_requests=0),
            IntervalRecord(t=30, target=0, ready=0, busy=0, initializing=0,
                           queue_length=0, arrivals_in_window=0,
                           t_start=30, t_end=40, observed_requests=0),
        ],
    )
    metrics = compute_burst_metrics(result, cfg)
    assert metrics["burst_cold_starts"] == 1
    assert metrics["slo_violation_rate"] == 0.5
    assert metrics["burst_ready_ratio"] == 0.5


def test_burst_metrics_empty_result_is_safe() -> None:
    metrics = compute_burst_metrics(SimResult(), SimConfig(duration_s=10))
    assert metrics["burst_intervals"] == 0
    assert metrics["burst_cold_start_share"] == 0.0
    assert metrics["burst_p99_latency_s"] is None
