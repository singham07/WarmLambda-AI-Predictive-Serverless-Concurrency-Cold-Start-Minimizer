"""Evaluate statistical and trained forecasters on standard and unseen traces."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np

from warmlambda.core.config import SimConfig
from warmlambda.core.forecaster import (
    EWMAForecaster,
    SeasonalNaiveForecaster,
    bin_trace_to_windows,
)
from warmlambda.core.forecaster_registry import get_forecaster
from warmlambda.core.ml_dataset import counts_to_features
from warmlambda.core.ml_forecaster import GRUForecaster, RidgeForecaster
from warmlambda.core.traffic import SCENARIOS, generate_trace


def _score(forecaster, counts: list[int], window_s: float, q90: bool = False) -> dict[str, float]:
    actual = np.asarray(counts[1:], dtype=float) / window_s
    if isinstance(forecaster, RidgeForecaster):
        features = np.asarray(
            [counts_to_features(np.asarray(counts, dtype=np.float32), index, forecaster.k) for index in range(1, len(counts))]
        )
        predictions = forecaster.predict_features(features)
    elif isinstance(forecaster, GRUForecaster):
        features = np.asarray(
            [counts_to_features(np.asarray(counts, dtype=np.float32), index, forecaster.k)[:forecaster.k] for index in range(1, len(counts))]
        )
        predictions = np.maximum(
            0.0,
            forecaster.model.predict(
                (np.log1p(features) / forecaster.input_scale).reshape(-1, forecaster.k, 1),
                verbose=0,
            ).ravel(),
        )
    else:
        predictions = np.asarray(
            [forecaster.predict(counts[:index], window_s) for index in range(1, len(counts))],
            dtype=float,
        )
    error = np.abs(predictions - actual)
    denominator = np.abs(predictions) + np.abs(actual)
    smape = np.mean(np.divide(2.0 * error, denominator, out=np.zeros_like(error), where=denominator > 0))
    result = {
        "mae": float(np.mean(error)),
        "smape": float(smape),
        "under_prediction_rate": float(np.mean(predictions < actual)),
    }
    if q90:
        result["pinball_loss"] = float(np.mean(np.maximum(0.9 * (actual - predictions), (0.9 - 1.0) * (actual - predictions))))
    return result


def main() -> None:
    """Write per-trace metrics and print means for both test distributions."""
    results_dir = Path(__file__).resolve().parents[1] / "results"
    results_dir.mkdir(exist_ok=True)
    window_s = 10.0
    model_factories = {
        "ewma": lambda: EWMAForecaster(alpha=0.4),
        "ewma_trend": lambda: EWMAForecaster(alpha=0.4, trend=True, beta=0.2),
        "seasonal": lambda: SeasonalNaiveForecaster(period_windows=60),
    }
    for name in ("ridge", "ridge_q90", "gru"):
        try:
            model_factories[name] = lambda name=name: get_forecaster(name)
        except Exception:
            pass

    rows: list[dict[str, object]] = []
    available_models = {}
    for name, factory in model_factories.items():
        try:
            available_models[name] = factory()
        except FileNotFoundError as exc:
            print(f"[eval_forecasters] skipping {name}: {exc}")

    for dataset, seeds, randomize in (
        ("standard", range(20), False),
        ("unseen", range(2000, 2020), True),
    ):
        for scenario in SCENARIOS:
            for seed in seeds:
                cfg = SimConfig()
                trace = generate_trace(scenario, cfg, seed, randomize=randomize)
                counts = bin_trace_to_windows(trace, cfg.duration_s, window_s)
                for name, model in available_models.items():
                    metrics = _score(model, counts, window_s, q90=name == "ridge_q90")
                    rows.append({"dataset": dataset, "scenario": scenario, "seed": seed, "forecaster": name, **metrics})

    fieldnames = ["dataset", "scenario", "seed", "forecaster", "mae", "smape", "under_prediction_rate", "pinball_loss"]
    with (results_dir / "forecast_eval.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})

    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["dataset"]), str(row["scenario"]), str(row["forecaster"]))].append(row)
    print("dataset | scenario | forecaster | MAE | sMAPE | under_prediction_rate | q90_pinball")
    print("--------+----------+------------+-----+-------+------------------------+------------")
    for key, values in sorted(grouped.items()):
        means = {
            metric: np.mean([float(value[metric]) for value in values if metric in value])
            for metric in ("mae", "smape", "under_prediction_rate", "pinball_loss")
            if any(metric in value for value in values)
        }
        print(
            f"{key[0]:8} | {key[1]:8} | {key[2]:10} | {means['mae']:.4f} | "
            f"{means['smape']:.4f} | {means['under_prediction_rate']:.4f} | "
            f"{means.get('pinball_loss', float('nan')):.4f}"
        )
    print(f"[eval_forecasters] Wrote {len(rows)} rows to {results_dir / 'forecast_eval.csv'}")


if __name__ == "__main__":
    main()
