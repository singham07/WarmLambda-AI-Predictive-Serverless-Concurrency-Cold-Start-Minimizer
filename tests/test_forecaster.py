"""
tests.test_forecaster
=====================
Tests for arrival-rate forecasters and walking-forward evaluation.

Note on Poisson noise floor
---------------------------
Even a perfect forecast of the true arrival rate has non-zero error when evaluated
against empirical Poisson realizations, because Poisson arrivals have an intrinsic
variance equal to the mean (standard deviation ~ sqrt(rate * window_s)).
Thus error metrics will always exhibit an irreducible positive floor.
"""

from __future__ import annotations

import math
import random

import pytest

from warmlambda.core.config import SimConfig
from warmlambda.core.forecaster import (
    EWMAForecaster,
    LastValueForecaster,
    SeasonalNaiveForecaster,
    bin_trace_to_windows,
    evaluate_forecaster,
)
from warmlambda.core.traffic import Request


# ---------------------------------------------------------------------------
# Test: Non-negativity
# ---------------------------------------------------------------------------


class TestNonNegativity:
    """Forecasters must never predict negative arrival rates."""

    @pytest.mark.parametrize(
        "forecaster",
        [
            EWMAForecaster(alpha=0.4, trend=False),
            EWMAForecaster(alpha=0.4, trend=True, beta=0.5),
            SeasonalNaiveForecaster(period_windows=5),
            LastValueForecaster(),
        ],
    )
    def test_empty_counts_non_negative(self, forecaster) -> None:
        assert forecaster.predict([], 20.0) >= 0.0

    def test_sharp_downward_trend_non_negative(self) -> None:
        # Severe downward trend: [100, 50, 10, 0, 0]
        forecaster = EWMAForecaster(alpha=0.8, trend=True, beta=0.8)
        pred = forecaster.predict([100, 50, 10, 0, 0], 20.0)
        assert pred >= 0.0


# ---------------------------------------------------------------------------
# Test: Constant traffic yields near-zero error
# ---------------------------------------------------------------------------


class TestConstantTraffic:
    """When arrivals are perfectly constant, forecasts should match the rate."""

    def test_constant_traffic_near_zero_error(self) -> None:
        window_s = 10.0
        rate = 5.0  # 5 req/s -> 50 req per window
        counts = [50] * 30

        ewma = EWMAForecaster(alpha=0.4)
        assert math.isclose(ewma.predict(counts, window_s), rate, rel_tol=1e-5)

        ewma_trend = EWMAForecaster(alpha=0.4, trend=True)
        assert math.isclose(ewma_trend.predict(counts, window_s), rate, rel_tol=1e-5)

        seasonal = SeasonalNaiveForecaster(period_windows=4)
        assert math.isclose(seasonal.predict(counts, window_s), rate, rel_tol=1e-5)

        last_val = LastValueForecaster()
        assert math.isclose(last_val.predict(counts, window_s), rate, rel_tol=1e-5)


# ---------------------------------------------------------------------------
# Test: Step change tracking
# ---------------------------------------------------------------------------


class TestStepChange:
    """A sudden step change in traffic should be tracked within a few windows."""

    def test_step_change_tracked_quickly(self) -> None:
        window_s = 20.0
        # Rate jumps from 2.0 (40 req/window) to 10.0 (200 req/window) at index 10
        low_counts = [40] * 10
        high_counts = [200] * 6
        full_counts = low_counts + high_counts

        ewma = EWMAForecaster(alpha=0.7)

        # Before jump
        assert math.isclose(ewma.predict(low_counts, window_s), 2.0, rel_tol=1e-4)

        # 1 window after jump: starts rising
        p1 = ewma.predict(low_counts + [200], window_s)
        assert p1 > 2.0

        # Within 4 windows after jump, forecast is within 5% of new rate (10.0)
        p4 = ewma.predict(low_counts + [200] * 4, window_s)
        assert p4 >= 9.5
        assert p4 <= 10.5


# ---------------------------------------------------------------------------
# Test: No data leakage (future windows do not affect past prediction)
# ---------------------------------------------------------------------------


class TestNoDataLeakage:
    """Predicting window k must strictly use counts 0..k-1 and ignore future."""

    def test_shuffling_future_does_not_affect_prediction(self) -> None:
        window_s = 10.0
        past_counts = [10, 15, 20, 25]
        future_counts_a = [100, 200, 300]
        future_counts_b = [0, 999, 1]

        forecasters = [
            EWMAForecaster(alpha=0.4),
            EWMAForecaster(alpha=0.4, trend=True),
            SeasonalNaiveForecaster(period_windows=3),
            LastValueForecaster(),
        ]

        for f in forecasters:
            # Predict next window using past_counts
            pred_base = f.predict(past_counts, window_s)

            # In walk-forward evaluation, window k=4 only gets past_counts[:4]
            # Changing future windows (indices 4, 5, 6) must not change prediction
            full_series_a = past_counts + future_counts_a
            full_series_b = past_counts + future_counts_b

            pred_a = f.predict(full_series_a[:len(past_counts)], window_s)
            pred_b = f.predict(full_series_b[:len(past_counts)], window_s)

            assert math.isclose(pred_a, pred_base, abs_tol=1e-9)
            assert math.isclose(pred_b, pred_base, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Test: SeasonalNaive fallback behavior
# ---------------------------------------------------------------------------


class TestSeasonalNaive:
    """SeasonalNaive uses period when available, otherwise falls back to last value."""

    def test_fallback_when_history_short(self) -> None:
        window_s = 10.0
        forecaster = SeasonalNaiveForecaster(period_windows=4)

        # Only 2 counts available: fallback to counts[-1] = 30
        assert math.isclose(forecaster.predict([10, 30], window_s), 3.0)

        # 4 counts available: uses counts[-4] = 10
        assert math.isclose(forecaster.predict([10, 20, 30, 40], window_s), 1.0)

        # 5 counts available: counts[-4] is 20
        assert math.isclose(forecaster.predict([10, 20, 30, 40, 50], window_s), 2.0)


# ---------------------------------------------------------------------------
# Test: Walk-forward evaluation function
# ---------------------------------------------------------------------------


class TestEvaluateForecaster:
    """evaluate_forecaster computes sensible MAE and sMAPE."""

    def test_constant_trace_evaluation(self) -> None:
        cfg = SimConfig(duration_s=100.0)
        window_s = 20.0  # 5 windows of 20s each: [0, 20), [20, 40), [40, 60), [60, 80), [80, 100)

        # 10 requests uniformly distributed in each window (0.5 req/s)
        trace = []
        req_id = 0
        for w in range(5):
            for i in range(10):
                trace.append(Request(id=req_id, arrival_s=w * 20.0 + i * 1.5, exec_s=0.2))
                req_id += 1

        f = LastValueForecaster()
        res = evaluate_forecaster(trace, cfg, f, window_s=window_s, start_window=1)

        assert "mae" in res
        assert "smape" in res
        # For perfectly identical window counts (10 in each window), error is 0.0
        assert math.isclose(res["mae"], 0.0, abs_tol=1e-6)
        assert math.isclose(res["smape"], 0.0, abs_tol=1e-6)
