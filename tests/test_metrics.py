"""
Tests for warmlambda.core.metrics
==================================
Hand-built SimResult objects with known numbers.
"""

from __future__ import annotations

import math

import pytest

from warmlambda.core.config import SimConfig
from warmlambda.core.metrics import compute_metrics, metrics_to_row
from warmlambda.core.simulator import RequestRecord, SimResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(**overrides) -> SimConfig:
    defaults = dict(
        duration_s=100.0,
        init_time_s=1.0,
        mean_exec_s=0.2,
        exec_sigma=0.5,
        idle_timeout_s=300.0,
        max_instances=100,
        concurrency_per_instance=1,
        queue_timeout_s=10.0,
        decision_interval_s=20.0,
        warm_cost_weight=1.0,
        busy_cost_weight=1.0,
    )
    defaults.update(overrides)
    return SimConfig(**defaults)


def _rec(
    id: int,
    arrival_s: float,
    start_s: float | None,
    finish_s: float | None,
    cold: bool,
    dropped: bool,
) -> RequestRecord:
    if start_s is not None and finish_s is not None:
        latency_s = finish_s - arrival_s
    else:
        latency_s = None
    return RequestRecord(
        id=id,
        arrival_s=arrival_s,
        start_s=start_s,
        finish_s=finish_s,
        cold=cold,
        dropped=dropped,
        latency_s=latency_s,
    )


# ---------------------------------------------------------------------------
# Test: hand-built SimResult with known numbers
# ---------------------------------------------------------------------------

