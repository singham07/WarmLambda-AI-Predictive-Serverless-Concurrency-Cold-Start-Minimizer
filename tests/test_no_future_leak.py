"""
tests.test_no_future_leak
=========================
Prove that WarmLambdaPolicy and the simulator have zero future-data leakage.

Verification strategy
---------------------
1. Generate a realistic trace for a given scenario.
2. Run the simulation with WarmLambdaPolicy and capture interval decisions up to T.
3. Construct a modified trace where all requests arriving after T are drastically
   altered (e.g. rate doubled, large burst injected).
4. Re-run the simulation with a fresh WarmLambdaPolicy instance on the modified trace.
5. Assert that the decision at T (and all decisions prior to T) are 100 % identical.
"""

from __future__ import annotations

import math

import pytest

from scipy.stats import poisson

from backend.api.services import instantiate_policy
from backend.warmlambda.core.capacity import capacity_from_quantile, capacity_from_rate
from backend.warmlambda.core.config import SimConfig
from backend.warmlambda.core.forecaster import EWMAForecaster
from backend.warmlambda.core.policies.warmlambda import WarmLambdaPolicy
from backend.warmlambda.core.simulator import simulate
from backend.warmlambda.core.traffic import Request, generate_trace


class TestCapacityFromRate:
    """Tests for capacity_from_rate (Little's Law)."""

    def test_littles_law_calculation(self) -> None:
        # rate = 10 req/s, mean_exec_s = 0.2s -> L = 2.0
        # headroom = 0.5 -> 2.0 * 1.5 = 3.0 -> ceil = 3
        cap = capacity_from_rate(rate=10.0, mean_exec_s=0.2, headroom=0.5, max_instances=100)
        assert cap == 3

    def test_respects_max_instances(self) -> None:
        cap = capacity_from_rate(rate=1000.0, mean_exec_s=1.0, headroom=0.5, max_instances=20)
        assert cap == 20

    def test_zero_or_negative_rate(self) -> None:
        assert capacity_from_rate(rate=0.0, mean_exec_s=0.2, headroom=0.5, max_instances=100) == 0
        assert capacity_from_rate(rate=-5.0, mean_exec_s=0.2, headroom=0.5, max_instances=100) == 0


class TestCapacityFromQuantile:
    def test_chooses_smallest_capacity_for_requested_tail_probability(self) -> None:
        target = capacity_from_quantile(
            rate=10.0,
            mean_exec_s=0.2,
            max_instances=100,
            epsilon=0.05,
        )
        assert target == 5
        assert poisson.sf(target, 2.0) <= 0.05
        assert poisson.sf(target - 1, 2.0) > 0.05

    def test_respects_instance_cap_and_lead_time(self) -> None:
        assert capacity_from_quantile(1000.0, 1.0, 3) == 3
        assert capacity_from_quantile(
            10.0, 0.2, 100, lead_time_s=0.1
        ) == 3

    @pytest.mark.parametrize("epsilon", [0.0, 1.0, -0.1])
    def test_invalid_epsilon_raises(self, epsilon: float) -> None:
        with pytest.raises(ValueError, match="epsilon"):
            capacity_from_quantile(10.0, 0.2, 100, epsilon=epsilon)


