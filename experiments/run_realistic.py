"""Evaluate WarmLambda on predictable traffic with scale-to-zero settings.

The 10-second idle timeout models a scale-to-zero platform rather than a
long-lived on-demand warm pool. Seasonal runs use the scenario's known cycle
as an explicit experiment assumption: 600 seconds for scheduled bursts and
1800 seconds for the compressed daily cycle.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import numpy as np

from backend.api.services import instantiate_policy
from backend.warmlambda.core.config import SimConfig
from backend.warmlambda.core.metrics import compute_burst_metrics, compute_metrics
from backend.warmlambda.core.simulator import simulate
from backend.warmlambda.core.traffic import generate_trace


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
SEEDS = range(20)
SCENARIO_PERIODS = {"scheduled_bursts": 600.0, "daily_cycle": 1800.0}
POLICY_SPECS = [
    ("no_warming", "no_warming", None, None),
    ("fixed_1", "fixed", 1, None),
    ("fixed_5", "fixed", 5, None),
    ("fixed_10", "fixed", 10, None),
    ("reactive", "reactive", None, None),
    ("wl_forecast_only_seasonal", "wl_forecast_only", None, "seasonal"),
    ("wl_littles_law_seasonal", "wl_littles_law", None, "seasonal"),
    ("wl_quantile_forecast_only_seasonal", "wl_quantile_forecast_only", None, "seasonal"),
    ("wl_quantile_full_seasonal", "wl_quantile_full", None, "seasonal"),
    ("wl_full_seasonal", "wl_full", None, "seasonal"),
    ("wl_full_ewma", "wl_full", None, "ewma"),
    ("oracle", "oracle", None, None),
]
METRIC_NAMES = (
    "cold_start_count", "cold_start_rate", "burst_cold_starts",
    "burst_p99_latency_s", "slo_violation_rate", "burst_ready_ratio",
    "total_cost", "utilization",
)


def _run(
    scenario: str,
    seed: int,
    policy_name: str,
    policy_type: str,
    fixed_n: int | None,
    model: str | None,
    headroom: float = 0.5,
) -> dict[str, Any]:
    cfg = SimConfig(
        duration_s=3600.0, idle_timeout_s=10.0, init_time_s=1.0,
        mean_exec_s=0.2,
    )
    trace = generate_trace(scenario, cfg, seed)
    policy, _ = instantiate_policy(
        policy_name=policy_type,
        trace=trace,
        cfg=cfg,
        fixed_n=fixed_n,
        headroom=headroom,
        warm_budget=None,
        model=model or "ewma",
        seasonal_period_s=SCENARIO_PERIODS.get(scenario),
    )
    result = simulate(trace, policy, cfg)
    metrics = compute_metrics(result, cfg)
    metrics.update(compute_burst_metrics(result, cfg))
    metrics["policy"] = policy_name
    metrics["scenario"] = scenario
    metrics["seed"] = seed
    return metrics


def _mean_std(rows: list[dict[str, Any]], key: str) -> tuple[float, float]:
    values = [
        float(row[key]) for row in rows
        if row.get(key) is not None
        and not (isinstance(row[key], float) and math.isnan(row[key]))
    ]
    return (float(np.mean(values)), float(np.std(values))) if values else (float("nan"), float("nan"))


def _write_summary(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Realistic scale-to-zero evaluation",
        "",
        "The 10-second idle timeout models scale-to-zero platforms. Seasonal "
        "forecasting is given the known scenario cycle (600 s or 1800 s). "
        "The Oracle uses future trace data and instantaneous provisioning; it "
        "is an unattainable upper bound, not a deployable policy.",
        "",
    ]
    for scenario in SCENARIO_PERIODS:
        lines.extend([f"## {scenario}", "", "| Policy | " + " | ".join(
            f"{name} mean ± std" for name in METRIC_NAMES
        ) + " |", "|---|" + "|".join(["---"] * len(METRIC_NAMES)) + "|"])
        for policy in dict.fromkeys(row["policy"] for row in rows if row["scenario"] == scenario):
            policy_rows = [row for row in rows if row["scenario"] == scenario and row["policy"] == policy]
            cells = []
            for name in METRIC_NAMES:
                mean, std = _mean_std(policy_rows, name)
                cells.append("nan" if math.isnan(mean) else f"{mean:.4f} ± {std:.4f}")
            lines.append("| " + policy + " | " + " | ".join(cells) + " |")
        scenario_rows = [row for row in rows if row["scenario"] == scenario]
        grouped = {
            policy: [row for row in scenario_rows if row["policy"] == policy]
            for policy in dict.fromkeys(row["policy"] for row in scenario_rows)
        }
        burst_means = {policy: _mean_std(items, "burst_cold_starts")[0] for policy, items in grouped.items()}
        costs = {policy: _mean_std(items, "total_cost")[0] for policy, items in grouped.items()}
        winner = min(burst_means, key=burst_means.get)
        baseline_cost = costs["no_warming"]
        fixed_cost = costs["fixed_10"]
        full_policy = "wl_full_seasonal"
        avoided = burst_means["fixed_10"] - burst_means[full_policy]
        cost_per_avoided = (costs[full_policy] - fixed_cost) / avoided if avoided > 0 else float("nan")
        lines.extend([
            "",
            "### Findings",
            f"- Fewest burst cold starts: **{winner}** ({burst_means[winner]:.2f} mean).",
            f"- Cost difference versus no_warming: {costs[winner] - baseline_cost:.2f} units.",
            f"- Cost per avoided burst cold start for {full_policy} versus fixed_10: "
            f"{cost_per_avoided:.2f} units." if not math.isnan(cost_per_avoided)
            else f"- Cost per avoided burst cold start for {full_policy} versus fixed_10: not applicable.",
        ])
        full = burst_means.get("wl_full_seasonal", float("inf"))
        if full >= burst_means["no_warming"] or costs.get("wl_full_seasonal", float("inf")) > baseline_cost * 1.25:
            lines.append("- wl_full does not beat no_warming on burst cold starts at comparable cost.")
        else:
            lines.append("- wl_full beats no_warming on burst cold starts at comparable cost.")
        lines.append("")
    return "\n".join(lines)


def _pareto(rows: list[dict[str, Any]], scenario: str) -> None:
    import matplotlib.pyplot as plt

    settings = [0.0, 0.25, 0.5, 1.0, 2.0]
    for setting in settings:
        values = [_run(scenario, seed, f"wl_full_seasonal_h{setting}", "wl_full", None, "seasonal", setting)
                  for seed in SEEDS]
        rows.append({
            "scenario": scenario, "policy": "wl_full_seasonal",
            "setting": setting,
            "mean_total_cost": _mean_std(values, "total_cost")[0],
            "mean_cold_starts": _mean_std(values, "cold_start_count")[0],
            "mean_burst_p99_latency_s": _mean_std(values, "burst_p99_latency_s")[0],
        })
    for setting in [0, 1, 2, 5, 10, 20]:
        values = [_run(scenario, seed, f"fixed_{setting}", "fixed", setting, None)
                  for seed in SEEDS]
        rows.append({
            "scenario": scenario, "policy": "fixed",
            "setting": setting,
            "mean_total_cost": _mean_std(values, "total_cost")[0],
            "mean_cold_starts": _mean_std(values, "cold_start_count")[0],
            "mean_burst_p99_latency_s": _mean_std(values, "burst_p99_latency_s")[0],
        })

    figure_rows = [row for row in rows if row["scenario"] == scenario]
    for family, color in (("wl_full_seasonal", "#f0a23b"), ("fixed", "#4cb5d6")):
        points = [row for row in figure_rows if row["policy"] == family]
        points.sort(key=lambda row: row["mean_total_cost"])
        plt.plot([row["mean_total_cost"] for row in points],
                 [row["mean_cold_starts"] for row in points],
                 marker="o", label=family, color=color)
    plt.xlabel("Mean total cost")
    plt.ylabel("Mean cold starts")
    plt.title(f"Pareto sweep: {scenario}")
    plt.legend()
    plt.tight_layout()
    (RESULTS / "figures").mkdir(parents=True, exist_ok=True)
    plt.savefig(RESULTS / "figures" / f"pareto_{scenario}.png", dpi=150)
    plt.close()


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    rows: list[dict[str, Any]] = []
    for scenario in SCENARIO_PERIODS:
        for seed in SEEDS:
            for policy_name, policy_type, fixed_n, model in POLICY_SPECS:
                rows.append(_run(scenario, seed, policy_name, policy_type, fixed_n, model))
    with open(RESULTS / "realistic.csv", "w", newline="", encoding="utf-8") as handle:
        fieldnames = ["scenario", "policy", "seed"] + sorted(
            key for key in rows[0] if key not in {"scenario", "policy", "seed"}
        )
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    summary = _write_summary(rows)
    (RESULTS / "realistic_summary.md").write_text(summary + "\n", encoding="utf-8")
    pareto_rows: list[dict[str, Any]] = []
    for scenario in SCENARIO_PERIODS:
        _pareto(pareto_rows, scenario)
    with open(RESULTS / "pareto.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "scenario", "policy", "setting", "mean_total_cost",
            "mean_cold_starts", "mean_burst_p99_latency_s",
        ])
        writer.writeheader()
        writer.writerows(pareto_rows)
    findings = "\n".join(line for line in summary.splitlines() if line.startswith("- "))
    print("Findings")
    print(findings)


if __name__ == "__main__":
    main()
