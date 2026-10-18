"""
warmlambda.core.forecaster
==========================
Traffic rate forecasters for WarmLambda AI.

Defines the :class:`Forecaster` abstract base class and concrete implementations
including :class:`EWMAForecaster` (with optional Holt's linear trend),
:class:`SeasonalNaiveForecaster`, and :class:`LastValueForecaster`.

Provides :func:`evaluate_forecaster` for walk-forward evaluation using mean absolute
error (MAE) and symmetric mean absolute percentage error (sMAPE).

Poisson Noise Note
------------------
Even a perfect forecast of the underlying true arrival rate has non-zero error
when evaluated against actual discrete arrivals, due to intrinsic Poisson noise.
For a Poisson arrival process with rate λ over window length W, the observed count
X ~ Poisson(λW) has standard deviation:

    σ_count = sqrt(λ * W)  →  σ_rate = sqrt(λ / W)

Therefore, empirical forecast error metrics have a theoretical floor determined by
Poisson variance rather than model deficiency.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any

from warmlambda.core.config import SimConfig
from warmlambda.core.traffic import Request


class Forecaster(ABC):
    """Abstract base class for arrival rate forecasters.

    A forecaster estimates the expected arrival rate (requests per second)
    in the *next* decision window using *only* completed past arrival counts.
    """

    name: str

    @abstractmethod
    def predict(self, counts: list[int], window_s: float) -> float:
        """Predict the expected arrival rate (req/s) for the next window.

        Parameters
        ----------
        counts : list[int]
            Chronological arrival counts for completed past windows:
            ``[c_0, c_1, ..., c_{k-1}]``. Must only represent the past.
        window_s : float
            Duration of each window in seconds.

        Returns
        -------
        float
            Predicted arrival rate in req/s (must be >= 0.0).
        """
        ...


class EWMAForecaster(Forecaster):
    """Exponentially Weighted Moving Average (EWMA) forecaster.

    Supports simple exponential smoothing or Holt's two-parameter linear
    exponential smoothing (level + trend). Always guarantees a non-negative
    rate prediction.

    Parameters
    ----------
    alpha : float, default 0.4
        Smoothing factor for the level (0 < alpha <= 1).
    trend : bool, default False
        Whether to incorporate Holt's linear trend.
    beta : float, default 0.2
        Smoothing factor for the trend component (0 < beta <= 1), used when
        ``trend=True``.
    """

    def __init__(
        self,
        alpha: float = 0.4,
        trend: bool = False,
        beta: float = 0.2,
    ) -> None:
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(f"alpha must be in [0, 1], got {alpha}")
        if not (0.0 <= beta <= 1.0):
            raise ValueError(f"beta must be in [0, 1], got {beta}")

        self.alpha = float(alpha)
        self.trend = bool(trend)
        self.beta = float(beta)

        if self.trend:
            self.name = f"ewma_trend_a{self.alpha}_b{self.beta}"
        else:
            self.name = f"ewma_a{self.alpha}"

    def predict(self, counts: list[int], window_s: float) -> float:
        """Predict expected rate using EWMA (with optional Holt's trend)."""
        if not counts or window_s <= 0:
            return 0.0

        rates = [c / window_s for c in counts]

        if not self.trend:
            level = rates[0]
            for r in rates[1:]:
                level = self.alpha * r + (1.0 - self.alpha) * level
            return max(0.0, float(level))

        # Holt's linear method
        if len(rates) == 1:
            return max(0.0, float(rates[0]))

        level = rates[0]
        trend = rates[1] - rates[0]
        for r in rates[1:]:
            prev_level = level
            level = self.alpha * r + (1.0 - self.alpha) * (level + trend)
            trend = self.beta * (level - prev_level) + (1.0 - self.beta) * trend

        return max(0.0, float(level + trend))


class SeasonalNaiveForecaster(Forecaster):
    """Predict the count from one seasonal period ago.

    Falls back to the most recent value if history is shorter than the period.

    Parameters
    ----------
    period_windows : int
        Number of windows in one seasonal period (e.g. period_s / window_s).
    """

    def __init__(self, period_windows: int) -> None:
        if period_windows < 1:
            raise ValueError(f"period_windows must be >= 1, got {period_windows}")
        self.period_windows = int(period_windows)
        self.name = f"seasonal_naive_p{self.period_windows}"

    def predict(self, counts: list[int], window_s: float) -> float:
        """Predict expected rate from historical seasonal count."""
        if not counts or window_s <= 0:
            return 0.0

        if len(counts) >= self.period_windows:
            pred_count = counts[-self.period_windows]
        else:
            pred_count = counts[-1]

        return max(0.0, float(pred_count / window_s))


class LastValueForecaster(Forecaster):
    """Predict the arrival rate from the most recent completed window."""

    def __init__(self) -> None:
        self.name = "last_value"

    def predict(self, counts: list[int], window_s: float) -> float:
        if not counts or window_s <= 0:
            return 0.0
        return max(0.0, float(counts[-1] / window_s))


def bin_trace_to_windows(
    trace: list[Request],
    duration_s: float,
    window_s: float,
) -> list[int]:
    """Bin invocation arrival times into fixed-width window counts.

    Parameters
    ----------
    trace : list[Request]
        Invocation records with ``arrival_s`` timestamps.
    duration_s : float
        Total duration of the trace in seconds.
    window_s : float
        Length of each window in seconds.

    Returns
    -------
    list[int]
        Counts of arrivals in each window ``[0, 1, ..., n_windows - 1]``.
    """
    if duration_s <= 0 or window_s <= 0:
        return []

    n_windows = int(math.ceil(duration_s / window_s))
    counts = [0] * n_windows

    for req in trace:
        idx = int(req.arrival_s / window_s)
        if 0 <= idx < n_windows:
            counts[idx] += 1

    return counts


def evaluate_forecaster(
    trace: list[Request],
    cfg: SimConfig,
    forecaster: Forecaster,
    window_s: float,
    start_window: int = 1,
) -> dict[str, float]:
    """Evaluate a forecaster by walking forward through binned windows.

    For each window ``k >= start_window``, the forecast is generated using ONLY
    completed past windows ``0..k-1``. The prediction is then compared to the
    actual arrival rate in window ``k``.

    Parameters
    ----------
    trace : list[Request]
        Trace of request arrivals.
    cfg : SimConfig
        Simulation configuration (supplies ``duration_s``).
    forecaster : Forecaster
        The forecaster to evaluate.
    window_s : float
        Window size in seconds.
    start_window : int, default 1
        First window to evaluate (must be >= 1 to ensure at least 1 past window).

    Returns
    -------
    dict[str, float]
        Dictionary with keys ``"mae"`` and ``"smape"``:
        - ``mae``: Mean Absolute Error between actual and predicted rates (req/s).
        - ``smape``: Symmetric Mean Absolute Percentage Error in [0.0, 2.0].
    """
    counts = bin_trace_to_windows(trace, cfg.duration_s, window_s)
    total_windows = len(counts)

    if total_windows <= start_window:
        return {"mae": 0.0, "smape": 0.0}

    abs_errors: list[float] = []
    smape_terms: list[float] = []

    for k in range(start_window, total_windows):
        past_counts = counts[:k]
        pred_rate = forecaster.predict(past_counts, window_s)
        actual_rate = counts[k] / window_s

        diff = abs(actual_rate - pred_rate)
        abs_errors.append(diff)

        denom = abs(actual_rate) + abs(pred_rate)
        if denom > 1e-12:
            smape_terms.append(2.0 * diff / denom)
        else:
            smape_terms.append(0.0)

    mae = float(sum(abs_errors) / len(abs_errors)) if abs_errors else 0.0
    smape = float(sum(smape_terms) / len(smape_terms)) if smape_terms else 0.0

    return {
        "mae": mae,
        "smape": smape,
    }
