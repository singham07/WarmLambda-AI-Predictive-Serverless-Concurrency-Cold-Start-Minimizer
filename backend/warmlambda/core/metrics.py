"""
warmlambda.core.metrics
========================
Post-simulation metrics for WarmLambda AI.

Computes a flat dictionary of aggregate statistics from a
:class:`~warmlambda.core.simulator.SimResult` and a
:class:`~warmlambda.core.config.SimConfig`.

Edge-case contract
------------------
* **No requests** (empty trace): counts are ``0``, rates are ``0.0``,
  latency percentiles are ``float('nan')``, utilization is ``float('nan')``,
  total_cost is ``0.0``.
* **All dropped**: ``cold_start_rate`` is ``float('nan')`` (0 non-dropped),
  latency percentiles are ``float('nan')``, utilization follows from
  instance seconds.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from backend.warmlambda.core.config import SimConfig
from backend.warmlambda.core.simulator import SimResult


_NAN = float("nan")


def compute_metrics(result: SimResult, cfg: SimConfig) -> dict[str, Any]:
    """Derive aggregate metrics from a simulation result.

    Parameters
    ----------
    result : SimResult
        Output of :func:`~warmlambda.core.simulator.simulate`.
    cfg : SimConfig
        The configuration used for the run (supplies cost weights).

    Returns
    -------
    dict[str, Any]
        Flat dictionary with exactly the keys documented below.

    Keys
    ----
    n_requests : int
        Total number of requests in the trace.
    n_dropped : int
        Number of dropped (timed-out) requests.
    dropped_rate : float
        ``n_dropped / n_requests``, or ``0.0`` when ``n_requests == 0``.
    cold_start_count : int
        Number of non-dropped requests served via a cold start.
    cold_start_rate : float
        ``cold_start_count / (n_requests - n_dropped)``, or ``nan`` when
        all requests were dropped or the trace was empty.
    mean_latency_s : float
        Arithmetic mean of ``latency_s`` over non-dropped requests, or
        ``nan`` when there are no non-dropped requests.
    p50_latency_s : float
        Median latency (50th percentile), or ``nan``.
    p95_latency_s : float
        95th-percentile latency, or ``nan``.
    p99_latency_s : float
        99th-percentile latency, or ``nan``.
    busy_instance_seconds : float
        Total instance-seconds spent in BUSY state.
    idle_warm_instance_seconds : float
        Total instance-seconds spent in IDLE (warm) state.
    init_instance_seconds : float
        Total instance-seconds spent in INITIALIZING state.
    total_cost : float
        ``busy_seconds * busy_cost_weight
        + (idle_warm_seconds + init_seconds) * warm_cost_weight``.
    utilization : float
        ``busy_seconds / (busy + idle_warm + init)``, or ``nan`` when
        total instance-seconds is zero.
    """
    n_requests = len(result.requests)
    n_dropped = sum(1 for r in result.requests if r.dropped)
    n_completed = n_requests - n_dropped

    dropped_rate = n_dropped / n_requests if n_requests > 0 else 0.0

    cold_start_count = sum(
        1 for r in result.requests if r.cold and not r.dropped
    )
    cold_start_rate = (
        cold_start_count / n_completed if n_completed > 0 else _NAN
    )

    # Latency statistics (non-dropped only)
    latencies = np.array(
        [r.latency_s for r in result.requests
         if not r.dropped and r.latency_s is not None],
        dtype=float,
    )

    if len(latencies) > 0:
        mean_latency_s = float(np.mean(latencies))
        p50_latency_s = float(np.percentile(latencies, 50))
        p95_latency_s = float(np.percentile(latencies, 95))
        p99_latency_s = float(np.percentile(latencies, 99))
    else:
        mean_latency_s = _NAN
        p50_latency_s = _NAN
        p95_latency_s = _NAN
        p99_latency_s = _NAN

    # Instance-second accounting
    busy_s = result.busy_seconds
    idle_s = result.idle_warm_seconds
    init_s = result.init_seconds

    total_cost = (
        busy_s * cfg.busy_cost_weight
        + (idle_s + init_s) * cfg.warm_cost_weight
    )

    total_instance_s = busy_s + idle_s + init_s
    utilization = busy_s / total_instance_s if total_instance_s > 0 else _NAN

    return {
        "n_requests": n_requests,
        "n_dropped": n_dropped,
        "dropped_rate": dropped_rate,
        "cold_start_count": cold_start_count,
        "cold_start_rate": cold_start_rate,
        "mean_latency_s": mean_latency_s,
        "p50_latency_s": p50_latency_s,
        "p95_latency_s": p95_latency_s,
        "p99_latency_s": p99_latency_s,
        "busy_instance_seconds": busy_s,
        "idle_warm_instance_seconds": idle_s,
        "init_instance_seconds": init_s,
        "total_cost": total_cost,
        "utilization": utilization,
    }


def metrics_to_row(
    metrics: dict[str, Any],
    scenario: str,
    policy_name: str,
    seed: int,
) -> dict[str, Any]:
    """Flatten metrics into a single CSV-friendly row.

    Prepends ``scenario``, ``policy``, and ``seed`` columns to the metrics
    dictionary so that results from multiple runs can be concatenated into
    a single table.

    Parameters
    ----------
    metrics : dict[str, Any]
        Output of :func:`compute_metrics`.
    scenario : str
        Traffic scenario name (e.g. ``"moderate"``).
    policy_name : str
        Policy identifier (e.g. ``"no_warming"``).
    seed : int
        Random seed used for the trace.

    Returns
    -------
    dict[str, Any]
        Flat dictionary suitable for ``csv.DictWriter`` or ``pd.DataFrame``.
    """
    row: dict[str, Any] = {
        "scenario": scenario,
        "policy": policy_name,
        "seed": seed,
    }
    row.update(metrics)
    return row


def compute_burst_metrics(
    result: SimResult,
    cfg: SimConfig,
    burst_factor: float = 3.0,
    slo_s: float = 0.5,
) -> dict[str, Any]:
    """Compute latency and capacity metrics focused on detected burst intervals."""
    completed = [
        request for request in result.requests
        if not request.dropped and request.latency_s is not None
    ]
    slo_rate = (
        sum(1 for request in completed if request.latency_s > slo_s) / len(completed)
        if completed else 0.0
    )
    intervals = list(result.intervals)
    rates = [
        record.observed_requests / (record.t_end - record.t_start)
        if record.t_end > record.t_start else 0.0
        for record in intervals
    ]
    median_rate = float(np.median(rates)) if rates else 0.0
    burst_flags = [
        rate > burst_factor * median_rate
        for rate in rates
    ]
    burst_indices = {index for index, is_burst in enumerate(burst_flags) if is_burst}
    burst_requests = [
        request for request in completed
        if any(
            record.t_start <= request.arrival_s < record.t_end
            for index, record in enumerate(intervals)
            if index in burst_indices
        )
    ]
    burst_cold_starts = sum(
        record.cold_starts for index, record in enumerate(intervals)
        if index in burst_indices
    )
    total_cold_starts = sum(record.cold_starts for record in intervals)

    p99 = (
        float(np.percentile([request.latency_s for request in burst_requests], 99))
        if burst_requests else None
    )
    episode_ratios: list[float] = []
    index = 0
    while index < len(intervals):
        if not burst_flags[index]:
            index += 1
            continue
        first = intervals[index]
        duration = first.t_end - first.t_start
        needed = math.ceil(
            first.observed_requests / duration * cfg.mean_exec_s
        ) if duration > 0 else 0
        if needed > 0:
            episode_ratios.append(min(1.0, first.ready / needed))
        index += 1
        while index < len(intervals) and burst_flags[index]:
            index += 1

    return {
        "slo_violation_rate": slo_rate,
        "burst_intervals": len(burst_indices),
        "burst_cold_starts": burst_cold_starts,
        "burst_cold_start_share": (
            burst_cold_starts / total_cold_starts if total_cold_starts else 0.0
        ),
        "burst_p99_latency_s": p99,
        "burst_ready_ratio": (
            float(np.mean(episode_ratios)) if episode_ratios else None
        ),
    }
