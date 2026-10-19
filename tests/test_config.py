"""
tests/test_config.py
====================
Unit tests for :class:`warmlambda.core.config.SimConfig`.

Covers:
- Default field values
- Custom overrides
- Validation: invalid values raise ``ValueError`` with a descriptive message
"""

from __future__ import annotations

import pytest

from warmlambda.core.config import SimConfig


# ──────────────────────────────────────────────────────────────────────────────
# Defaults
# ──────────────────────────────────────────────────────────────────────────────


class TestDefaults:
    """SimConfig should expose correct default values for every field."""

    def setup_method(self) -> None:
        self.cfg = SimConfig()

    def test_duration_s(self) -> None:
        assert self.cfg.duration_s == 3600.0

    def test_init_time_s(self) -> None:
        assert self.cfg.init_time_s == 1.0

    def test_mean_exec_s(self) -> None:
        assert self.cfg.mean_exec_s == 0.2

    def test_exec_sigma(self) -> None:
        assert self.cfg.exec_sigma == 0.5

    def test_idle_timeout_s(self) -> None:
        assert self.cfg.idle_timeout_s == 60.0

    def test_max_instances(self) -> None:
        assert self.cfg.max_instances == 100

    def test_concurrency_per_instance(self) -> None:
        assert self.cfg.concurrency_per_instance == 1

    def test_queue_timeout_s(self) -> None:
        assert self.cfg.queue_timeout_s == 10.0

    def test_decision_interval_s(self) -> None:
        assert self.cfg.decision_interval_s == 20.0

    def test_warm_cost_weight(self) -> None:
        assert self.cfg.warm_cost_weight == 1.0

    def test_busy_cost_weight(self) -> None:
        assert self.cfg.busy_cost_weight == 1.0


# ──────────────────────────────────────────────────────────────────────────────
# Custom config
# ──────────────────────────────────────────────────────────────────────────────


class TestCustomConfig:
    """Custom values should be accepted and stored correctly."""

    def test_custom_duration(self) -> None:
        cfg = SimConfig(duration_s=7200.0)
        assert cfg.duration_s == 7200.0

    def test_custom_max_instances(self) -> None:
        cfg = SimConfig(max_instances=50)
        assert cfg.max_instances == 50

    def test_custom_cost_weights(self) -> None:
        cfg = SimConfig(warm_cost_weight=2.5, busy_cost_weight=0.5)
        assert cfg.warm_cost_weight == 2.5
        assert cfg.busy_cost_weight == 0.5

    def test_zero_init_time_allowed(self) -> None:
        """init_time_s == 0 is explicitly permitted (instantaneous cold start)."""
        cfg = SimConfig(init_time_s=0.0)
        assert cfg.init_time_s == 0.0

    def test_all_fields_custom(self) -> None:
        cfg = SimConfig(
            duration_s=1800.0,
            init_time_s=0.5,
            mean_exec_s=0.1,
            exec_sigma=0.3,
            idle_timeout_s=120.0,
            max_instances=10,
            concurrency_per_instance=2,
            queue_timeout_s=5.0,
            decision_interval_s=10.0,
            warm_cost_weight=1.5,
            busy_cost_weight=0.8,
        )
        assert cfg.duration_s == 1800.0
        assert cfg.init_time_s == 0.5
        assert cfg.mean_exec_s == 0.1
        assert cfg.exec_sigma == 0.3
        assert cfg.idle_timeout_s == 120.0
        assert cfg.max_instances == 10
        assert cfg.concurrency_per_instance == 2
        assert cfg.queue_timeout_s == 5.0
        assert cfg.decision_interval_s == 10.0
        assert cfg.warm_cost_weight == 1.5
        assert cfg.busy_cost_weight == 0.8

    def test_frozen_immutability(self) -> None:
        """SimConfig is frozen; attribute assignment must raise FrozenInstanceError."""
        cfg = SimConfig()
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError (or AttributeError)
            cfg.duration_s = 999.0  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────────────────────
# Validation: invalid values must raise ValueError
# ──────────────────────────────────────────────────────────────────────────────


class TestValidation:
    """Invalid field values should raise ValueError with a clear message."""

    @pytest.mark.parametrize(
        "field,bad_value",
        [
            ("duration_s", 0),
            ("duration_s", -1.0),
            ("mean_exec_s", 0),
            ("mean_exec_s", -0.5),
            ("exec_sigma", 0),
            ("exec_sigma", -1.0),
            ("idle_timeout_s", 0),
            ("idle_timeout_s", -300.0),
            ("concurrency_per_instance", 0),
            ("concurrency_per_instance", -1),
            ("queue_timeout_s", 0),
            ("queue_timeout_s", -5.0),
            ("decision_interval_s", 0),
            ("decision_interval_s", -10.0),
            ("warm_cost_weight", 0),
            ("warm_cost_weight", -0.1),
            ("busy_cost_weight", 0),
            ("busy_cost_weight", -2.0),
        ],
    )
    def test_positive_field_raises(self, field: str, bad_value: float) -> None:
        with pytest.raises(ValueError, match=field):
            SimConfig(**{field: bad_value})

    def test_negative_init_time_raises(self) -> None:
        with pytest.raises(ValueError, match="init_time_s"):
            SimConfig(init_time_s=-0.1)

    @pytest.mark.parametrize("bad_value", [0, -1, -100])
    def test_max_instances_too_small_raises(self, bad_value: int) -> None:
        with pytest.raises(ValueError, match="max_instances"):
            SimConfig(max_instances=bad_value)

    def test_error_message_contains_field_name(self) -> None:
        """ValueError message should name the offending field."""
        with pytest.raises(ValueError, match="duration_s"):
            SimConfig(duration_s=-1.0)

    def test_error_message_contains_bad_value(self) -> None:
        """ValueError message should include the bad value for easy debugging."""
        with pytest.raises(ValueError, match="-42"):
            SimConfig(duration_s=-42.0)
