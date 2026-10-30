"""Machine-learning forecasters with a common causal runtime interface."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Optional

import numpy as np

from warmlambda.core.forecaster import Forecaster
from warmlambda.core.ml_dataset import counts_to_features


class RidgeForecaster(Forecaster):
    """Regularized linear forecaster with an optional calibrated quantile offset.

    The model uses the causal feature vector from ``ml_dataset`` and solves
    ridge regression with NumPy. For a quantile model, the requested residual
    quantile is added to the mean prediction and estimated on training data.
    """

    def __init__(self, quantile: Optional[float] = None, k: int = 60, window_s: float = 10.0, alpha: float = 1.0) -> None:
        if quantile is not None and not 0.0 < quantile < 1.0:
            raise ValueError(f"quantile must be between 0 and 1, got {quantile}")
        if alpha <= 0.0:
            raise ValueError(f"alpha must be positive, got {alpha}")
        self.quantile = quantile
        self.k = k
        self.window_s = window_s
        self.alpha = float(alpha)
        self.name = "ridge_q90" if quantile == 0.9 else "ridge"
        self.coef_: Optional[np.ndarray] = None
        self.feature_mean_: Optional[np.ndarray] = None
        self.feature_scale_: Optional[np.ndarray] = None
        self.intercept_: float = 0.0
        self.residual_offset_: float = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray, groups: Optional[np.ndarray] = None) -> "RidgeForecaster":
        if X.ndim != 2 or y.ndim != 1 or len(X) != len(y):
            raise ValueError("X must be 2-D, y must be 1-D, and they must have equal row counts")
        self.feature_mean_ = np.asarray(X.mean(axis=0), dtype=np.float64)
        scale = np.asarray(X.std(axis=0), dtype=np.float64)
        self.feature_scale_ = np.where(scale > 1e-8, scale, 1.0)
        scaled = (np.asarray(X, dtype=np.float64) - self.feature_mean_) / self.feature_scale_
        target = np.asarray(y, dtype=np.float64)
        design = np.column_stack((np.ones(len(scaled)), scaled))
        penalty = np.eye(design.shape[1], dtype=np.float64)
        penalty[0, 0] = 0.0
        system = design.T @ design + self.alpha * penalty
        solution = np.linalg.solve(system, design.T @ target)
        self.intercept_ = float(solution[0])
        self.coef_ = solution[1:]
        residuals = target - self._predict_rows(np.asarray(X, dtype=np.float64))
        self.residual_offset_ = float(np.quantile(residuals, self.quantile)) if self.quantile else 0.0
        return self

    def _predict_rows(self, X: np.ndarray) -> np.ndarray:
        if self.coef_ is None or self.feature_mean_ is None or self.feature_scale_ is None:
            raise RuntimeError("RidgeForecaster must be fitted or loaded before prediction")
        scaled = (X - self.feature_mean_) / self.feature_scale_
        return self.intercept_ + scaled @ self.coef_ + self.residual_offset_

    def predict_features(self, X: np.ndarray) -> np.ndarray:
        """Predict a batch of already-built causal feature rows."""
        return np.maximum(0.0, self._predict_rows(np.asarray(X, dtype=np.float64)))

    def predict(self, counts: list[int], window_s: float) -> float:
        features = counts_to_features(np.asarray(counts, dtype=np.float32), len(counts), self.k)
        return float(self.predict_features(features.reshape(1, -1))[0])

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            quantile=np.asarray(-1.0 if self.quantile is None else self.quantile),
            k=np.asarray(self.k),
            window_s=np.asarray(self.window_s),
            alpha=np.asarray(self.alpha),
            feature_mean=self.feature_mean_,
            feature_scale=self.feature_scale_,
            coef=self.coef_,
            intercept=np.asarray(self.intercept_),
            residual_offset=np.asarray(self.residual_offset_),
        )

    @classmethod
    def load(cls, path: str | Path) -> "RidgeForecaster":
        data = np.load(path, allow_pickle=False)
        quantile_value = float(data["quantile"])
        instance = cls(
            quantile=None if quantile_value < 0 else quantile_value,
            k=int(data["k"]),
            window_s=float(data["window_s"]),
            alpha=float(data["alpha"]),
        )
        instance.feature_mean_ = data["feature_mean"]
        instance.feature_scale_ = data["feature_scale"]
        instance.coef_ = data["coef"]
        instance.intercept_ = float(data["intercept"])
        instance.residual_offset_ = float(data["residual_offset"])
        return instance


class GRUForecaster(Forecaster):
    """Keras GRU forecaster; TensorFlow is imported only when used."""

    def __init__(self, k: int = 60, window_s: float = 10.0) -> None:
        self.k = k
        self.window_s = window_s
        self.name = "gru"
        self.model: Any = None
        self.input_scale = 1.0

    def fit(self, X: np.ndarray, y: np.ndarray, groups: Optional[np.ndarray] = None) -> "GRUForecaster":
        try:
            import tensorflow as tf
        except ImportError as exc:
            raise RuntimeError("GRUForecaster requires tensorflow; install requirements.txt") from exc
        random.seed(0)
        np.random.seed(0)
        tf.random.set_seed(0)
        # The first k columns are the lag sequence.  They are stored oldest first.
        self.model = tf.keras.Sequential(
            [
                tf.keras.layers.Input(shape=(self.k, 1)),
                tf.keras.layers.GRU(64),
                tf.keras.layers.Dense(32, activation="relu"),
                tf.keras.layers.Dense(1),
            ]
        )
        self.model.compile(optimizer=tf.keras.optimizers.Adam(), loss=tf.keras.losses.Huber())
        lag_data = np.log1p(np.maximum(X[:, :self.k], 0.0)).astype(np.float32)
        self.input_scale = max(float(lag_data.max()), 1.0)
        lag_data /= self.input_scale
        self.model.fit(
            lag_data.reshape((-1, self.k, 1)),
            np.maximum(y, 0.0),
            validation_split=0.1,
            epochs=100,
            batch_size=512,
            callbacks=[tf.keras.callbacks.EarlyStopping(patience=8, restore_best_weights=True)],
            verbose=0,
            shuffle=False,
        )
        return self

    def predict(self, counts: list[int], window_s: float) -> float:
        if self.model is None:
            return 0.0
        padded = counts_to_features(np.asarray(counts, dtype=np.float32), len(counts), self.k)[:self.k]
        scaled = np.log1p(np.maximum(padded, 0)) / self.input_scale
        value = float(self.model.predict(scaled.reshape(1, self.k, 1), verbose=0)[0, 0])
        return max(0.0, value)

    def save(self, path: str | Path) -> None:
        if self.model is None:
            raise RuntimeError("Cannot save an unfitted GRUForecaster")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.model.save(path)
        path.with_suffix(".json").write_text(
            json.dumps({"k": self.k, "window_s": self.window_s, "input_scale": self.input_scale}), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> "GRUForecaster":
        import tensorflow as tf
        metadata_path = Path(path).with_suffix(".json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        instance = cls(k=int(metadata.get("k", 60)), window_s=float(metadata.get("window_s", 10.0)))
        instance.input_scale = float(metadata.get("input_scale", 1.0))
        instance.model = tf.keras.models.load_model(path)
        return instance
