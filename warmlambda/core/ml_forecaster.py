"""Machine-learning forecasters with a common causal runtime interface."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Optional

import numpy as np

from warmlambda.core.forecaster import Forecaster
from warmlambda.core.ml_dataset import counts_to_features


class HGBForecaster(Forecaster):
    """Histogram gradient boosting regression forecaster."""

    def __init__(self, quantile: Optional[float] = None, k: int = 60, window_s: float = 10.0) -> None:
        self.quantile = quantile
        self.k = k
        self.window_s = window_s
        self.name = "hgb_q90" if quantile == 0.9 else "hgb"
        self.model: Any = None

    def fit(self, X: np.ndarray, y: np.ndarray, groups: Optional[np.ndarray] = None) -> "HGBForecaster":
        try:
            from sklearn.ensemble import HistGradientBoostingRegressor
        except ImportError as exc:
            raise RuntimeError("HGBForecaster requires scikit-learn; install requirements.txt") from exc
        kwargs: dict[str, Any] = {
            "max_iter": 300,
            "learning_rate": 0.08,
            "max_leaf_nodes": 31,
            "early_stopping": True,
            "random_state": 0,
        }
        if self.quantile is not None:
            kwargs.update({"loss": "quantile", "quantile": self.quantile})
        self.model = HistGradientBoostingRegressor(**kwargs)
        self.model.fit(X, y)
        return self

    def predict(self, counts: list[int], window_s: float) -> float:
        if self.model is None:
            return 0.0
        features = counts_to_features(np.asarray(counts, dtype=np.float32), len(counts), self.k)
        value = float(self.model.predict(features.reshape(1, -1))[0])
        return max(0.0, value)

    def save(self, path: str | Path) -> None:
        try:
            import joblib
        except ImportError as exc:
            raise RuntimeError("Saving HGB models requires joblib; install requirements.txt") from exc
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: str | Path) -> "HGBForecaster":
        import joblib
        return joblib.load(path)


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
