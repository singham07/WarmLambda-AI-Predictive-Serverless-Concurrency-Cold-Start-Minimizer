"""
tests.test_policies
===================
Tests for the baseline policies.
"""

from __future__ import annotations

import math

import pytest

from backend.api.services import instantiate_policy
from backend.warmlambda.core.config import SimConfig
from backend.warmlambda.core.policies.base import Policy, SimState, TrafficHistory
from backend.warmlambda.core.policies.fixed import FixedWarming
from backend.warmlambda.core.policies.no_warming import NoWarming
from backend.warmlambda.core.policies.oracle import Oracle
from backend.warmlambda.core.policies.reactive import Reactive
from backend.warmlambda.core.simulator import simulate
from backend.warmlambda.core.traffic import Request, generate_trace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(**overrides) -> SimConfig:
    """Return a SimConfig with sensible test defaults."""
    defaults = dict(
        duration_s=100.0,
        init_time_s=1.0,
        mean_exec_s=0.2,
        exec_sigma=0.5,
        idle_timeout_s=300.0,
        max_instances=100,
        concurrency_per_instance=1,
        queue_timeout_s=10.0,
        decision_interval_s=20.0,
    )
    defaults.update(overrides)
    return SimConfig(**defaults)


def _hist(**overrides) -> TrafficHistory:
    defaults = dict(window_s=20.0, counts=[], now=0.0)
    defaults.update(overrides)
    return TrafficHistory(**defaults)


def _state(**overrides) -> SimState:
    defaults = dict(
        now=0.0,
        ready_instances=0,
        busy_instances=0,
        initializing_instances=0,
        queue_length=0,
        held_target=0,
    )
    defaults.update(overrides)
    return SimState(**defaults)


# ---------------------------------------------------------------------------
# FixedWarming tests
# ---------------------------------------------------------------------------


class TestFixedWarming:
    """FixedWarming always returns the constant n."""

    @pytest.mark.parametrize("n", [0, 1, 5, 10, 20])
    def test_returns_n(self, n: int) -> None:
        policy = FixedWarming(n)
        assert policy.name == f"fixed_{n}"
        h = _hist()
        s = _state()
        assert policy.decide(h, s) == n


# ---------------------------------------------------------------------------
# Reactive tests
# ---------------------------------------------------------------------------


class TestReactive:
    """Reactive scales with busy+queue, respects max_step and cooldown."""

    def test_increases_when_load_grows(self) -> None:
        policy = Reactive(margin=0.0, max_step=100, cooldown_windows=0)
        h = _hist()
        # busy=2, queue=0 -> desired=2
        s = _state(busy_instances=2, queue_length=0, held_target=0)
        assert policy.decide(h, s) == 2

        # busy=5, queue=3 -> desired=8, step limit allows jump from 2 to 8
        s = _state(busy_instances=5, queue_length=3, held_target=2)
        assert policy.decide(h, s) == 8

    def test_respects_max_step(self) -> None:
        policy = Reactive(margin=0.0, max_step=3, cooldown_windows=0)
        h = _hist()
        # held=0, desired=10 -> step limit caps at 3
        s = _state(busy_instances=10, queue_length=0, held_target=0)
        assert policy.decide(h, s) == 3

    def test_respects_cooldown_on_scale_down(self) -> None:
        # margin=0, max_step large, cooldown=2
        policy = Reactive(margin=0.0, max_step=100, cooldown_windows=2)
        h = _hist()

        # Scale up from 0 to 5
        s = _state(busy_instances=5, queue_length=0, held_target=0)
        assert policy.decide(h, s) == 5
        # Cooldown should be active now

        # Next window: load drops to 0, but cooldown prevents scale-down
        s = _state(busy_instances=0, queue_length=0, held_target=5)
        assert policy.decide(h, s) == 5  # cooldown active, cannot scale down

        # Next window: cooldown expired, can scale down
        s = _state(busy_instances=0, queue_length=0, held_target=5)
        assert policy.decide(h, s) == 0


# ---------------------------------------------------------------------------
# Cold-start monotonicity test (same trace, increasing fixed n)
# ---------------------------------------------------------------------------


