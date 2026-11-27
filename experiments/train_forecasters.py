"""Train forecasting models using disjoint trace-seed groups."""

from __future__ import annotations

import argparse
import json
import time
from importlib import metadata
from pathlib import Path

import numpy as np

from backend.warmlambda.core.config import SimConfig
from backend.warmlambda.core.ml_dataset import build_dataset
from backend.warmlambda.core.ml_forecaster import GRUForecaster, HGBForecaster


def _mae(model, X: np.ndarray, y: np.ndarray) -> float:
    if isinstance(model, HGBForecaster):
        predictions = model.predict_features(X)
    else:
        predictions = np.maximum(
            0.0,
            model.model.predict(
                (np.log1p(np.maximum(X[:, :60], 0.0)) / model.input_scale).reshape(-1, 60, 1),
                verbose=0,
            ).ravel(),
        )
    return float(np.mean(np.abs(predictions - y[: len(predictions)])))


def main(reuse_models: bool = False) -> None:
    """Train available models or revalidate existing artifacts and refresh metadata."""
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
    metadata_path = model_dir / "metadata.json"
    previous_metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if reuse_models and metadata_path.exists()
        else {}
    )
    results: dict[str, float | str] = {}
    for name, model, filename in (
        ("hgb", HGBForecaster(k=60, window_s=10.0), "hgb.joblib"),
        ("hgb_q90", HGBForecaster(quantile=0.9, k=60, window_s=10.0), "hgb_q90.joblib"),
    ):
        fit_start = time.perf_counter()
        if reuse_models:
            model = HGBForecaster.load(model_dir / filename)
        else:
            model.fit(X[train_mask], y[train_mask], groups[train_mask])
        validation_mae = _mae(model, X[val_mask], y[val_mask])
        if not reuse_models:
            model.save(model_dir / filename)
        results[name] = validation_mae
        activity = "validation_time_s" if reuse_models else "train_time_s"
        print(f"[train_forecasters] {name}: validation MAE={validation_mae:.6f}, {activity}={time.perf_counter() - fit_start:.1f}")

    try:
        gru_path = model_dir / "gru.keras"
        gru = GRUForecaster.load(gru_path) if reuse_models else GRUForecaster(k=60, window_s=10.0)
        fit_start = time.perf_counter()
        if not reuse_models:
            gru.fit(X[train_mask], y[train_mask], groups[train_mask])
        results["gru"] = _mae(gru, X[val_mask], y[val_mask])
        if not reuse_models:
            gru.save(gru_path)
        activity = "validation_time_s" if reuse_models else "train_time_s"
        print(f"[train_forecasters] gru: validation MAE={results['gru']:.6f}, {activity}={time.perf_counter() - fit_start:.1f}")
    except (FileNotFoundError, RuntimeError) as exc:
        results["gru"] = f"unavailable: {exc}"
        print(f"[train_forecasters] {exc}; skipping GRU")

    metadata = {
        **meta,
        "training_seeds": seeds[:160],
        "validation_seeds": seeds[160:],
        "validation_metrics": results,
        "training_time_s": (
            previous_metadata.get("training_time_s", 0.0)
            if reuse_models else time.perf_counter() - started
        ),
        "training_mode": "revalidated" if reuse_models else "trained",
        "library_versions": {
            name: _version(name)
            for name in ("numpy", "pandas", "scikit-learn", "joblib", "tensorflow")
        },
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"[train_forecasters] training_time_s={metadata['training_time_s']:.1f}")


def _version(name: str) -> str:
    candidates = (name, "tensorflow-cpu", "tensorflow_cpu") if name == "tensorflow" else (name,)
    for candidate in candidates:
        try:
            return metadata.version(candidate)
        except metadata.PackageNotFoundError:
            continue
    return "not installed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reuse-models",
        action="store_true",
        help="Recompute held-out validation metrics from existing model artifacts without retraining",
    )
    main(reuse_models=parser.parse_args().reuse_models)
