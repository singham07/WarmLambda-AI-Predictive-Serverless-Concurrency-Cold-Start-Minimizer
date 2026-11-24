"""
warmlambda.core.policies.reactive
=================================
Reactive warming policy that scales to current load.
"""

from __future__ import annotations

import math

from warmlambda.core.policies.base import Policy, SimState, TrafficHistory


class Reactive(Policy):
    """Scale warm instances reactively to the current load.

    The target is derived solely from the *current* simulator state (never
    from history or future knowledge):

        target = ceil((busy_instances + queue_length) * (1 + margin))

    Changes are limited to ``max_step`` per decision, and after a scale-up
    the policy waits ``cooldown_windows`` decision intervals before it is
    allowed to scale down again.  This avoids oscillation when load hovers
    near a threshold.

    Parameters
    ----------
    margin : float
        Headroom factor applied to the current busy + queued load.
    cooldown_windows : int
        Number of decision intervals to wait after a scale-up before scaling
        down is permitted again.
    max_step : int
        Maximum change in the target per decision (up or down).
    """

    def __init__(
        self,
        margin: float = 0.3,
        cooldown_windows: int = 2,
        max_step: int = 5,
    ) -> None:
        self.margin = margin
        self.cooldown_windows = cooldown_windows
        self.max_step = max_step
        self.name = "reactive"
        # Decision-interval cooldown counter remaining since the last scale-up.
        self._cooldown: int = 0

    def decide(self, history: TrafficHistory, state: SimState) -> int:  # noqa: ARG002
        """Return the reactive warm-instance target (see class docstring)."""
        current_load = state.busy_instances + state.queue_length
        desired = math.ceil(current_load * (1.0 + self.margin))

        held = state.held_target
        hi = held + self.max_step

        if self._cooldown > 0:
            # In cooldown: we may still scale up, but not down.
            lo = held
            self._cooldown -= 1
        else:
            lo = held - self.max_step

        new_target = min(max(desired, lo), hi)
        new_target = max(0, new_target)

        # Track whether we scaled up this tick (to start cooldown if needed).
        scaled_up = new_target > held

        if scaled_up and self.cooldown_windows > 0:
            self._cooldown = self.cooldown_windows - 1

        return new_target