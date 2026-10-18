"""
Tests for warmlambda.core.simulator
====================================
Hand-computed scenarios with init_time_s = 1.0 (unless overridden).
"""

from __future__ import annotations

import math

import pytest

from warmlambda.core.config import SimConfig
from warmlambda.core.policies.base import Policy, SimState, TrafficHistory
from warmlambda.core.policies.no_warming import NoWarming
from warmlambda.core.simulator import simulate, SimResult
from warmlambda.core.traffic import Request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(**overrides) -> SimConfig:
    """Return a SimConfig with sensible test defaults (short duration)."""
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


def _req(id: int, arrival_s: float, exec_s: float) -> Request:
    return Request(id=id, arrival_s=arrival_s, exec_s=exec_s)


# ---------------------------------------------------------------------------
# Test: one request at t=0, exec 0.5 → cold, latency 1.5
# ---------------------------------------------------------------------------


class TestOneRequest:
    """Single request: cold start adds init_time_s to latency."""

    def test_cold_start_latency(self) -> None:
        cfg = _cfg()
        trace = [_req(0, arrival_s=0.0, exec_s=0.5)]
        result = simulate(trace, NoWarming(), cfg)

        assert len(result.requests) == 1
        rec = result.requests[0]

        assert rec.cold is True
        assert rec.dropped is False
        # latency = init_time(1.0) + exec(0.5) = 1.5
        assert rec.latency_s is not None
        assert math.isclose(rec.latency_s, 1.5, abs_tol=1e-9)
        assert rec.start_s is not None
        assert math.isclose(rec.start_s, 1.0, abs_tol=1e-9)
        assert rec.finish_s is not None
        assert math.isclose(rec.finish_s, 1.5, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Test: two requests, t=0 and t=10, exec 0.5 each, idle_timeout=300
#   → first cold (latency 1.5), second warm (latency 0.5)
# ---------------------------------------------------------------------------


class TestTwoRequestsWarmReuse:
    """Second request reuses the warm instance."""

    def test_warm_reuse(self) -> None:
        cfg = _cfg(idle_timeout_s=300.0)
        trace = [
            _req(0, arrival_s=0.0, exec_s=0.5),
            _req(1, arrival_s=10.0, exec_s=0.5),
        ]
        result = simulate(trace, NoWarming(), cfg)

        assert len(result.requests) == 2

        r0 = result.requests[0]
        assert r0.cold is True
        assert math.isclose(r0.latency_s, 1.5, abs_tol=1e-9)

        r1 = result.requests[1]
        assert r1.cold is False
        assert r1.dropped is False
        assert r1.latency_s is not None
        assert math.isclose(r1.latency_s, 0.5, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Test: two overlapping requests at t=0 and t=0.1, concurrency=1
#   → both cold (each gets its own instance)
# ---------------------------------------------------------------------------


class TestOverlappingColdStarts:
    """Two near-simultaneous requests both trigger cold starts."""

    def test_both_cold(self) -> None:
        cfg = _cfg(concurrency_per_instance=1)
        trace = [
            _req(0, arrival_s=0.0, exec_s=2.0),
            _req(1, arrival_s=0.1, exec_s=0.5),
        ]
        result = simulate(trace, NoWarming(), cfg)

        assert len(result.requests) == 2

        r0 = result.requests[0]
        r1 = result.requests[1]

        assert r0.cold is True
        assert r1.cold is True
        assert r0.dropped is False
        assert r1.dropped is False


# ---------------------------------------------------------------------------
# Test: max_instances=1, queue_timeout_s=0.2 with a long request → second
#   request is dropped
# ---------------------------------------------------------------------------


class TestQueueDrop:
    """Queue timeout drops the second request when no instance is free."""

    def test_second_dropped(self) -> None:
        cfg = _cfg(
            max_instances=1,
            queue_timeout_s=0.2,
            concurrency_per_instance=1,
        )
        trace = [
            _req(0, arrival_s=0.0, exec_s=5.0),
            _req(1, arrival_s=0.5, exec_s=0.5),
        ]
        result = simulate(trace, NoWarming(), cfg)

        assert len(result.requests) == 2

        r0 = result.requests[0]
        assert r0.cold is True
        assert r0.dropped is False

        r1 = result.requests[1]
        assert r1.dropped is True
        assert r1.latency_s is None


# ---------------------------------------------------------------------------
# Test: every request is accounted for (completed or dropped)
# ---------------------------------------------------------------------------


class TestAllRequestsAccountedFor:
    """All input requests appear exactly once in the output."""

    def test_all_requests_present(self) -> None:
        cfg = _cfg(max_instances=2, queue_timeout_s=0.5)
        trace = [
            _req(i, arrival_s=i * 0.1, exec_s=3.0)
            for i in range(10)
        ]
        result = simulate(trace, NoWarming(), cfg)

        assert len(result.requests) == 10
        ids = {r.id for r in result.requests}
        assert ids == set(range(10))

        for rec in result.requests:
            assert rec.dropped or (
                rec.start_s is not None
                and rec.finish_s is not None
                and rec.latency_s is not None
            )


# ---------------------------------------------------------------------------
# Test: init_time_s=0 → no cold-start latency added
# ---------------------------------------------------------------------------


class TestZeroInitTime:
    """With zero init time, cold starts add no extra latency."""

    def test_no_extra_latency(self) -> None:
        cfg = _cfg(init_time_s=0.0)
        trace = [_req(0, arrival_s=0.0, exec_s=0.5)]
        result = simulate(trace, NoWarming(), cfg)

        rec = result.requests[0]
        assert rec.cold is True
        assert rec.latency_s is not None
        # With init_time=0, latency = exec time = 0.5
        assert math.isclose(rec.latency_s, 0.5, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Test: instance seconds are non-negative and consistent
# ---------------------------------------------------------------------------


class TestInstanceSeconds:
    """Aggregate instance-seconds are non-negative."""

    def test_non_negative(self) -> None:
        cfg = _cfg()
        trace = [
            _req(0, arrival_s=0.0, exec_s=0.5),
            _req(1, arrival_s=5.0, exec_s=0.5),
        ]
        result = simulate(trace, NoWarming(), cfg)

        assert result.busy_seconds >= 0.0
        assert result.idle_warm_seconds >= 0.0
        assert result.init_seconds >= 0.0
        # Total should be positive (at least the execution time)
        total = result.busy_seconds + result.idle_warm_seconds + result.init_seconds
        assert total > 0.0

    def test_busy_at_least_exec_time(self) -> None:
        """Busy seconds >= sum of execution times for completed requests."""
        cfg = _cfg()
        trace = [
            _req(0, arrival_s=0.0, exec_s=0.5),
            _req(1, arrival_s=5.0, exec_s=1.0),
        ]
        result = simulate(trace, NoWarming(), cfg)

        total_exec = sum(
            r.finish_s - r.start_s
            for r in result.requests
            if not r.dropped and r.start_s is not None
        )
        assert result.busy_seconds >= total_exec - 1e-9


# ---------------------------------------------------------------------------
# Integration: moderate trace + NoWarming finishes quickly
# ---------------------------------------------------------------------------


class TestIntegrationModerate:
    """Running a 1-hour moderate trace with NoWarming should complete fast."""

    def test_runs_and_has_cold_starts(self) -> None:
        from warmlambda.core.traffic import generate_trace

        cfg = SimConfig()  # defaults: 1 hour
        trace = generate_trace("moderate", cfg, seed=42)
        result = simulate(trace, NoWarming(), cfg)

        cold_starts = sum(1 for r in result.requests if r.cold)
        completed = sum(1 for r in result.requests if not r.dropped)

        assert completed > 0
        assert cold_starts > 0
        # With NoWarming, we expect a significant fraction of cold starts
        print(
            f"  moderate/NoWarming: {completed} completed, "
            f"{cold_starts} cold starts "
            f"({100 * cold_starts / max(1, completed):.1f}%)"
        )
