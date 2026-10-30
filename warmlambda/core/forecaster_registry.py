"""Named forecaster construction and model-file loading."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from warmlambda.core.forecaster import EWMAForecaster, SeasonalNaiveForecaster
from warmlambda.core.ml_forecaster import GRUForecaster, RidgeForecaster


MODEL_DIR = Path(__file__).resolve().parents[2] / "models"


def default_model_name() -> str:
    """Prefer the trained q90 model, while keeping a fresh checkout usable."""
    return "ridge_q90" if (MODEL_DIR / "ridge_q90.npz").exists() else "ewma"


@lru_cache(maxsize=8)
def get_forecaster(name: str):
    """Return a named forecaster, loading trained models when required."""
    if name == "ewma":
        return EWMAForecaster(alpha=0.4)
    if name == "seasonal":
        return SeasonalNaiveForecaster(period_windows=60)
    if name in {"ridge", "ridge_q90"}:
        path = MODEL_DIR / f"{name}.npz"
        if not path.exists():
            raise FileNotFoundError(
                f"Model file {path} is missing. Run `python -m experiments.train_forecasters` first."
            )
        return RidgeForecaster.load(path)
    if name == "gru":
        path = MODEL_DIR / "gru.keras"
        if not path.exists():
            raise FileNotFoundError(
                f"Model file {path} is missing. Run `python -m experiments.train_forecasters` first."
            )
        return GRUForecaster.load(path)
    raise ValueError("Unknown forecaster {!r}; choose ewma, seasonal, ridge, ridge_q90, or gru".format(name))
