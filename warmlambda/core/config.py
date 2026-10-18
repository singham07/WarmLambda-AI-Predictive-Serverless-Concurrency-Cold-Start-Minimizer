"""
warmlambda.core.config
======================
Simulation configuration dataclass for WarmLambda AI.

All time values are in **seconds**; cost weights are dimensionless simulation
units (not real money).  The dataclass is *frozen* so that a ``SimConfig``
object can be safely shared across threads and used as a dict key.

Example
-------
>>> from warmlambda.core.config import SimConfig
>>> cfg = SimConfig(duration_s=7200, max_instances=50)
>>> cfg.duration_s
7200
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SimConfig:
    """Immutable configuration for a single WarmLambda simulation run.

    Parameters
    ----------
    duration_s : float
        Total wall-clock duration of the simulation in **seconds**.
        Must be > 0.  Default: ``3600`` (1 hour).
    init_time_s : float
        Cold-start (initialisation) latency added to the first invocation
        on a fresh instance, in **seconds**.  May be 0 (instantaneous cold
        start) but not negative.  Default: ``1.0``.
    mean_exec_s : float
        Mean execution time of a single function invocation in **seconds**,
        used as the μ parameter of the log-normal execution-time distribution.
        Must be > 0.  Default: ``0.2``.
    exec_sigma : float
        Standard deviation (σ) of the log-normal execution-time distribution,
        in **seconds**.  Controls how bursty individual invocations are.
        Must be > 0.  Default: ``0.5``.
    idle_timeout_s : float
        Time in **seconds** after which an idle (warm but not executing)
        instance is automatically evicted to free resources.  Must be > 0.
        Default: ``300.0`` (5 minutes).
    max_instances : int
        Hard upper limit on the number of concurrent instances the platform
        is allowed to maintain (warm + busy combined).  Must be >= 1.
        Default: ``100``.
    concurrency_per_instance : int
        Maximum number of invocations that can execute simultaneously on a
        single instance.  Use ``1`` for the standard AWS Lambda model (one
        request per container).  Must be >= 1.  Default: ``1``.
    queue_timeout_s : float
        Maximum time in **seconds** a queued invocation will wait for a
        free instance slot before being dropped (simulating a timeout /
        throttle error).  Must be > 0.  Default: ``10.0``.
    decision_interval_s : float
        Interval in **seconds** between successive policy decision ticks
        (e.g. how often a keep-alive policy re-evaluates which instances to
        keep warm).  Must be > 0.  Default: ``20``.
    warm_cost_weight : float
        Dimensionless cost multiplier applied per idle-second an instance
        spends in the *warm* (idle) state.  Higher values penalise keeping
        many instances warm.  Must be > 0.  Default: ``1.0``.
    busy_cost_weight : float
        Dimensionless cost multiplier applied per busy-second an instance
        spends executing an invocation.  Typically left at ``1.0`` as a
        baseline reference cost.  Must be > 0.  Default: ``1.0``.
    """

    # ------------------------------------------------------------------ #
    # Simulation horizon                                                   #
    # ------------------------------------------------------------------ #
    duration_s: float = 3600.0
    """Total simulation duration in seconds."""

    # ------------------------------------------------------------------ #
    # Execution-time distribution                                          #
    # ------------------------------------------------------------------ #
    init_time_s: float = 1.0
    """Cold-start initialisation latency in seconds (>= 0)."""

    mean_exec_s: float = 0.2
    """Mean invocation execution time in seconds (log-normal μ)."""

    exec_sigma: float = 0.5
    """Std-dev of invocation execution time in seconds (log-normal σ)."""

    # ------------------------------------------------------------------ #
    # Instance lifecycle                                                   #
    # ------------------------------------------------------------------ #
    idle_timeout_s: float = 300.0
    """Seconds before an idle warm instance is evicted."""

    max_instances: int = 100
    """Hard cap on total concurrent instances (warm + busy)."""

    concurrency_per_instance: int = 1
    """Max simultaneous invocations per instance."""

    # ------------------------------------------------------------------ #
    # Queue behaviour                                                      #
    # ------------------------------------------------------------------ #
    queue_timeout_s: float = 10.0
    """Max wait time in seconds before a queued request is dropped."""

    # ------------------------------------------------------------------ #
    # Policy clock                                                         #
    # ------------------------------------------------------------------ #
    decision_interval_s: float = 20.0
    """Seconds between policy decision ticks."""

    # ------------------------------------------------------------------ #
    # Cost model                                                           #
    # ------------------------------------------------------------------ #
    warm_cost_weight: float = 1.0
    """Cost multiplier per idle-second (warm state)."""

    busy_cost_weight: float = 1.0
    """Cost multiplier per busy-second (executing state)."""

    # ------------------------------------------------------------------ #
    # Validation                                                           #
    # ------------------------------------------------------------------ #
    def __post_init__(self) -> None:
        """Validate all field values after construction.

        Raises
        ------
        ValueError
            If any numeric field violates its domain constraint.
        """
        # Fields that must be strictly positive (> 0)
        positive_fields: dict[str, float] = {
            "duration_s": self.duration_s,
            "mean_exec_s": self.mean_exec_s,
            "exec_sigma": self.exec_sigma,
            "idle_timeout_s": self.idle_timeout_s,
            "concurrency_per_instance": self.concurrency_per_instance,
            "queue_timeout_s": self.queue_timeout_s,
            "decision_interval_s": self.decision_interval_s,
            "warm_cost_weight": self.warm_cost_weight,
            "busy_cost_weight": self.busy_cost_weight,
        }
        for name, value in positive_fields.items():
            if value <= 0:
                raise ValueError(
                    f"SimConfig.{name} must be > 0, got {value!r}."
                )

        # init_time_s may be 0 (instantaneous cold start) but not negative
        if self.init_time_s < 0:
            raise ValueError(
                f"SimConfig.init_time_s must be >= 0, got {self.init_time_s!r}."
            )

        # max_instances must be at least 1
        if self.max_instances < 1:
            raise ValueError(
                f"SimConfig.max_instances must be >= 1, got {self.max_instances!r}."
            )
