"""
api.services
============
Simulation execution, policy orchestration, interval downsampling,
and summary aggregation services for the WarmLambda AI API.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import HTTPException

from api.schemas import CompareRequest, IntervalPoint, RunRequest
from warmlambda.core.capacity import capacity_from_rate
from warmlambda.core.config import SimConfig
from warmlambda.core.forecaster import EWMAForecaster
from warmlambda.core.metrics import compute_metrics
from warmlambda.core.policies.base import Policy, SimState, TrafficHistory
from warmlambda.core.policies.fixed import FixedWarming
from warmlambda.core.policies.no_warming import NoWarming
from warmlambda.core.policies.oracle import Oracle
from warmlambda.core.policies.reactive import Reactive
from warmlambda.core.simulator import SimResult, simulate
from warmlambda.core.traffic import Request, generate_trace


class WarmLambdaHybridPolicy(Policy):
    """Proactive and/or reactive WarmLambda policy variant.

    Supports:
    - 'wl_forecast_only': Little's Law on EWMA arrival rate forecast.
    - 'wl_correction_only': Headroom applied reactively to current busy+queue load.
    - 'wl_full': Max of proactive forecast capacity and reactive concurrency load.
    """

    def __init__(
        self,
        mode: str,
        cfg: SimConfig,
        headroom: float = 0.5,
        warm_budget: Optional[int] = None,
    ) -> None:
        self.mode = mode
        self.cfg = cfg
        self.headroom = float(headroom)
        self.warm_budget = warm_budget
        self.name = mode
        self.forecaster = EWMAForecaster(alpha=0.4)
        self.forecast_history: dict[float, float] = {}

    def decide(self, history: TrafficHistory, state: SimState) -> int:
        rate = self.forecaster.predict(history.counts, history.window_s)
        self.forecast_history[history.now] = rate

        if self.mode == "wl_forecast_only":
            target = capacity_from_rate(
                rate=rate,
                mean_exec_s=self.cfg.mean_exec_s,
                headroom=self.headroom,
                max_instances=self.cfg.max_instances,
            )
        elif self.mode == "wl_correction_only":
            curr_load = state.busy_instances + state.queue_length
            target = math.ceil(curr_load * (1.0 + self.headroom))
        else:  # wl_full
            cap_forecast = capacity_from_rate(
                rate=rate,
                mean_exec_s=self.cfg.mean_exec_s,
                headroom=self.headroom,
                max_instances=self.cfg.max_instances,
            )
            curr_load = state.busy_instances + state.queue_length
            cap_corr = math.ceil(curr_load * (1.0 + self.headroom))
            target = max(cap_forecast, cap_corr)

        if self.warm_budget is not None:
            target = min(target, self.warm_budget)

        return max(0, min(self.cfg.max_instances, target))


def build_config(req: RunRequest | CompareRequest) -> SimConfig:
    """Build a SimConfig applying any requested overrides."""
    kwargs: dict[str, Any] = {}
    if req.init_time_s is not None:
        kwargs["init_time_s"] = req.init_time_s
    if req.mean_exec_s is not None:
        kwargs["mean_exec_s"] = req.mean_exec_s
    if req.duration_s is not None:
        kwargs["duration_s"] = req.duration_s
    if req.idle_timeout_s is not None:
        kwargs["idle_timeout_s"] = req.idle_timeout_s
    if req.max_instances is not None:
        kwargs["max_instances"] = req.max_instances

    return SimConfig(**kwargs)


def instantiate_policy(
    policy_name: str,
    trace: list[Request],
    cfg: SimConfig,
    fixed_n: Optional[int] = 5,
    headroom: float = 0.5,
    warm_budget: Optional[int] = None,
) -> tuple[Policy, Optional[dict[float, float]]]:
    """Create a policy instance and optionally return its forecast tracker."""
    forecast_tracker: Optional[dict[float, float]] = None

    if policy_name == "no_warming":
        policy = NoWarming()
    elif policy_name == "fixed":
        n = fixed_n if fixed_n is not None else 5
        policy = FixedWarming(n=n)
    elif policy_name == "reactive":
        policy = Reactive()
    elif policy_name in ("wl_forecast_only", "wl_correction_only", "wl_full"):
        p = WarmLambdaHybridPolicy(
            mode=policy_name,
            cfg=cfg,
            headroom=headroom,
            warm_budget=warm_budget,
        )
        forecast_tracker = p.forecast_history
        policy = p
    elif policy_name == "oracle":
        policy = Oracle(trace=trace, cfg=cfg)
    else:
        raise ValueError(f"Unsupported policy type: '{policy_name}'")

    return policy, forecast_tracker


def sanitize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Replace float NaN with None for valid JSON serialization."""
    sanitized: dict[str, Any] = {}
    for k, v in metrics.items():
        if isinstance(v, float) and math.isnan(v):
            sanitized[k] = None
        else:
            sanitized[k] = v
    return sanitized


