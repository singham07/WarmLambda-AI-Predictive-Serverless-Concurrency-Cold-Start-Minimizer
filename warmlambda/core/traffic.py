"""
warmlambda.core.traffic
=======================
Traffic generation for WarmLambda AI.

Provides four rate-function factories (scenarios), a thinning-based
non-homogeneous Poisson process generator, and CSV persistence.

Rate functions
--------------
Each factory has signature ``(cfg: SimConfig, seed: int) -> RateFn`` where
``RateFn = Callable[[float], float]`` maps simulation time *t* (seconds) to
an instantaneous arrival rate in **requests per second**.

Scenarios
---------
moderate   – base 3 req/s ± 30 % sine wave, period 1200 s
high_load  – base 30 req/s, linear ramp 0.6× → 1.4× over the simulation
extreme    – base 2 req/s + 3-6 random spikes of 15× lasting 30-120 s each
periodic   – base 5 req/s with 60 % sine amplitude, period 600 s

Thinning method
---------------
Lewis-Shedler thinning algorithm: generate a homogeneous Poisson process at
``λ_max`` (numerically determined), then independently accept each candidate
event with probability ``rate(t) / λ_max``.

Execution times
---------------
Drawn from a log-normal distribution whose *mean* equals ``cfg.mean_exec_s``::

    μ_ln = log(mean) − σ²/2   →   E[X] = exp(μ_ln + σ²/2) = mean  ✓

Reproducibility
---------------
All randomness flows through ``numpy.random.default_rng``.  The same
``(scenario, cfg, seed)`` triple always produces an identical trace.
"""

from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass
from typing import Callable

import numpy as np

from warmlambda.core.config import SimConfig

# Public type alias
RateFn = Callable[[float], float]

# ---------------------------------------------------------------------------
# Request dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Request:
    """A single serverless function invocation request.

    Attributes
    ----------
    id : int
        Zero-based sequential index within the trace (order = arrival order).
    arrival_s : float
        Simulated arrival time in seconds from simulation start.
    exec_s : float
        Execution duration in seconds, sampled from a log-normal distribution
        whose mean equals ``SimConfig.mean_exec_s``.
    """

    id: int
    arrival_s: float
    exec_s: float


# ---------------------------------------------------------------------------
# Rate function factories
# ---------------------------------------------------------------------------


def _make_moderate(cfg: SimConfig, seed: int) -> RateFn:  # noqa: ARG001
    """Base 3 req/s with ±30 % sine modulation, period 1200 s.

    rate(t) = 3 · (1 + 0.30 · sin(2π·t / 1200))

    Maximum rate: 3.0 × 1.30 = 3.90 req/s
    Expected total over 3600 s: 10 800 requests (sine averages to zero).
    """
    BASE = 3.0
    AMPLITUDE = 0.30
    PERIOD = 1_200.0

    def rate_fn(t: float) -> float:
        return BASE * (1.0 + AMPLITUDE * math.sin(2.0 * math.pi * t / PERIOD))

    return rate_fn


def _make_high_load(cfg: SimConfig, seed: int) -> RateFn:  # noqa: ARG001
    """Base 30 req/s with a linear ramp: 0.6× at t=0 → 1.4× at t=duration_s.

    rate(t) = 30 · (0.6 + 0.8 · t / duration_s)

    Maximum rate: 30 × 1.4 = 42.0 req/s
    Expected total over 3600 s: 108 000 requests.
    """
    BASE = 30.0

    def rate_fn(t: float) -> float:
        scale = 0.6 + 0.8 * (t / cfg.duration_s)
        return BASE * scale

    return rate_fn


