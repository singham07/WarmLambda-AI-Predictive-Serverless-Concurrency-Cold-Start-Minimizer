"""Regression tests for meaningful long-run policy comparisons."""

from __future__ import annotations

from api.services import instantiate_policy
from warmlambda.core.config import SimConfig
from warmlambda.core.metrics import compute_metrics
from warmlambda.core.policies.fixed import FixedWarming
from warmlambda.core.policies.no_warming import NoWarming
from warmlambda.core.simulator import simulate
from warmlambda.core.traffic import generate_trace


def _run(scenario: str, policy_name: str):
    cfg = SimConfig(duration_s=3600.0)
    trace = generate_trace(scenario, cfg, seed=0)
    if policy_name == "fixed_5":
        policy = FixedWarming(5)
    elif policy_name == "no_warming":
        policy = NoWarming()
    else:
        policy, _ = instantiate_policy(policy_name, trace, cfg)
    result = simulate(trace, policy, cfg)
    return compute_metrics(result, cfg), result


def test_forecast_only_bootstraps_before_high_load_traffic() -> None:
    """Forecast-only creates causal bootstrap capacity before arrivals are served."""
    _, result = _run("high_load", "wl_forecast_only")
    assert result.intervals[0].t == 0.0
    assert result.intervals[0].target >= 1
    assert result.policy_created_instances >= 1


def test_wl_full_and_no_warming_differ_on_high_load() -> None:
    """The full policy must change at least one aggregate metric."""
    no_warming, _ = _run("high_load", "no_warming")
    wl_full, _ = _run("high_load", "wl_full")
    assert no_warming != wl_full


def test_no_warming_has_more_cold_starts_than_fixed_five() -> None:
    """Five fixed warm instances reduce cold starts versus on-demand only."""
    no_warming, _ = _run("high_load", "no_warming")
    fixed, _ = _run("high_load", "fixed_5")
    assert no_warming["cold_start_rate"] > fixed["cold_start_rate"]
