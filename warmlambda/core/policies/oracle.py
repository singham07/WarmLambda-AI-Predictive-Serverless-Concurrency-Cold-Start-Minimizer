"""
warmlambda.core.policies.oracle
================================
Oracle bound — CHEATS by looking at the true future.
"""

from __future__ import annotations

import math

from warmlambda.core.config import SimConfig
from warmlambda.core.policies.base import Policy, SimState, TrafficHistory
from warmlambda.core.traffic import Request


class Oracle(Policy):
    """Unreachable upper bound that CHEATS by looking at future arrivals.

    .. WARNING::

        THIS IS NOT A REAL POLICY.  It receives the complete trace (including
        arrivals that have not happened yet) and therefore represents an
        UNREACHABLE UPPER BOUND on what any causal warm-capacity policy could
        achieve.  DO NOT use it in production and DO NOT compare it as a peer
        to real policies.

    At each decision tick the oracle counts the arrivals in the next two
    decision intervals and sets

        target = ceil(future_rate * mean_exec_s * 1.2)

    where ``future_rate`` is the arrival rate (req/s) over that look-ahead
    window and the factor 1.2 is a small headroom margin.
    """

    LOOKAHEAD_INTERVALS = 2
    HEADROOM = 1.2

    def __init__(self, trace: list[Request], cfg: SimConfig) -> None:
        self.trace = trace
        self.cfg = cfg
        self.name = "oracle"

    def decide(self, history: TrafficHistory, state: SimState) -> int:  # noqa: ARG002
        """Return the oracle warm-instance target (see class docstring)."""
        horizon = self.LOOKAHEAD_INTERVALS * self.cfg.decision_interval_s
        t0 = state.now
        t1 = t0 + horizon
        future_arrivals = sum(
            1 for req in self.trace if t0 <= req.arrival_s < t1
        )
        future_rate = future_arrivals / horizon if horizon > 0 else 0.0
        target = math.ceil(future_rate * self.cfg.mean_exec_s * self.HEADROOM)
        return max(0, target)