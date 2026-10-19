"""
Run the policy ablation benchmark across all standard scenarios.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from warmlambda.core.config import SimConfig
from warmlambda.core.metrics import compute_metrics
from warmlambda.core.policies.fixed import FixedWarming
from warmlambda.core.policies.no_warming import NoWarming
from warmlambda.core.policies.reactive import Reactive
from warmlambda.core.simulator import simulate
from warmlambda.core.traffic import SCENARIOS, generate_trace
from api.services import instantiate_policy


def main() -> None:
    """Print mean cold-start, p95 latency, and cost for each ablation."""
    policy_names = ("no_warming", "fixed_5", "reactive", "wl_forecast_only", "wl_full")
    aggregates: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for scenario in SCENARIOS:
        for seed in range(5):
            cfg = SimConfig()
            trace = generate_trace(scenario, cfg, seed)
            policies = {
                "no_warming": NoWarming(),
                "fixed_5": FixedWarming(5),
                "reactive": Reactive(),
            }
            for name in ("wl_forecast_only", "wl_full"):
                policies[name], _ = instantiate_policy(name, trace, cfg)
            for name, policy in policies.items():
                aggregates[(scenario, name)].append(
                    compute_metrics(simulate(trace, policy, cfg), cfg)
                )

    print("scenario | policy            | mean cold_start_rate | mean p95_latency_s | mean total_cost")
    print("---------+-------------------+----------------------+--------------------+----------------")
    for scenario in SCENARIOS:
        for policy in policy_names:
            rows = aggregates[(scenario, policy)]
            mean = lambda key: sum(float(row[key]) for row in rows) / len(rows)
            print(
                f"{scenario:9} | {policy:17} | {mean('cold_start_rate'):20.6f} | "
                f"{mean('p95_latency_s'):18.6f} | {mean('total_cost'):14.1f}"
            )


if __name__ == "__main__":
    main()