def downsample_intervals(
    raw_intervals: list[Any],
    forecast_tracker: Optional[dict[float, float]],
    max_points: int = 500,
) -> list[IntervalPoint]:
    """Convert IntervalRecords to IntervalPoint models downsampled to max_points."""
    points: list[IntervalPoint] = []
    for rec in raw_intervals:
        fc_rate = forecast_tracker.get(rec.t) if forecast_tracker else None
        points.append(
            IntervalPoint(
                t=rec.t,
                arrivals_in_window=rec.arrivals_in_window,
                forecast_rate=fc_rate,
                target=rec.target,
                ready=rec.ready,
                busy=rec.busy,
                queue_length=rec.queue_length,
            )
        )

    if len(points) <= max_points:
        return points

    step = (len(points) - 1) / (max_points - 1)
    sampled_indices = {int(round(i * step)) for i in range(max_points)}
    sampled_indices.add(len(points) - 1)
    sorted_indices = sorted(sampled_indices)
    return [points[i] for i in sorted_indices]


def run_single_simulation(req: RunRequest) -> dict[str, Any]:
    """Run one simulation scenario and return config, metrics, and intervals."""
    cfg = build_config(req)
    trace = generate_trace(req.scenario, cfg, req.seed)

    policy, forecast_tracker = instantiate_policy(
        policy_name=req.policy,
        trace=trace,
        cfg=cfg,
        fixed_n=req.fixed_n,
        headroom=req.headroom,
        warm_budget=req.warm_budget,
    )

    result = simulate(trace, policy, cfg)
    raw_metrics = compute_metrics(result, cfg)
    metrics = sanitize_metrics(raw_metrics)

    intervals = downsample_intervals(
        raw_intervals=result.intervals,
        forecast_tracker=forecast_tracker,
        max_points=500,
    )

    config_dict = {
        "duration_s": cfg.duration_s,
        "init_time_s": cfg.init_time_s,
        "mean_exec_s": cfg.mean_exec_s,
        "idle_timeout_s": cfg.idle_timeout_s,
        "max_instances": cfg.max_instances,
        "concurrency_per_instance": cfg.concurrency_per_instance,
        "decision_interval_s": cfg.decision_interval_s,
        "warm_cost_weight": cfg.warm_cost_weight,
        "busy_cost_weight": cfg.busy_cost_weight,
    }

    return {
        "config": config_dict,
        "metrics": metrics,
        "intervals": intervals,
    }


def run_comparison(req: CompareRequest) -> dict[str, Any]:
    """Run multiple policies on the exact same trace and compare metrics."""
    cfg = build_config(req)
    trace = generate_trace(req.scenario, cfg, req.seed)

    results: dict[str, Any] = {}

    for pol_name in req.policies:
        policy, forecast_tracker = instantiate_policy(
            policy_name=pol_name,
            trace=trace,
            cfg=cfg,
            fixed_n=req.fixed_n,
            headroom=req.headroom,
            warm_budget=req.warm_budget,
        )

        result = simulate(trace, policy, cfg)
        raw_metrics = compute_metrics(result, cfg)
        metrics = sanitize_metrics(raw_metrics)

        intervals = downsample_intervals(
            raw_intervals=result.intervals,
            forecast_tracker=forecast_tracker,
            max_points=500,
        )

        results[pol_name] = {
            "metrics": metrics,
            "intervals": intervals,
        }

    return {
        "scenario": req.scenario,
        "seed": req.seed,
        "results": results,
    }


def get_results_summary() -> dict[str, Any]:
    """Aggregate results/final_metrics.csv by scenario and policy (mean, std)."""
    csv_path = Path(__file__).resolve().parents[1] / "results" / "final_metrics.csv"
    if not csv_path.exists():
        raise HTTPException(
            status_code=404,
            detail="results/final_metrics.csv not found",
        )

    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read results/final_metrics.csv: {exc}",
        )

    required_cols = {"scenario", "policy"}
    if not required_cols.issubset(df.columns):
        raise HTTPException(
            status_code=500,
            detail="CSV missing required 'scenario' or 'policy' columns",
        )

    # Metric columns to aggregate
    candidate_metrics = [
        "cold_start_rate",
        "total_cost",
        "utilization",
        "mean_latency_s",
        "p50_latency_s",
        "p95_latency_s",
        "p99_latency_s",
        "dropped_rate",
    ]
    numeric_cols = [c for c in candidate_metrics if c in df.columns]

    agg_df = df.groupby(["scenario", "policy"])[numeric_cols].agg(["mean", "std"])

    summary_tree: dict[str, dict[str, dict[str, Any]]] = {}
    for (scenario, policy), row in agg_df.iterrows():
        sc = str(scenario)
        pol = str(policy)
        if sc not in summary_tree:
            summary_tree[sc] = {}
        summary_tree[sc][pol] = {}
        for col in numeric_cols:
            mean_val = row[(col, "mean")]
            std_val = row[(col, "std")]
            summary_tree[sc][pol][col] = {
                "mean": None if pd.isna(mean_val) else float(mean_val),
                "std": None if pd.isna(std_val) else float(std_val),
            }

    return summary_tree
