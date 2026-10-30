"""Focused tests for causal ML features and model interfaces."""

from __future__ import annotations

import numpy as np

from warmlambda.core.config import SimConfig
from warmlambda.core.forecaster_registry import get_forecaster
from warmlambda.core.ml_dataset import counts_to_features
from warmlambda.core.ml_forecaster import RidgeForecaster
from warmlambda.core.policies.warmlambda import WarmLambdaPolicy


def test_features_ignore_future_counts() -> None:
    """Changing windows after t cannot change the feature row at t."""
    prefix = np.asarray([2, 4, 6, 8], dtype=np.float32)
    first = counts_to_features(np.concatenate([prefix, [1, 1]]), 4, 60)
    second = counts_to_features(np.concatenate([prefix, [999, 999]]), 4, 60)
    np.testing.assert_array_equal(first, second)


def test_ml_feature_shape_and_float32() -> None:
    row = counts_to_features(np.asarray([1, 2, 3], dtype=np.float32), 3, 60)
    assert row.shape == (80,)
    assert row.dtype == np.float32


def test_registry_statistical_models_are_non_negative() -> None:
    for name in ("ewma", "seasonal"):
        model = get_forecaster(name)
        assert model.predict([10, 0, 2], 10.0) >= 0.0


def test_policy_accepts_registry_forecaster() -> None:
    cfg = SimConfig(duration_s=100.0)
    policy = WarmLambdaPolicy(get_forecaster("ewma"), cfg)
    assert policy.decide(
        type("History", (), {"counts": [10], "window_s": 10.0, "now": 20.0})(),
        type("State", (), {})(),
    ) >= 0


def test_ridge_forecaster_is_causal_and_round_trips(tmp_path) -> None:
    X = np.asarray(
        [counts_to_features(np.asarray(row, dtype=np.float32), len(row), 60) for row in ([1, 2], [2, 4], [4, 8], [8, 16])],
        dtype=np.float32,
    )
    y = np.asarray([1.0, 2.0, 4.0, 8.0], dtype=np.float32)
    model = RidgeForecaster(quantile=0.9)
    model.fit(X, y)
    path = tmp_path / "ridge_q90.npz"
    model.save(path)
    loaded = RidgeForecaster.load(path)

    np.testing.assert_allclose(model.predict_features(X), loaded.predict_features(X))
    assert loaded.predict([1, 2], 10.0) >= 0.0
