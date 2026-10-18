"""
experiments.run_baselines
=========================
Run the baseline policies and oracle across all scenarios and seeds.
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from warmlambda.core.config import SimConfig
from warmlambda.core.metrics import compute_metrics, metrics_to_row
from warmlambda.core.policies.fixed import FixedWarming
from warmlambda.core.policies.no_warming import NoWarming
from warmlambda.core.policies.oracle import Oracle
from warmlambda.core.policies.reactive import Reactive
from warmlambda.core.simulator import simulate
from warmlambda.core.traffic import SCENARIOS, generate_trace


def _format_table(header: list[str], rows: list[list[str]]) -> str:
    """Format tabular data into an aligned, easy-to-read text table."""
    col_widths = [len(h) for h in header]
    for row in rows:
        for idx, cell in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(cell))

    lines = []
    # Header line
    lines.append(" | ".join(h.ljust(col_widths[i]) for i, h in enumerate(header)))
    # Separator line
    lines.append("-+-".join("-" * col_widths[i] for i in range(len(header))))
    # Data rows
    for row in rows:
        lines.append(" | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)


def main() -> None:
    """Run baselines and write CSV + print pivot."""
    results_dir = Path(__file__).resolve().parents[1] / "results"
    results_dir.mkdir(exist_ok=True)

    out_csv = results_dir / "baselines.csv"
    fieldnames: list[str] = []

    ordered_policy_names = [
        "no_warming",
        "fixed_1",
        "fixed_2",
        "fixed_5",
        "fixed_10",
        "fixed_20",
        "reactive",
        "oracle",
    ]

    seeds = range(5)  # 0..4
    rows: list[dict[str, Any]] = []

    print("[run_baselines] Starting simulation across scenarios and seeds...")

    for scenario_name in SCENARIOS:
        for seed in seeds:
            cfg = SimConfig()  # default settings
            trace = generate_trace(scenario_name, cfg, seed)

            # Build fresh policy instances per trace
            policies = [
                ("no_warming", NoWarming()),
                ("fixed_1", FixedWarming(1)),
                ("fixed_2", FixedWarming(2)),
                ("fixed_5", FixedWarming(5)),
                ("fixed_10", FixedWarming(10)),
                ("fixed_20", FixedWarming(20)),
                ("reactive", Reactive()),
                ("oracle", Oracle(trace, cfg)),
            ]

            for policy_name, policy in policies:
                result = simulate(trace, policy, cfg)
                metrics = compute_metrics(result, cfg)
                row = metrics_to_row(metrics, scenario_name, policy_name, seed)
                if not fieldnames:
                    fieldnames = list(row.keys())
                rows.append(row)

    # Write CSV
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[run_baselines] Wrote {len(rows)} rows to {out_csv}")

    # ----- Aggregate & Print Pivot Tables -----
    cold_start_sum: dict[tuple[str, str], float] = defaultdict(float)
    cost_sum: dict[tuple[str, str], float] = defaultdict(float)
    count: dict[tuple[str, str], int] = defaultdict(int)

    for r in rows:
        key = (r["scenario"], r["policy"])
        cs = r.get("cold_start_rate")
        tc = r.get("total_cost")
        if isinstance(cs, (int, float)) and not (isinstance(cs, float) and math.isnan(cs)):
            cold_start_sum[key] += float(cs)
        if isinstance(tc, (int, float)) and not (isinstance(tc, float) and math.isnan(tc)):
            cost_sum[key] += float(tc)
        count[key] += 1

    all_scenarios = list(SCENARIOS.keys())

    # 1. Cold start rate pivot
    print("\n=== Mean cold_start_rate by scenario and policy ===")
    header = ["scenario"] + ordered_policy_names
    cs_rows = []
    for sc in all_scenarios:
        row = [sc]
        for pol in ordered_policy_names:
            cnt = count.get((sc, pol), 0)
            if cnt > 0:
                v = cold_start_sum[(sc, pol)] / cnt
                row.append(f"{v:.4f}")
            else:
                row.append("nan")
        cs_rows.append(row)
    print(_format_table(header, cs_rows))

    # 2. Total cost pivot
    print("\n=== Mean total_cost by scenario and policy ===")
    cost_rows = []
    for sc in all_scenarios:
        row = [sc]
        for pol in ordered_policy_names:
            cnt = count.get((sc, pol), 0)
            if cnt > 0:
                v = cost_sum[(sc, pol)] / cnt
                row.append(f"{v:.1f}")
            else:
                row.append("nan")
        cost_rows.append(row)
    print(_format_table(header, cost_rows))


if __name__ == "__main__":
    main()