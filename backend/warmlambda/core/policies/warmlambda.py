"""
warmlambda.core.policies.warmlambda
===================================
Forecast-based proactive warm capacity policy for WarmLambda AI.
"""

from __future__ import annotations

from typing import Optional

from warmlambda.core.capacity import capacity_from_rate
from warmlambda.core.config import SimConfig
from warmlambda.core.forecaster import Forecaster
from warmlambda.core.policies.base import Policy, SimState, TrafficHistory


class WarmLambdaPolicy(Policy):
    """Proactive serverless warming policy driven by traffic rate forecasting.

    At each decision interval, WarmLambda queries the underlying :class:`Forecaster`
    using ONLY completed past window arrival counts (:attr:`TrafficHistory.counts`).
    The forecasted arrival rate is then mapped to required warm instances using
    Little's Law with a configurable safety headroom margin:

        target = capacity_from_rate(rate, cfg.mean_exec_s, headroom, cfg.max_instances)

    Parameters
    ----------
    forecaster : Forecaster
        Statistical or machine learning rate forecaster.
    cfg : SimConfig
        Simulator configuration providing service characteristics (mean_exec_s,
        max_instances).
    headroom : float, default 0.5
        Proactive capacity safety headroom multiplier above expected concurrency.
    name : str, optional
        Custom policy identifier. Defaults to ``"warmlambda_forecast"``.
    """

    def __init__(
        self,
        forecaster: Forecaster,
        cfg: SimConfig,
        headroom: float = 0.5,
        name: Optional[str] = None,
    ) -> None:
        self.forecaster = forecaster
        self.cfg = cfg
        self.headroom = float(headroom)
        self.name = name if name is not None else "warmlambda_forecast"
        self.last_forecast_rate: Optional[float] = None

    def decide(self, history: TrafficHistory, state: SimState) -> int:  # noqa: ARG002
        """Forecast rate from past counts and compute warm target via Little's Law."""
        if not history.counts:
            # A single causal bootstrap instance prevents the first burst from
            # being entirely exposed to cold-start latency.
            return 1
        rate = self.forecaster.predict(history.counts, history.window_s)
        self.last_forecast_rate = rate
        return capacity_from_rate(
            rate=rate,
            mean_exec_s=self.cfg.mean_exec_s,
            headroom=self.headroom,
            max_instances=self.cfg.max_instances,
        )
