"""
warmlambda.core.policies.no_warming
=====================================
Baseline policy that never pre-warms any instances.

Use this as a lower-bound comparison: every request triggers a cold start
unless an instance happens to still be alive from a previous execution within
the idle-timeout window.
"""

from __future__ import annotations

from warmlambda.core.policies.base import Policy, SimState, TrafficHistory


class NoWarming(Policy):
    """Always return 0 as the warm-instance target.

    The simulator will never create proactive instances, and idle instances
    expire after ``cfg.idle_timeout_s`` with no protection.  This maximises
    cold-start count while minimising idle-instance cost.
    """

    name = "no_warming"

    def decide(self, history: TrafficHistory, state: SimState) -> int:  # noqa: ARG002
        return 0
