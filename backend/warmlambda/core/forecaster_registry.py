"""Named forecaster construction and model-file loading."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from backend.warmlambda.core.forecaster import (
    EWMAForecaster,
    PersistenceForecaster,
    SeasonalNaiveForecaster,
)
from backend.warmlambda.core.ml_forecaster import GRUForecaster, HGBForecaster


MODEL_DIR = Path(__file__).resolve().parents[3] / "models"


def default_model_name() -> str:
    """Return the default trained forecaster; missing artifacts are errors."""
    return "hgb_q90"


@lru_cache(maxsize=16)
def get_forecaster(
    name: str, period_windows: int = 60
):
    """Return a named forecaster, loading trained models when required."""
    if name == "ewma":
        return EWMAForecaster(alpha=0.4)
    if name == "ewma_trend":
        return EWMAForecaster(alpha=0.4, trend=True, beta=0.2)
    if name == "seasonal":
        return SeasonalNaiveForecaster(period_windows=period_windows)
    if name == "persistence":
        return PersistenceForecaster()
    if name in {"hgb", "hgb_q90"}:
        path = MODEL_DIR / f"{name}.joblib"
        if not path.exists():
            raise FileNotFoundError(
                f"Model file {path} is missing. Run `python -m experiments.train_forecasters` first."
            )
        forecaster = HGBForecaster.load(path)
        if forecaster.name != name:
            raise ValueError(
                f"Model file {path} contains {forecaster.name}, expected {name}"
            )
        return forecaster
    if name == "gru":
        path = MODEL_DIR / "gru.keras"
        if not path.exists():
            raise FileNotFoundError(
                f"Model file {path} is missing. Run `python -m experiments.train_forecasters` first."
            )
        return GRUForecaster.load(path)
    raise ValueError(
        "Unknown forecaster {!r}; choose hgb, hgb_q90, ewma, ewma_trend, "
        "seasonal, persistence, or gru".format(name)
    )