class TestNoFutureDataLeakage:
    """Proves no future information leaks into decisions at or before T."""

    @pytest.mark.parametrize("scenario", ["moderate", "periodic"])
    def test_decisions_identical_when_future_changes(self, scenario: str) -> None:
        cfg = SimConfig(duration_s=200.0, decision_interval_s=20.0, mean_exec_s=0.2)
        base_trace = generate_trace(scenario, cfg, seed=42)

        T = 60.0  # decision tick at 60s (after 3 completed 20s windows: [0, 20), [20, 40), [40, 60))

        # Split base trace into past (<= T) and future (> T)
        past_requests = [r for r in base_trace if r.arrival_s <= T]
        future_requests = [r for r in base_trace if r.arrival_s > T]

        assert len(past_requests) > 0
        assert len(future_requests) > 0

        # Construct modified trace: drastically alter future arrivals
        # 1) Double the future arrivals by adding duplicate shifted requests
        # 2) Add a massive 500-request burst at T + 1.0s
        modified_future = []
        next_id = max(r.id for r in base_trace) + 1

        for r in future_requests:
            modified_future.append(r)
            # Add an extra request 0.05s later
            modified_future.append(
                Request(id=next_id, arrival_s=min(cfg.duration_s - 0.01, r.arrival_s + 0.05), exec_s=r.exec_s)
            )
            next_id += 1

        # Massive burst at T + 1s
        for _ in range(200):
            modified_future.append(Request(id=next_id, arrival_s=T + 1.0, exec_s=0.3))
            next_id += 1

        # Sort combined trace by arrival_s
        modified_trace = sorted(past_requests + modified_future, key=lambda r: r.arrival_s)
        # Ensure sequential ids
        modified_trace = [
            Request(id=idx, arrival_s=r.arrival_s, exec_s=r.exec_s)
            for idx, r in enumerate(modified_trace)
        ]

        # Run 1: original trace
        forecaster1 = EWMAForecaster(alpha=0.4)
        policy1 = WarmLambdaPolicy(forecaster1, cfg, headroom=0.5)
        res1 = simulate(base_trace, policy1, cfg)

        # Run 2: modified future trace
        forecaster2 = EWMAForecaster(alpha=0.4)
        policy2 = WarmLambdaPolicy(forecaster2, cfg, headroom=0.5)
        res2 = simulate(modified_trace, policy2, cfg)

        # Extract decisions up to and including T
        decisions1_up_to_T = [
            (rec.t, rec.target) for rec in res1.intervals if rec.t <= T + 1e-9
        ]
        decisions2_up_to_T = [
            (rec.t, rec.target) for rec in res2.intervals if rec.t <= T + 1e-9
        ]

        # Verify decisions match exactly at all ticks <= T
        assert len(decisions1_up_to_T) > 0
        assert decisions1_up_to_T == decisions2_up_to_T

        # Verify specifically decision at T
        target_at_T_1 = [rec.target for rec in res1.intervals if math.isclose(rec.t, T, abs_tol=1e-5)][0]
        target_at_T_2 = [rec.target for rec in res2.intervals if math.isclose(rec.t, T, abs_tol=1e-5)][0]
        assert target_at_T_1 == target_at_T_2

        # Verify that decisions AFTER T do differ because future traffic is drastically different
        decisions1_after_T = [rec.target for rec in res1.intervals if rec.t > T]
        decisions2_after_T = [rec.target for rec in res2.intervals if rec.t > T]
        assert decisions1_after_T != decisions2_after_T

    @pytest.mark.parametrize(
        "policy_name",
        [
            "wl_littles_law",
            "wl_quantile_forecast_only",
            "wl_quantile_full",
        ],
    )
    def test_new_capacity_policies_are_causal(self, policy_name: str) -> None:
        cfg = SimConfig(duration_s=200.0, decision_interval_s=20.0, mean_exec_s=0.2)
        base_trace = generate_trace("moderate", cfg, seed=42)
        decision_time = 60.0
        past_requests = [r for r in base_trace if r.arrival_s <= decision_time]
        future_requests = [r for r in base_trace if r.arrival_s > decision_time]
        next_id = max(request.id for request in base_trace) + 1
        modified_future = []
        for request in future_requests:
            modified_future.extend(
                [
                    request,
                    Request(
                        id=next_id,
                        arrival_s=min(cfg.duration_s - 0.01, request.arrival_s + 0.05),
                        exec_s=request.exec_s,
                    ),
                ]
            )
            next_id += 1
        modified_future.extend(
            Request(id=next_id + index, arrival_s=decision_time + 1.0, exec_s=0.3)
            for index in range(200)
        )
        modified_trace = sorted(
            past_requests + modified_future, key=lambda request: request.arrival_s
        )
        modified_trace = [
            Request(index, request.arrival_s, request.exec_s)
            for index, request in enumerate(modified_trace)
        ]

        results = []
        for trace in (base_trace, modified_trace):
            policy, _ = instantiate_policy(
                policy_name,
                trace,
                cfg,
                model="ewma",
            )
            results.append(simulate(trace, policy, cfg))

        decisions = [
            [(record.t, record.target) for record in result.intervals if record.t <= decision_time]
            for result in results
        ]
        assert decisions[0] == decisions[1]
        after_time = [
            [record.target for record in result.intervals if record.t > decision_time]
            for result in results
        ]
        assert after_time[0] != after_time[1]