def _make_extreme(cfg: SimConfig, seed: int) -> RateFn:
    """Base 2 req/s plus 3-6 non-overlapping spikes of 15× lasting 30-120 s.

    Spike timing is determined by *seed* so results are fully reproducible.
    Spikes are guaranteed not to overlap: remaining slack is distributed as
    inter-spike gaps using a Dirichlet split.

    Maximum rate during a spike: 2 × 15 = 30 req/s.
    """
    BASE = 2.0
    SPIKE_MULT = 15.0
    MIN_GAP = 5.0  # minimum seconds between consecutive spikes / edges

    # Use [seed, 1] so spike placement and arrival thinning are independent
    rng = np.random.default_rng([seed, 1])

    n_spikes = int(rng.integers(3, 7))  # inclusive range [3, 6]
    durations = rng.uniform(30.0, 120.0, size=n_spikes)

    total_spike = float(durations.sum())
    min_slack = MIN_GAP * (n_spikes + 1)

    # If total spike time + mandatory gaps exceed duration, scale durations down
    if total_spike + min_slack > cfg.duration_s:
        max_spike = max(cfg.duration_s - min_slack, n_spikes * 10.0)
        durations = durations * (max_spike / total_spike)
        total_spike = float(durations.sum())

    # Distribute remaining slack into (n_spikes+1) gaps using Dirichlet split
    remaining = cfg.duration_s - total_spike
    raw_gaps = rng.exponential(1.0, size=n_spikes + 1)
    gaps = (raw_gaps / raw_gaps.sum()) * remaining

    # Build spike [start, end) intervals
    starts = np.empty(n_spikes)
    t = gaps[0]
    for i in range(n_spikes):
        starts[i] = t
        t += durations[i] + gaps[i + 1]

    ends = starts + durations
    _intervals: list[tuple[float, float]] = list(zip(starts.tolist(), ends.tolist()))

    def rate_fn(t: float) -> float:
        for s, e in _intervals:
            if s <= t < e:
                return BASE * SPIKE_MULT
        return BASE

    return rate_fn


def _make_periodic(cfg: SimConfig, seed: int) -> RateFn:  # noqa: ARG001
    """Base 5 req/s with 60 % sine amplitude, period 600 s.

    rate(t) = 5 · (1 + 0.60 · sin(2π·t / 600))

    Maximum rate: 5.0 × 1.60 = 8.0 req/s.
    The repeating 600 s pattern completes 6 full cycles in a 3600 s simulation.
    """
    BASE = 5.0
    AMPLITUDE = 0.60
    PERIOD = 600.0

    def rate_fn(t: float) -> float:
        return BASE * (1.0 + AMPLITUDE * math.sin(2.0 * math.pi * t / PERIOD))

    return rate_fn


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, Callable[[SimConfig, int], RateFn]] = {
    "moderate": _make_moderate,
    "high_load": _make_high_load,
    "extreme": _make_extreme,
    "periodic": _make_periodic,
}


def get_max_rate(
    scenario: str,
    cfg: SimConfig,
    seed: int,
    n_points: int = 10_000,
) -> float:
    """Return the numerical maximum of the rate function over [0, duration_s).

    Evaluates the rate function on a uniform grid of *n_points* and returns
    the maximum value.  Used internally by :func:`generate_trace` as
    ``λ_max`` for the thinning algorithm, and exposed for callers that need
    an upper-bound estimate (e.g. capacity-planning scripts).

    Parameters
    ----------
    scenario : str
        One of the keys in :data:`SCENARIOS`.
    cfg : SimConfig
        Simulation configuration (supplies ``duration_s``).
    seed : int
        Passed to the rate-function factory (only matters for ``extreme``).
    n_points : int
        Grid resolution.  Higher values give a tighter ``λ_max`` bound.

    Returns
    -------
    float
        Maximum instantaneous rate in req/s.

    Raises
    ------
    ValueError
        If *scenario* is not in :data:`SCENARIOS`.
    """
    if scenario not in SCENARIOS:
        raise ValueError(
            f"Unknown scenario {scenario!r}. Valid scenarios: {sorted(SCENARIOS)}"
        )
    rate_fn = SCENARIOS[scenario](cfg, seed)
    ts = np.linspace(0.0, cfg.duration_s, n_points, endpoint=False)
    rates = np.vectorize(rate_fn)(ts)
    return float(rates.max())


# ---------------------------------------------------------------------------
# Trace generation
# ---------------------------------------------------------------------------