class TestKnownMetrics:
    """Four requests: 2 cold, 1 warm, 1 dropped → exact metric values."""

    @pytest.fixture()
    def result_and_cfg(self) -> tuple[SimResult, SimConfig]:
        cfg = _cfg(warm_cost_weight=2.0, busy_cost_weight=1.5)
        # Request 0: cold, arrival=0, start=1.0, finish=1.5 → latency=1.5
        # Request 1: warm, arrival=5, start=5.0, finish=5.5 → latency=0.5
        # Request 2: cold, arrival=10, start=11.0, finish=12.0 → latency=2.0
        # Request 3: dropped
        requests = [
            _rec(0, arrival_s=0.0, start_s=1.0, finish_s=1.5, cold=True, dropped=False),
            _rec(1, arrival_s=5.0, start_s=5.0, finish_s=5.5, cold=False, dropped=False),
            _rec(2, arrival_s=10.0, start_s=11.0, finish_s=12.0, cold=True, dropped=False),
            _rec(3, arrival_s=15.0, start_s=None, finish_s=None, cold=False, dropped=True),
        ]
        result = SimResult(
            requests=requests,
            intervals=[],
            busy_seconds=10.0,
            idle_warm_seconds=20.0,
            init_seconds=5.0,
        )
        return result, cfg

    def test_n_requests(self, result_and_cfg: tuple[SimResult, SimConfig]) -> None:
        result, cfg = result_and_cfg
        m = compute_metrics(result, cfg)
        assert m["n_requests"] == 4

    def test_n_dropped(self, result_and_cfg: tuple[SimResult, SimConfig]) -> None:
        result, cfg = result_and_cfg
        m = compute_metrics(result, cfg)
        assert m["n_dropped"] == 1

    def test_dropped_rate(self, result_and_cfg: tuple[SimResult, SimConfig]) -> None:
        result, cfg = result_and_cfg
        m = compute_metrics(result, cfg)
        assert math.isclose(m["dropped_rate"], 0.25, abs_tol=1e-9)

    def test_cold_start_count(self, result_and_cfg: tuple[SimResult, SimConfig]) -> None:
        result, cfg = result_and_cfg
        m = compute_metrics(result, cfg)
        assert m["cold_start_count"] == 2

    def test_cold_start_rate(self, result_and_cfg: tuple[SimResult, SimConfig]) -> None:
        result, cfg = result_and_cfg
        m = compute_metrics(result, cfg)
        # 2 cold / 3 non-dropped = 0.6667
        assert math.isclose(m["cold_start_rate"], 2.0 / 3.0, abs_tol=1e-9)

    def test_mean_latency(self, result_and_cfg: tuple[SimResult, SimConfig]) -> None:
        result, cfg = result_and_cfg
        m = compute_metrics(result, cfg)
        # (1.5 + 0.5 + 2.0) / 3 = 4.0/3 ≈ 1.3333
        assert math.isclose(m["mean_latency_s"], 4.0 / 3.0, abs_tol=1e-9)

    def test_p50_latency(self, result_and_cfg: tuple[SimResult, SimConfig]) -> None:
        result, cfg = result_and_cfg
        m = compute_metrics(result, cfg)
        # sorted latencies: [0.5, 1.5, 2.0] → median = 1.5
        assert math.isclose(m["p50_latency_s"], 1.5, abs_tol=1e-9)

    def test_p95_latency(self, result_and_cfg: tuple[SimResult, SimConfig]) -> None:
        result, cfg = result_and_cfg
        m = compute_metrics(result, cfg)
        # p95 of [0.5, 1.5, 2.0] → close to 2.0
        assert m["p95_latency_s"] >= 1.5
        assert m["p95_latency_s"] <= 2.0 + 1e-9

    def test_p99_latency(self, result_and_cfg: tuple[SimResult, SimConfig]) -> None:
        result, cfg = result_and_cfg
        m = compute_metrics(result, cfg)
        assert m["p99_latency_s"] >= 1.5
        assert m["p99_latency_s"] <= 2.0 + 1e-9

    def test_instance_seconds(self, result_and_cfg: tuple[SimResult, SimConfig]) -> None:
        result, cfg = result_and_cfg
        m = compute_metrics(result, cfg)
        assert m["busy_instance_seconds"] == 10.0
        assert m["idle_warm_instance_seconds"] == 20.0
        assert m["init_instance_seconds"] == 5.0

    def test_total_cost(self, result_and_cfg: tuple[SimResult, SimConfig]) -> None:
        result, cfg = result_and_cfg
        m = compute_metrics(result, cfg)
        # 10 * 1.5 + (20 + 5) * 2.0 = 15 + 50 = 65
        assert math.isclose(m["total_cost"], 65.0, abs_tol=1e-9)

    def test_utilization(self, result_and_cfg: tuple[SimResult, SimConfig]) -> None:
        result, cfg = result_and_cfg
        m = compute_metrics(result, cfg)
        # 10 / (10 + 20 + 5) = 10/35 ≈ 0.2857
        assert math.isclose(m["utilization"], 10.0 / 35.0, abs_tol=1e-9)

    def test_all_keys_present(self, result_and_cfg: tuple[SimResult, SimConfig]) -> None:
        result, cfg = result_and_cfg
        m = compute_metrics(result, cfg)
        expected_keys = {
            "n_requests", "n_dropped", "dropped_rate",
            "cold_start_count", "cold_start_rate",
            "mean_latency_s", "p50_latency_s", "p95_latency_s", "p99_latency_s",
            "busy_instance_seconds", "idle_warm_instance_seconds",
            "init_instance_seconds", "total_cost", "utilization",
        }
        assert set(m.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Test: empty result (no requests at all)
# ---------------------------------------------------------------------------

class TestEmptyResult:
    """Empty trace → counts are 0, latencies and rates are nan."""

    @pytest.fixture()
    def metrics(self) -> dict:
        cfg = _cfg()
        result = SimResult(
            requests=[],
            intervals=[],
            busy_seconds=0.0,
            idle_warm_seconds=0.0,
            init_seconds=0.0,
        )
        return compute_metrics(result, cfg)

    def test_counts_zero(self, metrics: dict) -> None:
        assert metrics["n_requests"] == 0
        assert metrics["n_dropped"] == 0
        assert metrics["cold_start_count"] == 0

    def test_dropped_rate_zero(self, metrics: dict) -> None:
        assert metrics["dropped_rate"] == 0.0

    def test_cold_start_rate_nan(self, metrics: dict) -> None:
        assert math.isnan(metrics["cold_start_rate"])

    def test_latencies_nan(self, metrics: dict) -> None:
        assert math.isnan(metrics["mean_latency_s"])
        assert math.isnan(metrics["p50_latency_s"])
        assert math.isnan(metrics["p95_latency_s"])
        assert math.isnan(metrics["p99_latency_s"])

    def test_cost_zero(self, metrics: dict) -> None:
        assert metrics["total_cost"] == 0.0

    def test_utilization_nan(self, metrics: dict) -> None:
        assert math.isnan(metrics["utilization"])


# ---------------------------------------------------------------------------
# Test: all dropped
# ---------------------------------------------------------------------------

class TestAllDropped:
    """Every request dropped → cold_start_rate is nan, latencies are nan."""

    @pytest.fixture()
    def metrics(self) -> dict:
        cfg = _cfg()
        requests = [
            _rec(0, 0.0, None, None, cold=False, dropped=True),
            _rec(1, 1.0, None, None, cold=False, dropped=True),
            _rec(2, 2.0, None, None, cold=False, dropped=True),
        ]
        result = SimResult(
            requests=requests,
            intervals=[],
            busy_seconds=0.0,
            idle_warm_seconds=5.0,
            init_seconds=3.0,
        )
        return compute_metrics(result, cfg)

    def test_n_requests(self, metrics: dict) -> None:
        assert metrics["n_requests"] == 3

    def test_n_dropped(self, metrics: dict) -> None:
        assert metrics["n_dropped"] == 3

    def test_dropped_rate(self, metrics: dict) -> None:
        assert math.isclose(metrics["dropped_rate"], 1.0, abs_tol=1e-9)

    def test_cold_start_count_zero(self, metrics: dict) -> None:
        assert metrics["cold_start_count"] == 0

    def test_cold_start_rate_nan(self, metrics: dict) -> None:
        assert math.isnan(metrics["cold_start_rate"])

    def test_latencies_nan(self, metrics: dict) -> None:
        assert math.isnan(metrics["mean_latency_s"])
        assert math.isnan(metrics["p50_latency_s"])
        assert math.isnan(metrics["p95_latency_s"])
        assert math.isnan(metrics["p99_latency_s"])

    def test_utilization_zero(self, metrics: dict) -> None:
        # busy=0, total=8 → utilization=0
        assert math.isclose(metrics["utilization"], 0.0, abs_tol=1e-9)

    def test_total_cost(self, metrics: dict) -> None:
        # 0*1 + (5+3)*1 = 8
        assert math.isclose(metrics["total_cost"], 8.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Test: metrics_to_row
# ---------------------------------------------------------------------------

class TestMetricsToRow:
    """metrics_to_row prepends scenario, policy, seed."""

    def test_row_has_prefix_keys(self) -> None:
        cfg = _cfg()
        result = SimResult(
            requests=[
                _rec(0, 0.0, 1.0, 1.5, cold=True, dropped=False),
            ],
            intervals=[],
            busy_seconds=1.0,
            idle_warm_seconds=2.0,
            init_seconds=0.5,
        )
        m = compute_metrics(result, cfg)
        row = metrics_to_row(m, scenario="moderate", policy_name="no_warming", seed=42)

        assert row["scenario"] == "moderate"
        assert row["policy"] == "no_warming"
        assert row["seed"] == 42
        # All metric keys should also be present
        for key in m:
            assert key in row
            assert row[key] == m[key] or (
                math.isnan(row[key]) and math.isnan(m[key])
            )


# ---------------------------------------------------------------------------
# Integration: NoWarming on moderate → sensible values
# ---------------------------------------------------------------------------

class TestIntegrationModerate:
    """Metrics from a real simulation should have sensible ranges."""

    def test_sensible_metrics(self) -> None:
        from warmlambda.core.policies.no_warming import NoWarming
        from warmlambda.core.simulator import simulate
        from warmlambda.core.traffic import generate_trace

        cfg = SimConfig()
        trace = generate_trace("moderate", cfg, seed=42)
        result = simulate(trace, NoWarming(), cfg)
        m = compute_metrics(result, cfg)

        assert m["n_requests"] > 0
        assert 0.0 <= m["cold_start_rate"] <= 1.0
        assert 0.0 <= m["utilization"] <= 1.0
        assert m["mean_latency_s"] > 0.0
        assert m["p50_latency_s"] > 0.0
        assert m["p95_latency_s"] >= m["p50_latency_s"]
        assert m["p99_latency_s"] >= m["p95_latency_s"]
        assert m["total_cost"] > 0.0

        # Print for visual inspection
        print("\n  Metrics for moderate / NoWarming / seed=42:")
        for k, v in m.items():
            if isinstance(v, float):
                print(f"    {k:30s} = {v:.6f}")
            else:
                print(f"    {k:30s} = {v}")