class TestFixedMonotonicity:
    """Cold starts should not increase as fixed n increases on the same trace.

    This test generates ONE trace and runs it through FixedWarming for
    n in [0, 1, 2, 5, 10, 20]. Cold start count should be non-increasing.
    If violated, we explain why in a comment and report it.
    """

    def test_cold_starts_non_increasing(self) -> None:
        cfg = _cfg(duration_s=100.0, decision_interval_s=20.0)
        trace = generate_trace("moderate", cfg, seed=42)

        prev_cold = None
        violations: list[tuple[int, int]] = []  # (n, cold_count)

        counts: dict[int, int] = {}
        for n in [0, 1, 2, 5, 10, 20]:
            policy = FixedWarming(n)
            result = simulate(trace, policy, cfg)
            cold_count = sum(1 for r in result.requests if r.cold and not r.dropped)
            counts[n] = cold_count

            if prev_cold is not None and cold_count > prev_cold:
                violations.append((n, cold_count))
            prev_cold = cold_count

        if violations:
            # Report violations with explanation
            print("\n=== COLD START MONOTONICITY VIOLATIONS ===")
            for n, cold in violations:
                print(f"  FixedWarming({n}): {cold} cold starts")
            print("EXPLANATION:")
            print("  Cold starts can theoretically increase with larger n due to")
            print("  race conditions: proactive instances may steal requests that")
            print("  would have warmed an existing instance, leaving it idle and")
            print("  causing it to expire before the next burst. This is a known")
            print("  artifact of discrete-event simulation with concurrent init.")
            pytest.fail(f"Monotonicity violated for {violations}")

        # If we get here, monotonicity held
        print("  Cold start counts:", counts)


# ---------------------------------------------------------------------------
# Oracle test (sanity check)
# ---------------------------------------------------------------------------


class TestOracle:
    """Oracle cheats by looking at future."""

    def test_name_and_decide(self) -> None:
        cfg = _cfg()
        trace = [Request(id=0, arrival_s=10.0, exec_s=0.5)]
        oracle = Oracle(trace, cfg)
        assert oracle.name == "oracle"
        h = _hist()
        s = _state(now=5.0)  # before the arrival at t=10
        target = oracle.decide(h, s)
        assert target >= 0
        assert target == 1

    def test_decide_after_arrival(self) -> None:
        cfg = _cfg()
        trace = [Request(id=0, arrival_s=10.0, exec_s=0.5)]
        oracle = Oracle(trace, cfg)
        h = _hist()
        s = _state(now=15.0)  # after the arrival
        target = oracle.decide(h, s)
        assert target == 0

    def test_target_is_next_interval_peak_concurrent_capacity(self) -> None:
        cfg = _cfg(
            duration_s=20.0,
            decision_interval_s=5.0,
        )
        trace = [
            Request(0, 0.1, 4.9),
            Request(1, 0.2, 4.8),
            Request(2, 7.0, 1.0),
        ]
        oracle = Oracle(trace, cfg)
        assert oracle.decide(_hist(), _state(now=0.0)) == 2
        assert oracle.decide(_hist(), _state(now=5.0)) == 1

    def test_unaligned_interval_includes_demand_already_active_at_start(self) -> None:
        cfg = _cfg(duration_s=20.0, decision_interval_s=5.0)
        trace = [Request(0, 1.0, 5.0)]
        oracle = Oracle(trace, cfg)
        assert oracle.decide(_hist(), _state(now=3.0)) == 1

    def test_unaligned_interval_excludes_demand_ending_at_start(self) -> None:
        cfg = _cfg(duration_s=20.0, decision_interval_s=5.0)
        trace = [Request(0, 1.0, 2.0)]
        oracle = Oracle(trace, cfg)
        assert oracle.decide(_hist(), _state(now=3.0)) == 0

    def test_oracle_has_no_more_cold_starts_than_causal_policies(self) -> None:
        cfg = _cfg(
            duration_s=20.0,
            decision_interval_s=5.0,
            init_time_s=1.0,
            idle_timeout_s=30.0,
        )
        trace = [
            Request(0, 0.5, 2.0),
            Request(1, 0.7, 1.0),
            Request(2, 7.0, 2.0),
            Request(3, 7.3, 1.0),
        ]
        oracle_result = simulate(trace, Oracle(trace, cfg), cfg)
        oracle_cold_starts = sum(
            request.cold and not request.dropped for request in oracle_result.requests
        )

        causal_policy_names = (
            "no_warming",
            "fixed",
            "reactive",
            "wl_forecast_only",
            "wl_correction_only",
            "wl_full",
            "wl_littles_law",
            "wl_quantile_forecast_only",
            "wl_quantile_full",
        )
        for policy_name in causal_policy_names:
            policy, _ = instantiate_policy(
                policy_name,
                trace,
                cfg,
                fixed_n=2,
                model="ewma",
            )
            result = simulate(trace, policy, cfg)
            cold_starts = sum(
                request.cold and not request.dropped for request in result.requests
            )
            assert oracle_cold_starts <= cold_starts, policy_name

        assert oracle_cold_starts == 0