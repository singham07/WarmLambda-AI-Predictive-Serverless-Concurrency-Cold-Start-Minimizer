"""
tests/test_traffic.py
=====================
Unit and statistical tests for :mod:`warmlambda.core.traffic`.

Test classes
------------
TestRequest              – frozen dataclass basics
TestReproducibility      – same seed ↔ identical trace; different seeds differ
TestArrivalProperties    – sorted, in-range, sequential IDs
TestCountAccuracy        – empirical count within 10 % of rate-function integral
TestExecTimeMean         – empirical mean exec_s within 10 % of cfg.mean_exec_s
TestExtremeSpikes        – at least one window with rate > 5× base
TestUnknownScenario      – generate_trace raises ValueError on bad scenario
TestSaveLoad             – CSV round-trip identical to original trace
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from warmlambda.core.config import SimConfig
from warmlambda.core.traffic import (
    SCENARIOS,
    Request,
    generate_trace,
    get_max_rate,
    load_trace,
    save_trace,
)

# ---------------------------------------------------------------------------
# Shared fixtures / constants
# ---------------------------------------------------------------------------

_DEFAULT_CFG = SimConfig(duration_s=3600.0, mean_exec_s=0.2, exec_sigma=0.5)
_SEED = 42


# ---------------------------------------------------------------------------
# Request dataclass
# ---------------------------------------------------------------------------


class TestRequest:
    """Basic structural tests for the Request dataclass."""

    def test_fields_stored(self) -> None:
        req = Request(id=3, arrival_s=12.5, exec_s=0.4)
        assert req.id == 3
        assert req.arrival_s == 12.5
        assert req.exec_s == 0.4

    def test_frozen_raises_on_assignment(self) -> None:
        req = Request(id=0, arrival_s=0.0, exec_s=0.1)
        with pytest.raises(Exception):
            req.id = 99  # type: ignore[misc]

    def test_equality_by_value(self) -> None:
        assert Request(0, 1.0, 0.5) == Request(0, 1.0, 0.5)
        assert Request(0, 1.0, 0.5) != Request(1, 1.0, 0.5)


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------


class TestReproducibility:
    """Same seed produces an identical trace; different seeds produce different traces."""

    @pytest.mark.parametrize("scenario", list(SCENARIOS))
    def test_same_seed_same_trace(self, scenario: str) -> None:
        trace_a = generate_trace(scenario, _DEFAULT_CFG, seed=_SEED)
        trace_b = generate_trace(scenario, _DEFAULT_CFG, seed=_SEED)
        assert len(trace_a) == len(trace_b), "Lengths differ with same seed"
        for a, b in zip(trace_a, trace_b):
            assert a.arrival_s == b.arrival_s, "arrival_s differs with same seed"
            assert a.exec_s == b.exec_s, "exec_s differs with same seed"

    @pytest.mark.parametrize("scenario", list(SCENARIOS))
    def test_different_seeds_differ(self, scenario: str) -> None:
        trace_a = generate_trace(scenario, _DEFAULT_CFG, seed=1)
        trace_b = generate_trace(scenario, _DEFAULT_CFG, seed=2)
        # Either length differs or at least one arrival time differs
        same = len(trace_a) == len(trace_b) and all(
            a.arrival_s == b.arrival_s for a, b in zip(trace_a, trace_b)
        )
        assert not same, "Different seeds produced identical traces"

    @pytest.mark.parametrize("scenario", list(SCENARIOS))
    def test_randomize_false_preserves_legacy_trace(self, scenario: str) -> None:
        """The new option must not alter the established default path."""
        implicit = generate_trace(scenario, _DEFAULT_CFG, seed=_SEED)
        explicit = generate_trace(scenario, _DEFAULT_CFG, seed=_SEED, randomize=False)
        assert implicit == explicit


# ---------------------------------------------------------------------------
# Arrival properties
# ---------------------------------------------------------------------------


class TestArrivalProperties:
    """Arrivals must be sorted, in [0, duration_s), and have sequential IDs."""

    @pytest.mark.parametrize("scenario", list(SCENARIOS))
    def test_sorted_by_arrival(self, scenario: str) -> None:
        trace = generate_trace(scenario, _DEFAULT_CFG, seed=_SEED)
        arrivals = [r.arrival_s for r in trace]
        assert arrivals == sorted(arrivals), "Trace not sorted by arrival_s"

    @pytest.mark.parametrize("scenario", list(SCENARIOS))
    def test_arrivals_in_range(self, scenario: str) -> None:
        trace = generate_trace(scenario, _DEFAULT_CFG, seed=_SEED)
        for req in trace:
            assert 0.0 <= req.arrival_s < _DEFAULT_CFG.duration_s, (
                f"arrival_s={req.arrival_s} out of [0, {_DEFAULT_CFG.duration_s})"
            )

    @pytest.mark.parametrize("scenario", list(SCENARIOS))
    def test_ids_are_sequential_from_zero(self, scenario: str) -> None:
        trace = generate_trace(scenario, _DEFAULT_CFG, seed=_SEED)
        assert [r.id for r in trace] == list(range(len(trace)))


# ---------------------------------------------------------------------------
# Count accuracy (within 10 % of rate-function integral)
# ---------------------------------------------------------------------------


class TestCountAccuracy:
    """Empirical request count should be within 10 % of ∫rate(t)dt."""

    # ── Analytic integrals ──────────────────────────────────────────────────

    @staticmethod
    def _integral_moderate(duration_s: float) -> float:
        """∫₀ᵀ 3·(1 + 0.3·sin(2π·t/1200)) dt = 3·T  (sine averages to ~0)."""
        return 3.0 * duration_s

    @staticmethod
    def _integral_high_load(cfg: SimConfig) -> float:
        """∫₀ᵀ 30·(0.6 + 0.8·t/T) dt = 30·T·(0.6 + 0.4) = 30·T."""
        return 30.0 * cfg.duration_s  # average scale = (0.6+1.4)/2 = 1.0

    # ── Tests ───────────────────────────────────────────────────────────────

    def test_moderate_count_within_10_percent(self) -> None:
        cfg = SimConfig(duration_s=3600.0)
        trace = generate_trace("moderate", cfg, seed=0)
        expected = self._integral_moderate(cfg.duration_s)
        ratio = abs(len(trace) - expected) / expected
        assert ratio <= 0.10, (
            f"moderate count {len(trace)} deviates {ratio:.1%} from expected {expected:.0f}"
        )

    def test_high_load_count_within_10_percent(self) -> None:
        cfg = SimConfig(duration_s=3600.0)
        trace = generate_trace("high_load", cfg, seed=0)
        expected = self._integral_high_load(cfg)
        ratio = abs(len(trace) - expected) / expected
        assert ratio <= 0.10, (
            f"high_load count {len(trace)} deviates {ratio:.1%} from expected {expected:.0f}"
        )


# ---------------------------------------------------------------------------
# Execution-time mean accuracy
# ---------------------------------------------------------------------------


class TestExecTimeMean:
    """Empirical mean exec_s must be within 10 % of cfg.mean_exec_s."""

    @pytest.mark.parametrize(
        "scenario,mean_exec_s",
        [
            ("moderate", 0.3),
            ("high_load", 0.5),
            ("periodic", 0.2),
        ],
    )
    def test_mean_exec_s_accurate(self, scenario: str, mean_exec_s: float) -> None:
        # Use a 2-hour run to get enough samples for statistical stability
        cfg = SimConfig(duration_s=7200.0, mean_exec_s=mean_exec_s, exec_sigma=0.5)
        trace = generate_trace(scenario, cfg, seed=99)
        assert len(trace) >= 200, (
            f"Trace too short ({len(trace)}) for statistical mean test"
        )
        empirical = sum(r.exec_s for r in trace) / len(trace)
        ratio = abs(empirical - mean_exec_s) / mean_exec_s
        assert ratio <= 0.10, (
            f"{scenario}: empirical mean {empirical:.4f} deviates {ratio:.1%} "
            f"from cfg.mean_exec_s={mean_exec_s}"
        )


# ---------------------------------------------------------------------------
# Extreme spike verification
# ---------------------------------------------------------------------------


class TestExtremeSpikes:
    """The extreme scenario must have at least one window with rate > 5× base."""

    def test_spike_window_exists(self) -> None:
        """Find a 30-second bin whose empirical rate exceeds 5 × 2.0 req/s."""
        cfg = SimConfig(duration_s=3600.0)
        BIN_S = 30.0
        BASE = 2.0
        THRESHOLD_MULT = 5.0

        # Try multiple seeds to guard against unlucky placement
        for seed in range(5):
            trace = generate_trace("extreme", cfg, seed=seed)
            n_bins = int(cfg.duration_s / BIN_S)
            counts = [0] * n_bins
            for req in trace:
                b = int(req.arrival_s / BIN_S)
                if b < n_bins:
                    counts[b] += 1

            max_rate_empirical = max(counts) / BIN_S
            if max_rate_empirical > THRESHOLD_MULT * BASE:
                return  # Found a spike – test passes

        pytest.fail(
            f"No 30 s window exceeded {THRESHOLD_MULT}× base ({BASE} req/s) "
            f"across seeds 0-4 for extreme scenario."
        )

    def test_get_max_rate_extreme_above_base(self) -> None:
        """get_max_rate for extreme must be > 5× the base rate."""
        cfg = SimConfig(duration_s=3600.0)
        max_r = get_max_rate("extreme", cfg, seed=0)
        assert max_r > 5 * 2.0, f"get_max_rate={max_r} not > 5×base"


# ---------------------------------------------------------------------------
# Unknown scenario
# ---------------------------------------------------------------------------


class TestUnknownScenario:
    def test_generate_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown scenario"):
            generate_trace("nonexistent", _DEFAULT_CFG, seed=0)

    def test_get_max_rate_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown scenario"):
            get_max_rate("nonexistent", _DEFAULT_CFG, seed=0)


# ---------------------------------------------------------------------------
# CSV round-trip
# ---------------------------------------------------------------------------


class TestSaveLoad:
    """save_trace then load_trace must give a trace identical to the original."""

    @pytest.mark.parametrize("scenario", list(SCENARIOS))
    def test_round_trip_exact(self, scenario: str, tmp_path: object) -> None:
        import pathlib

        original = generate_trace(scenario, _DEFAULT_CFG, seed=123)
        path = pathlib.Path(str(tmp_path)) / "trace.csv"  # type: ignore[arg-type]
        save_trace(path, original)
        loaded = load_trace(path)

        assert len(original) == len(loaded), "Length mismatch after round-trip"
        for orig, load in zip(original, loaded):
            assert orig.id == load.id, "id mismatch"
            assert orig.arrival_s == load.arrival_s, (
                f"arrival_s mismatch: {orig.arrival_s!r} vs {load.arrival_s!r}"
            )
            assert orig.exec_s == load.exec_s, (
                f"exec_s mismatch: {orig.exec_s!r} vs {load.exec_s!r}"
            )

    def test_csv_header(self, tmp_path: object) -> None:
        import pathlib

        trace = generate_trace("moderate", _DEFAULT_CFG, seed=0)
        path = pathlib.Path(str(tmp_path)) / "trace.csv"  # type: ignore[arg-type]
        save_trace(path, trace)
        with open(path) as fh:
            header = fh.readline().strip()
        assert header == "id,arrival_s,exec_s"

    def test_empty_trace_round_trip(self, tmp_path: object) -> None:
        """An empty trace should save and load cleanly."""
        import pathlib

        path = pathlib.Path(str(tmp_path)) / "empty.csv"  # type: ignore[arg-type]
        save_trace(path, [])
        loaded = load_trace(path)
        assert loaded == []
