from __future__ import annotations

import numpy as np

from backend.warmlambda.core.config import SimConfig
from backend.warmlambda.core.traffic import SCENARIOS, generate_trace


def test_realistic_rate_factories_are_deterministic_and_seeded() -> None:
    cfg = SimConfig(duration_s=3600)
    for name in ("scheduled_bursts", "daily_cycle"):
        first = SCENARIOS[name](cfg, 0)
        same = SCENARIOS[name](cfg, 0)
        other = SCENARIOS[name](cfg, 1)
        values = [first(t) for t in np.linspace(0, 3599, 500)]
        assert [first(t) for t in (0, 300, 900)] == [same(t) for t in (0, 300, 900)]
        assert any(first(t) != other(t) for t in (0, 300, 900))
        assert min(values) >= 0


def test_realistic_rates_have_expected_shape() -> None:
    cfg = SimConfig(duration_s=3600)
    scheduled = SCENARIOS["scheduled_bursts"](cfg, 0)
    daily = SCENARIOS["daily_cycle"](cfg, 0)
    assert scheduled(330) >= 8 * scheduled(100)
    assert max(daily(t) for t in np.linspace(0, 1800, 500)) >= 10 * min(
        daily(t) for t in np.linspace(0, 1800, 500)
    )


def test_realistic_trace_generation_supports_short_and_full_runs() -> None:
    for duration in (600.0, 3600.0):
        cfg = SimConfig(duration_s=duration)
        for scenario in ("scheduled_bursts", "daily_cycle"):
            trace = generate_trace(scenario, cfg, seed=0)
            assert all(0 <= request.arrival_s < duration for request in trace)
