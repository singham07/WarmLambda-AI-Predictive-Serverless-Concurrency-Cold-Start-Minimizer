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

from scipy.stats import poisson


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


def capacity_from_quantile(
    rate: float,
    mean_exec_s: float,
    max_instances: int,
    epsilon: float = 0.05,
    lead_time_s: float | None = None,
) -> int:
    """Return the smallest capacity whose Poisson overflow probability is <= epsilon.

    The Poisson mean is ``rate * execution_window_s``, where the effective
    execution window is bounded by the provisioning lead time when supplied.
    """
    if not math.isfinite(rate) or rate < 0.0:
        raise ValueError(f"rate must be finite and >= 0, got {rate!r}")
    if not math.isfinite(mean_exec_s) or mean_exec_s <= 0.0:
        raise ValueError(f"mean_exec_s must be finite and > 0, got {mean_exec_s!r}")
    if max_instances < 0:
        raise ValueError(f"max_instances must be >= 0, got {max_instances!r}")
    if not math.isfinite(epsilon) or not 0.0 < epsilon < 1.0:
        raise ValueError(f"epsilon must be finite and between 0 and 1, got {epsilon!r}")
    if lead_time_s is not None and (
        not math.isfinite(lead_time_s) or lead_time_s <= 0.0
    ):
        raise ValueError(
            f"lead_time_s must be finite and > 0, got {lead_time_s!r}"
        )
    if rate == 0.0 or max_instances == 0:
        return 0

    execution_window_s = (
        min(mean_exec_s, lead_time_s)
        if lead_time_s is not None
        else mean_exec_s
    )
    demand_mean = rate * execution_window_s
    demand_quantile = float(poisson.ppf(1.0 - epsilon, demand_mean))
    if not math.isfinite(demand_quantile):
        return max_instances
    return min(max_instances, max(0, math.ceil(demand_quantile)))
