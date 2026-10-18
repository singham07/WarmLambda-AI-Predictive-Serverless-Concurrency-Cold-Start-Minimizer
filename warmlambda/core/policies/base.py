"""
warmlambda.core.policies.base
==============================
Abstract interface shared by all warm-capacity policies.

Every policy receives two read-only snapshots at each decision tick:

* :class:`TrafficHistory` – past arrival counts, partitioned into equal-width
  windows.  Only *completed* windows are included; the current (in-progress)
  window is never exposed, so the history is always causally safe.
* :class:`SimState` – a point-in-time snapshot of the instance pool and queue.

The policy's :meth:`Policy.decide` method returns a single integer: the
number of warm instances the simulator should protect from idle expiry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TrafficHistory:
    """Observed arrival counts for all completed past decision windows.

    Attributes
    ----------
    window_s : float
        Duration of each counting window in seconds.  Equal to
        ``SimConfig.decision_interval_s``.
    counts : list[int]
        ``counts[i]`` is the number of requests that arrived in the window
        ``[i * window_s, (i+1) * window_s)``.  Only completed windows are
        included; no future or in-progress data is ever present.
    now : float
        Current simulation time in seconds (= the decision tick time).
    """

    window_s: float
    counts: list[int]
    now: float


@dataclass
class SimState:
    """Point-in-time snapshot of the simulator at a policy decision tick.

    Attributes
    ----------
    now : float
        Current simulation time in seconds.
    ready_instances : int
        Number of IDLE (warm, not executing) instances.
    busy_instances : int
        Number of BUSY (currently executing at least one request) instances.
    initializing_instances : int
        Number of INITIALIZING (cold-starting) instances.
    queue_length : int
        Effective number of requests waiting in the FIFO queue, excluding
        requests that have already timed out.
    held_target : int
        The warm-instance target that was set at the *previous* decision tick
        (0 at the start of the simulation).
    """

    now: float
    ready_instances: int
    busy_instances: int
    initializing_instances: int
    queue_length: int
    held_target: int


class Policy(ABC):
    """Abstract base class for all warm-capacity policies.

    Subclasses **must** define a class-level :attr:`name` string and
    implement :meth:`decide`.

    The simulator calls :meth:`decide` every ``cfg.decision_interval_s``
    seconds.  The return value becomes the new *held target*: the number of
    IDLE instances that are shielded from idle-timeout eviction.  BUSY and
    INITIALIZING instances are never evicted regardless of the target.

    Creating new instances
    ----------------------
    If the target exceeds the current total instance count, the simulator
    creates the difference as new INITIALIZING instances (cold-starting
    proactively).  These become IDLE after ``cfg.init_time_s`` seconds and
    will then count toward the protected pool.
    """

    name: str  # human-readable identifier, e.g. "no_warming"

    @abstractmethod
    def decide(self, history: TrafficHistory, state: SimState) -> int:
        """Return the target number of warm instances to hold.

        Parameters
        ----------
        history : TrafficHistory
            Arrival counts for every *completed* past window.
        state : SimState
            Current instance-pool and queue snapshot.

        Returns
        -------
        int
            Desired number of warm (IDLE) instances to protect from expiry.
            Must be >= 0.
        """
        ...
