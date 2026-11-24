"""
warmlambda.core.policies.fixed
==============================
Fixed warming policy that always returns a constant number of warm instances.
"""

from __future__ import annotations

from warmlambda.core.policies.base import Policy, SimState, TrafficHistory


class FixedWarming(Policy):
    """Always return a fixed number n as the warm-instance target.

    The policy ignores history and state and simply returns the constant
    value ``n`` supplied at construction.  Useful as a baseline and for
    sensitivity analysis.

    Parameters
    ----------
    n : int
        Constant target number of warm (IDLE) instances to hold.
        Must be >= 0.
    """

    def __init__(self, n: int) -> None:
        if n < 0:
            raise ValueError("FixedWarming n must be >= 0")
        self.n = n
        self.name = f"fixed_{n}"

    def decide(self, history: TrafficHistory, state: SimState) -> int:  # noqa: ARG002
        return self.n