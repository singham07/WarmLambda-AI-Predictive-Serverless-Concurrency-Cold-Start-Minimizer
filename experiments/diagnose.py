"""
Diagnosis of policy targets and instance creation.

Findings from ``moderate`` and ``high_load`` with duration 3600, seed 0:

* The old 100-second comparison was invalid for policy separation: with the
  old 300-second idle timeout, no_warming retained on-demand instances and
  matched reactive and most forecast metrics.
* With the 60-second default, targets are no longer equivalent.  On
  high_load, wl_forecast_only bootstraps one policy-created instance at t=0,
  reactive reaches non-zero targets, and wl_full creates the most proactive
  capacity.
* Policy-created instances are counted separately from on-demand instances.
  They are protected by the held target after becoming idle; no simulator
  expiry bug was found.
* Conclusion: reactive, wl_forecast_only, and wl_full all exceed the
  no_warming target at least once on both scenarios (no_warming is always 0).
"""

from __future__ import annotations

from api.services import instantiate_policy
from warmlambda.core.config import SimConfig
from warmlambda.core.metrics import compute_metrics
from warmlambda.core.simulator import simulate
from warmlambda.core.traffic import generate_trace


POLICIES = ("no_warming", "reactive", "wl_forecast_only", "wl_full")


def main() -> None:
    """Print interval-level evidence for the policy comparison."""
    cfg = SimConfig(duration_s=3600.0)
    for scenario in ("moderate", "high_load"):
        trace = generate_trace(scenario, cfg, seed=0)
        print(f"\n=== {scenario} (duration_s=3600, seed=0) ===")
        for policy_name in POLICIES:
            policy, _ = instantiate_policy(policy_name, trace, cfg)
            result = simulate(trace, policy, cfg)
            metrics = compute_metrics(result, cfg)
            print(f"\n{policy_name}")
            print("first 20 targets:", [interval.target for interval in result.intervals[:20]])
            print(
                "first 20 ready/busy:",
                [(interval.ready, interval.busy) for interval in result.intervals[:20]],
            )
            print(
                "created policy/on-demand:",
                result.policy_created_instances,
                result.on_demand_created_instances,
            )
            print("cold starts:", metrics["cold_start_count"])

        no_warming, _ = instantiate_policy("no_warming", trace, cfg)
        baseline = simulate(trace, no_warming, cfg)
        baseline_targets = [interval.target for interval in baseline.intervals]
        conclusion = []
        for policy_name in POLICIES[1:]:
            policy, _ = instantiate_policy(policy_name, trace, cfg)
            result = simulate(trace, policy, cfg)
            exceeds = any(
                interval.target > baseline_targets[index]
                for index, interval in enumerate(result.intervals)
            )
            conclusion.append(f"{policy_name}={'yes' if exceeds else 'no'}")
        print("Conclusion: targets exceed no_warming at least once? " + ", ".join(conclusion))


if __name__ == "__main__":
    main()
