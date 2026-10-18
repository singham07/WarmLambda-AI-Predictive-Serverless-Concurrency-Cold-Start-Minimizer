"""
experiments.run_forecast_policy
===============================
Evaluate WarmLambdaPolicy with varying headroom against baseline policies.

Runs WarmLambda with headroom in [0.2, 0.5, 1.0] across all scenarios and seeds 0..4.
Writes results to results/forecast_policy.csv, loads results/baselines.csv, and
prints comprehensive comparison tables of cold_start_rate and total_cost per scenario.
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from warmlambda.core.config import SimConfig
from warmlambda.core.forecaster import EWMAForecaster
from warmlambda.core.metrics import compute_metrics, metrics_to_row
from warmlambda.core.policies.warmlambda import WarmLambdaPolicy
from warmlambda.core.simulator import simulate
from warmlambda.core.traffic import SCENARIOS, generate_trace


def _format_table(header: list[str], rows: list[list[str]]) -> str:
    """Format tabular data into an aligned, readable text table."""
    col_widths = [len(h) for h in header]
    for row in rows:
        for idx, cell in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(cell))

    lines = []
    lines.append(" | ".join(h.ljust(col_widths[i]) for i, h in enumerate(header)))
    lines.append("-+-".join("-" * col_widths[i] for i in range(len(header))))
    for row in rows:
        lines.append(" | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)


def main() -> None:
    results_dir = Path(__file__).resolve().parents[1] / "results"
    results_dir.mkdir(exist_ok=True)
    out_csv = results_dir / "forecast_policy.csv"
    baselines_csv = results_dir / "baselines.csv"

    headroom_levels = [0.2, 0.5, 1.0]
    seeds = range(5)  # 0..4
    forecast_rows: list[dict[str, Any]] = []
    fieldnames: list[str] = []

    print("[run_forecast_policy] Running WarmLambda simulations across scenarios and seeds...")

    for scenario_name in SCENARIOS:
        for seed in seeds:
            cfg = SimConfig()  # default settings
            trace = generate_trace(scenario_name, cfg, seed)

            for hr in headroom_levels:
                policy_name = f"warmlambda_h{hr}"
                forecaster = EWMAForecaster(alpha=0.4)
                policy = WarmLambdaPolicy(forecaster, cfg, headroom=hr, name=policy_name)

                result = simulate(trace, policy, cfg)
                metrics = compute_metrics(result, cfg)
                row = metrics_to_row(metrics, scenario_name, policy_name, seed)

                if not fieldnames:
                    fieldnames = list(row.keys())
                forecast_rows.append(row)

    # Save forecast_policy.csv
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(forecast_rows)

    print(f"[run_forecast_policy] Wrote {len(forecast_rows)} rows to {out_csv}")

    # Combine with baselines for unified reporting
    combined_rows: list[dict[str, Any]] = []

    if baselines_csv.exists():
        with open(baselines_csv, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for r in reader:
                # Convert numeric fields
                converted = dict(r)
                for key in ["cold_start_rate", "total_cost"]:
                    if key in converted and converted[key] != "":
                        try:
                            converted[key] = float(converted[key])
                        except ValueError:
                            pass
                combined_rows.append(converted)
        print(f"[run_forecast_policy] Loaded {len(combined_rows)} baseline rows from {baselines_csv}")
    else:
        print("[run_forecast_policy] Warning: baselines.csv not found, showing only forecast policy results")

    combined_rows.extend(forecast_rows)

    # Group metrics by (scenario, policy)
    cold_start_sum: dict[tuple[str, str], float] = defaultdict(float)
    cost_sum: dict[tuple[str, str], float] = defaultdict(float)
    count: dict[tuple[str, str], int] = defaultdict(int)

    for r in combined_rows:
        key = (r["scenario"], r["policy"])
        cs = r.get("cold_start_rate")
        tc = r.get("total_cost")
        if isinstance(cs, (int, float)) and not (isinstance(cs, float) and math.isnan(cs)):
            cold_start_sum[key] += float(cs)
        if isinstance(tc, (int, float)) and not (isinstance(tc, float) and math.isnan(tc)):
            cost_sum[key] += float(tc)
        count[key] += 1

    # Desired policy display order
    policy_display_order = [
        "no_warming",
        "fixed_1",
        "fixed_2",
        "fixed_5",
        "fixed_10",
        "fixed_20",
        "reactive",
        "oracle",
        "warmlambda_h0.2",
        "warmlambda_h0.5",
        "warmlambda_h1.0",
    ]

    all_scenarios = list(SCENARIOS.keys())

    print("\n" + "=" * 70)
    print("PER-SCENARIO POLICY COMPARISON: COLD START RATE & TOTAL COST")
    print("=" * 70)

    for sc in all_scenarios:
        print(f"\n--- Scenario: {sc.upper()} ---")
        header = ["Policy", "Mean Cold Start Rate", "Mean Total Cost"]
        table_rows = []

        for pol in policy_display_order:
            cnt = count.get((sc, pol), 0)
            if cnt > 0:
                mean_cs = cold_start_sum[(sc, pol)] / cnt
                mean_cost = cost_sum[(sc, pol)] / cnt
                table_rows.append([pol, f"{mean_cs:.6f}", f"{mean_cost:.1f}"])
            else:
                table_rows.append([pol, "N/A", "N/A"])

        print(_format_table(header, table_rows))


if __name__ == "__main__":
    main()
