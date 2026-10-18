"""
experiments.eval_forecasters
============================
Evaluate traffic rate forecasters across all scenarios and seeds.

Compares:
- EWMA with alpha in {0.2, 0.4, 0.7}
- EWMA with Holt's linear trend (alpha=0.4, beta=0.2)
- SeasonalNaive (period_windows=30 for 600 s period on 20 s window)
- LastValue baseline

Saves results to results/forecast_eval.csv and prints summary pivot tables.
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from warmlambda.core.config import SimConfig
from warmlambda.core.forecaster import (
    EWMAForecaster,
    Forecaster,
    LastValueForecaster,
    SeasonalNaiveForecaster,
    evaluate_forecaster,
)
from warmlambda.core.traffic import SCENARIOS, generate_trace


def _format_table(header: list[str], rows: list[list[str]]) -> str:
    """Format tabular rows into an aligned text table."""
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
    out_csv = results_dir / "forecast_eval.csv"

    window_s = 20.0
    seeds = range(5)  # 0..4

    forecaster_factories: list[tuple[str, type[Forecaster], dict[str, Any]]] = [
        ("ewma_a0.2", EWMAForecaster, {"alpha": 0.2}),
        ("ewma_a0.4", EWMAForecaster, {"alpha": 0.4}),
        ("ewma_a0.7", EWMAForecaster, {"alpha": 0.7}),
        ("ewma_trend_a0.4_b0.2", EWMAForecaster, {"alpha": 0.4, "trend": True, "beta": 0.2}),
        ("seasonal_naive_p30", SeasonalNaiveForecaster, {"period_windows": 30}),
        ("last_value", LastValueForecaster, {}),
    ]

    forecaster_names = [name for name, _, _ in forecaster_factories]
    rows: list[dict[str, Any]] = []

    print("[eval_forecasters] Evaluating forecasters across scenarios and seeds...")

    for scenario_name in SCENARIOS:
        for seed in seeds:
            cfg = SimConfig()  # defaults: 3600s
            trace = generate_trace(scenario_name, cfg, seed)

            for name, factory, kwargs in forecaster_factories:
                forecaster = factory(**kwargs)
                metrics = evaluate_forecaster(trace, cfg, forecaster, window_s=window_s)
                rows.append({
                    "scenario": scenario_name,
                    "seed": seed,
                    "forecaster": name,
                    "mae": metrics["mae"],
                    "smape": metrics["smape"],
                })

    # Write CSV
    fieldnames = ["scenario", "seed", "forecaster", "mae", "smape"]
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[eval_forecasters] Wrote {len(rows)} rows to {out_csv}")

    # Compute means per (scenario, forecaster)
    mae_sum: dict[tuple[str, str], float] = defaultdict(float)
    smape_sum: dict[tuple[str, str], float] = defaultdict(float)
    count: dict[tuple[str, str], int] = defaultdict(int)

    for r in rows:
        key = (r["scenario"], r["forecaster"])
        mae_sum[key] += r["mae"]
        smape_sum[key] += r["smape"]
        count[key] += 1

    all_scenarios = list(SCENARIOS.keys())

    # 1. MAE Table
    print("\n=== Mean MAE (req/s) by Scenario and Forecaster ===")
    header = ["scenario"] + forecaster_names
    mae_rows = []
    best_per_scenario: dict[str, tuple[str, float]] = {}

    for sc in all_scenarios:
        row = [sc]
        best_name = ""
        best_val = float("inf")
        for f_name in forecaster_names:
            cnt = count.get((sc, f_name), 0)
            if cnt > 0:
                v = mae_sum[(sc, f_name)] / cnt
                row.append(f"{v:.4f}")
                if v < best_val:
                    best_val = v
                    best_name = f_name
            else:
                row.append("nan")
        best_per_scenario[sc] = (best_name, best_val)
        mae_rows.append(row)
    print(_format_table(header, mae_rows))

    # 2. sMAPE Table
    print("\n=== Mean sMAPE by Scenario and Forecaster ===")
    smape_rows = []
    for sc in all_scenarios:
        row = [sc]
        for f_name in forecaster_names:
            cnt = count.get((sc, f_name), 0)
            if cnt > 0:
                v = smape_sum[(sc, f_name)] / cnt
                row.append(f"{v:.4f}")
            else:
                row.append("nan")
        smape_rows.append(row)
    print(_format_table(header, smape_rows))

    # 3. Best Forecaster per Scenario
    print("\n=== Best Forecaster per Scenario (Lowest Mean MAE) ===")
    best_header = ["scenario", "best_forecaster", "min_mean_mae"]
    best_rows = [
        [sc, best_per_scenario[sc][0], f"{best_per_scenario[sc][1]:.4f}"]
        for sc in all_scenarios
    ]
    print(_format_table(best_header, best_rows))


if __name__ == "__main__":
    main()
