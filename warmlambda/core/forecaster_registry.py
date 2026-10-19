"""Named forecaster construction and model-file loading."""

from __future__ import annotations

from pathlib import Path

from warmlambda.core.forecaster import EWMAForecaster, SeasonalNaiveForecaster
from warmlambda.core.ml_forecaster import GRUForecaster, HGBForecaster


MODEL_DIR = Path(__file__).resolve().parents[2] / "models"


def default_model_name() -> str:
    """Prefer the trained q90 model, while keeping a fresh checkout usable."""
    return "hgb_q90" if (MODEL_DIR / "hgb_q90.joblib").exists() else "ewma"


def get_forecaster(name: str):
    """Return a named forecaster, loading trained models when required."""
    if name == "ewma":
        return EWMAForecaster(alpha=0.4)
    if name == "seasonal":
        return SeasonalNaiveForecaster(period_windows=60)
    if name in {"hgb", "hgb_q90"}:
        path = MODEL_DIR / f"{name}.joblib"
        if not path.exists():
            raise FileNotFoundError(
                f"Model file {path} is missing. Run `python -m experiments.train_forecasters` first."
            )
        return HGBForecaster.load(path)
    if name == "gru":
        path = MODEL_DIR / "gru.keras"
        if not path.exists():
            raise FileNotFoundError(
                f"Model file {path} is missing. Run `python -m experiments.train_forecasters` first."
            )
        return GRUForecaster.load(path)
    raise ValueError("Unknown forecaster {!r}; choose ewma, seasonal, hgb, hgb_q90, or gru".format(name))
