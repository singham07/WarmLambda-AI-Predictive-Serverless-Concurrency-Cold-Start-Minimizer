"""Train forecasting models using disjoint trace-seed groups."""

from __future__ import annotations

import json
import time
from importlib import metadata
from pathlib import Path

import numpy as np

from warmlambda.core.config import SimConfig
from warmlambda.core.ml_dataset import build_dataset
from warmlambda.core.ml_forecaster import GRUForecaster, HGBForecaster


def _mae(model, X: np.ndarray, y: np.ndarray) -> float:
    sample = X[:20000]
    if isinstance(model, HGBForecaster):
        predictions = np.maximum(0.0, model.model.predict(sample))
    else:
        predictions = np.maximum(
            0.0,
            model.model.predict(
                (np.log1p(np.maximum(sample[:, :60], 0.0)) / model.input_scale).reshape(-1, 60, 1),
                verbose=0,
            ).ravel(),
        )
    return float(np.mean(np.abs(predictions - y[: len(predictions)])))


def main() -> None:
    """Build the default large dataset and train available model families."""
    seeds = list(range(1000, 1200))
    scenarios = ("moderate", "high_load", "extreme", "periodic")
    cfg = SimConfig()
    started = time.perf_counter()
    X, y, groups, meta = build_dataset(seeds, scenarios, cfg, window_s=10.0, k=60, randomize=True)
    split = set(seeds[:160])
    train_mask = np.isin(groups, list(split))
    val_mask = ~train_mask
    print(f"[train_forecasters] rows={len(y):,}, features={X.shape[1]}, train={train_mask.sum():,}, validation={val_mask.sum():,}")
    print(f"[train_forecasters] group overlap={set(groups[train_mask]) & set(groups[val_mask])}")

    model_dir = Path(__file__).resolve().parents[1] / "models"
    model_dir.mkdir(exist_ok=True)
    results: dict[str, float | str] = {}
    for name, model, filename in (
        ("hgb", HGBForecaster(k=60, window_s=10.0), "hgb.joblib"),
        ("hgb_q90", HGBForecaster(quantile=0.9, k=60, window_s=10.0), "hgb_q90.joblib"),
    ):
        fit_start = time.perf_counter()
        model.fit(X[train_mask], y[train_mask], groups[train_mask])
        validation_mae = _mae(model, X[val_mask], y[val_mask])
        model.save(model_dir / filename)
        results[name] = validation_mae
        print(f"[train_forecasters] {name}: validation MAE={validation_mae:.6f}, train_time_s={time.perf_counter() - fit_start:.1f}")

    try:
        gru = GRUForecaster(k=60, window_s=10.0)
        fit_start = time.perf_counter()
        gru.fit(X[train_mask], y[train_mask], groups[train_mask])
        results["gru"] = _mae(gru, X[val_mask], y[val_mask])
        gru.save(model_dir / "gru.keras")
        print(f"[train_forecasters] gru: validation MAE={results['gru']:.6f}, train_time_s={time.perf_counter() - fit_start:.1f}")
    except RuntimeError as exc:
        results["gru"] = f"unavailable: {exc}"
        print(f"[train_forecasters] {exc}; skipping GRU")

    metadata = {
        **meta,
        "training_seeds": seeds[:160],
        "validation_seeds": seeds[160:],
        "validation_metrics": results,
        "training_time_s": time.perf_counter() - started,
        "library_versions": {
            name: _version(name) for name in ("numpy", "pandas", "scikit-learn", "joblib", "tensorflow")
        },
    }
    (model_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"[train_forecasters] total_time_s={metadata['training_time_s']:.1f}")


def _version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not installed"


if __name__ == "__main__":
    main()