def generate_trace(scenario: str, cfg: SimConfig, seed: int) -> list[Request]:
    """Generate a complete invocation trace using a non-homogeneous Poisson process.

    Uses the Lewis-Shedler *thinning* method:

    1. Compute ``λ_max = max rate × 1.01`` (1 % safety margin) on a 10 000-
       point grid.
    2. Generate inter-arrival times from ``Exponential(λ_max)`` to build a
       homogeneous Poisson proposal process.
    3. Accept each candidate at time *t* independently with probability
       ``rate(t) / λ_max``.
    4. Draw execution durations from ``LogNormal(μ_ln, σ)`` where
       ``μ_ln = log(mean) − σ²/2`` guarantees ``E[exec_s] = cfg.mean_exec_s``.

    All randomness is seeded with ``[seed, 0]`` for thinning and ``[seed, 1]``
    for spike placement (extreme scenario), ensuring full reproducibility.

    Parameters
    ----------
    scenario : str
        Traffic scenario key (see :data:`SCENARIOS`).
    cfg : SimConfig
        Simulation configuration.
    seed : int
        Master random seed.  Same ``(scenario, cfg, seed)`` → identical trace.

    Returns
    -------
    list[Request]
        Trace sorted by ``arrival_s``, IDs 0 .. n-1.
        All arrivals satisfy ``0 ≤ arrival_s < cfg.duration_s``.

    Raises
    ------
    ValueError
        If *scenario* is not recognised.
    """
    if scenario not in SCENARIOS:
        raise ValueError(
            f"Unknown scenario {scenario!r}. Valid scenarios: {sorted(SCENARIOS)}"
        )

    rate_fn = SCENARIOS[scenario](cfg, seed)

    # --- Compute λ_max on a fine grid ----------------------------------------
    ts_grid = np.linspace(0.0, cfg.duration_s, 10_000, endpoint=False)
    lambda_max = float(np.vectorize(rate_fn)(ts_grid).max()) * 1.01

    # --- Thinning (Lewis-Shedler) algorithm ----------------------------------
    # Seed [seed, 0] is independent from spike-placement seed [seed, 1]
    rng = np.random.default_rng([seed, 0])

    arrival_times: list[float] = []
    t = 0.0
    while True:
        # Next candidate from homogeneous Poisson(λ_max)
        t += rng.exponential(1.0 / lambda_max)
        if t >= cfg.duration_s:
            break
        # Accept with probability rate(t) / λ_max
        if rng.random() <= rate_fn(t) / lambda_max:
            arrival_times.append(t)

    # --- Draw execution times ------------------------------------------------
    n = len(arrival_times)
    if n > 0:
        # Log-normal parameterisation so that E[exec_s] = cfg.mean_exec_s
        mu_ln = math.log(cfg.mean_exec_s) - 0.5 * cfg.exec_sigma ** 2
        exec_arr = rng.lognormal(mean=mu_ln, sigma=cfg.exec_sigma, size=n)
    else:
        exec_arr = np.empty(0, dtype=float)

    # Arrivals are already in ascending order (thinning preserves order)
    requests = [
        Request(id=i, arrival_s=arrival_times[i], exec_s=float(exec_arr[i]))
        for i in range(n)
    ]
    return requests


# ---------------------------------------------------------------------------
# CSV persistence
# ---------------------------------------------------------------------------


def save_trace(path: str | os.PathLike, trace: list[Request]) -> None:
    """Save a trace to a CSV file with exact floating-point round-trip.

    Columns: ``id``, ``arrival_s``, ``exec_s``.  Float values are written
    using ``repr()`` which guarantees ``float(repr(x)) == x`` in Python 3.

    Parameters
    ----------
    path : str | os.PathLike
        Destination file path.  Parent directory must exist.
    trace : list[Request]
        Trace to persist (typically sorted by ``arrival_s``).
    """
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "arrival_s", "exec_s"])
        for req in trace:
            writer.writerow([req.id, repr(req.arrival_s), repr(req.exec_s)])


def load_trace(path: str | os.PathLike) -> list[Request]:
    """Load a trace previously saved with :func:`save_trace`.

    Parameters
    ----------
    path : str | os.PathLike
        Path to the CSV file.

    Returns
    -------
    list[Request]
        Requests in file order (should be sorted by ``arrival_s``).
    """
    requests: list[Request] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            requests.append(
                Request(
                    id=int(row["id"]),
                    arrival_s=float(row["arrival_s"]),
                    exec_s=float(row["exec_s"]),
                )
            )
    return requests
