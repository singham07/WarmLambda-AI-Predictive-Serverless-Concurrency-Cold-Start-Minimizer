"""
warmlambda.core.capacity
========================
Capacity calculations using Little's Law for WarmLambda AI.

Little's Law states that for a stationary queuing system:

    L = λ * W

where:
- L is the average number of concurrent requests in the system,
- λ is the arrival rate (requests per second),
- W is the average time a request spends in the system (mean execution time, seconds).

To ensure that arrivals can be handled warm with high probability, WarmLambda
provisions warm capacity according to Little's law plus a configurable safety
margin (headroom):

    target_instances = min(max_instances, ceil(rate * mean_exec_s * (1 + headroom)))
"""

from __future__ import annotations

import math


def capacity_from_rate(
    rate: float,
    mean_exec_s: float,
    headroom: float,
    max_instances: int,
) -> int:
    """Compute required warm instance capacity from arrival rate via Little's Law.

    Parameters
    ----------
    rate : float
        Forecasted or observed arrival rate in requests per second (must be >= 0.0).
    mean_exec_s : float
        Mean execution duration per request in seconds (must be >= 0.0).
    headroom : float
        Safety headroom margin (e.g. 0.5 for 50 % headroom above Little's Law).
    max_instances : int
        Maximum instance limit permitted by the simulation configuration.

    Returns
    -------
    int
        Target integer warm instances in [0, max_instances].
    """
    if rate <= 0.0 or mean_exec_s <= 0.0:
        return 0

    required_concurrency = rate * mean_exec_s * (1.0 + max(0.0, headroom))
    target = math.ceil(required_concurrency)
    return max(0, min(max_instances, target))
