"""
warmlambda.core.simulator
=========================
Discrete-event simulator for serverless cold-start behaviour.

The simulator is **deterministic**: given the same trace, policy, and
configuration it always produces an identical :class:`SimResult`.  All
randomness lives in the traffic generator; the simulator itself never
draws random numbers.

Events are managed via :mod:`heapq` (a min-heap keyed on simulated time).
The simulator never sleeps — it jumps from event to event in zero
wall-clock time.

Instance lifecycle
------------------
Each instance moves through:  ``INITIALIZING → IDLE ↔ BUSY``.

* **INITIALIZING** — cold-starting; lasts ``cfg.init_time_s`` seconds.
* **IDLE** — ready to serve a request immediately (warm start).
* **BUSY** — executing one or more requests (up to
  ``cfg.concurrency_per_instance``).

If a request arrives when no slot is available and total instances <
``cfg.max_instances``, a new instance is created (cold start).  Otherwise
the request enters a FIFO queue; if it waits > ``cfg.queue_timeout_s`` it
is dropped.
"""

from __future__ import annotations

import heapq
import math
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import Optional

import numpy as np

from warmlambda.core.config import SimConfig
from warmlambda.core.policies.base import Policy, SimState, TrafficHistory
from warmlambda.core.traffic import Request


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class _EventType(IntEnum):
    INITIAL_POLICY_TICK = auto()
    REQUEST_ARRIVAL = auto()
    REQUEST_FINISH = auto()
    INSTANCE_READY = auto()      # cold-start finished
    IDLE_EXPIRY_CHECK = auto()   # idle timeout expired
    POLICY_TICK = auto()
    QUEUE_TIMEOUT = auto()


@dataclass(order=True)
class _Event:
    """Priority-queue entry.  Ordered by *time*, then *kind* ordinal."""
    time: float
    kind: _EventType = field(compare=True)
    # Payload fields — not used in ordering
    request_id: int = field(default=-1, compare=False)
    instance_id: int = field(default=-1, compare=False)


# ---------------------------------------------------------------------------
# Instance state machine
# ---------------------------------------------------------------------------

class _InstanceState(IntEnum):
    INITIALIZING = auto()
    IDLE = auto()
    BUSY = auto()


@dataclass
class _Instance:
    id: int
    state: _InstanceState
    active_requests: int = 0       # how many requests currently running
    idle_since: float = 0.0        # when the instance last became IDLE
    pending_request_id: int = -1   # request waiting for init to finish


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RequestRecord:
    """Per-request outcome produced by the simulator."""
    id: int
    arrival_s: float
    start_s: Optional[float]     # None when dropped
    finish_s: Optional[float]    # None when dropped
    cold: bool
    dropped: bool
    latency_s: Optional[float]   # None when dropped


@dataclass(frozen=True)
class IntervalRecord:
    """Snapshot captured at every policy decision tick."""
    t: float
    target: int
    ready: int
    busy: int
    initializing: int
    queue_length: int
    arrivals_in_window: int
    t_start: float = 0.0
    t_end: float = 0.0
    observed_requests: int = 0
    predicted_requests: Optional[float] = None
    recommended_warm: int = 0
    ready_instances: int = 0
    cold_starts: int = 0
    avg_latency_s: Optional[float] = None
    p95_latency_s: Optional[float] = None
    dropped_requests: int = 0
    interval_cost: float = 0.0
    shortfall: int = 0
    forecast_rate: Optional[float] = None
    budget_clamped: bool = False


@dataclass
class SimResult:
    """Complete output of a single simulation run.

    Attributes
    ----------
    requests : list[RequestRecord]
        One entry per input request.
    intervals : list[IntervalRecord]
        One entry per policy decision tick.
    busy_seconds : float
        Total instance-seconds spent in BUSY state.
    idle_warm_seconds : float
        Total instance-seconds spent in IDLE (warm) state.
    init_seconds : float
        Total instance-seconds spent in INITIALIZING state.
    """
    requests: list[RequestRecord] = field(default_factory=list)
    intervals: list[IntervalRecord] = field(default_factory=list)
    busy_seconds: float = 0.0
    idle_warm_seconds: float = 0.0
    init_seconds: float = 0.0
    policy_created_instances: int = 0
    on_demand_created_instances: int = 0


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

def simulate(
    trace: list[Request],
    policy: Policy,
    cfg: SimConfig,
) -> SimResult:
    """Run a deterministic discrete-event simulation.

    Parameters
    ----------
    trace : list[Request]
        Sorted list of requests (from :func:`generate_trace` or hand-built).
    policy : Policy
        Warm-capacity policy to evaluate.
    cfg : SimConfig
        Simulation configuration.

    Returns
    -------
    SimResult
        Full accounting of every request and every policy-tick interval.
    """
    # ----- bookkeeping -----
    heap: list[_Event] = []
    instances: dict[int, _Instance] = {}
    next_instance_id = 0
    held_target = 0  # current policy target

    # Queue: list of (request_id, arrival_time)
    queue: deque[tuple[int, float]] = deque()
    # Track which queued requests have already been dropped
    dropped_set: set[int] = set()

    # Request metadata for building final RequestRecord
    req_meta: dict[int, dict] = {}  # req_id -> {arrival, start, finish, cold, dropped}

    # Arrival counting for TrafficHistory
    arrival_counts: list[int] = []  # counts[i] = arrivals in [i*dt, (i+1)*dt)
    decision_dt = cfg.decision_interval_s

    # Instance-second accounting: track state-entry times
    inst_busy_enter: dict[int, float] = {}   # inst_id -> time entered BUSY
    inst_idle_enter: dict[int, float] = {}   # inst_id -> time entered IDLE
    inst_init_enter: dict[int, float] = {}   # inst_id -> time entered INIT

    total_busy_s = 0.0
    total_idle_s = 0.0
    total_init_s = 0.0
    policy_created_instances = 0
    on_demand_created_instances = 0

    intervals: list[IntervalRecord] = []
    interval_costs = {
        "busy": [0.0] * int(math.ceil(cfg.duration_s / decision_dt)),
        "idle": [0.0] * int(math.ceil(cfg.duration_s / decision_dt)),
        "init": [0.0] * int(math.ceil(cfg.duration_s / decision_dt)),
    }

    # ----- helper: count alive instances -----
    def _count_by_state(st: _InstanceState) -> int:
        return sum(1 for inst in instances.values() if inst.state == st)

    def _total_instances() -> int:
        return len(instances)

    # ----- helper: find an instance with a free slot -----
    def _find_free_instance() -> Optional[_Instance]:
        # Prefer IDLE instances first (true warm start), then BUSY with spare slots
        best: Optional[_Instance] = None
        for inst in instances.values():
            if inst.state == _InstanceState.IDLE:
                return inst
            if (
                inst.state == _InstanceState.BUSY
                and inst.active_requests < cfg.concurrency_per_instance
            ):
                if best is None or inst.active_requests < best.active_requests:
                    best = inst
        return best

    # ----- helper: flush instance accounting when state changes -----
    def _flush_instance_time(inst: _Instance, now: float) -> None:
        nonlocal total_busy_s, total_idle_s, total_init_s
        iid = inst.id
        if iid in inst_busy_enter:
            start = inst_busy_enter.pop(iid)
            duration = max(0.0, min(now, cfg.duration_s) - start)
            total_busy_s += duration
            _account_interval("busy", start, now)
        if iid in inst_idle_enter:
            start = inst_idle_enter.pop(iid)
            duration = max(0.0, min(now, cfg.duration_s) - start)
            total_idle_s += duration
            _account_interval("idle", start, now)
        if iid in inst_init_enter:
            start = inst_init_enter.pop(iid)
            duration = max(0.0, min(now, cfg.duration_s) - start)
            total_init_s += duration
            _account_interval("init", start, now)

    def _account_interval(kind: str, start: float, end: float) -> None:
        """Attribute an instance-state segment to each overlapping interval."""
        clipped_start = max(0.0, start)
        clipped_end = min(cfg.duration_s, end)
        if clipped_end <= clipped_start:
            return
        first = int(clipped_start / decision_dt)
        last = min(len(interval_costs[kind]) - 1, int((clipped_end - 1e-12) / decision_dt))
        if first == last:
            interval_costs[kind][first] += clipped_end - clipped_start
            return
        for index in range(first, last + 1):
            overlap_start = max(clipped_start, index * decision_dt)
            overlap_end = min(clipped_end, (index + 1) * decision_dt)
            if overlap_end > overlap_start:
                interval_costs[kind][index] += overlap_end - overlap_start

    # ----- helper: set instance state and record entry time -----
    def _set_state(inst: _Instance, new_state: _InstanceState, now: float) -> None:
        _flush_instance_time(inst, now)
        inst.state = new_state
        iid = inst.id
        if new_state == _InstanceState.BUSY:
            inst_busy_enter[iid] = now
        elif new_state == _InstanceState.IDLE:
            inst_idle_enter[iid] = now
            inst.idle_since = now
        elif new_state == _InstanceState.INITIALIZING:
            inst_init_enter[iid] = now

    # ----- helper: create a new instance (cold start) -----
    def _create_instance(now: float, pending_req_id: int = -1) -> _Instance:
        nonlocal next_instance_id, policy_created_instances, on_demand_created_instances
        if pending_req_id >= 0:
            on_demand_created_instances += 1
        else:
            policy_created_instances += 1
        iid = next_instance_id
        next_instance_id += 1
        inst = _Instance(
            id=iid,
            state=_InstanceState.INITIALIZING,
            pending_request_id=pending_req_id,
        )
        instances[iid] = inst
        inst_init_enter[iid] = now
        # Schedule INSTANCE_READY event
        heapq.heappush(heap, _Event(
            time=now + cfg.init_time_s,
            kind=_EventType.INSTANCE_READY,
            instance_id=iid,
        ))
        return inst

    # ----- helper: remove an instance -----
    def _remove_instance(inst: _Instance, now: float) -> None:
        _flush_instance_time(inst, now)
        del instances[inst.id]

    # ----- helper: dispatch a request to an instance (warm start) -----
    def _dispatch_warm(req_id: int, inst: _Instance, now: float) -> None:
        inst.active_requests += 1
        if inst.state == _InstanceState.IDLE:
            _set_state(inst, _InstanceState.BUSY, now)
        # If already BUSY, just increment active_requests (already accounted)

        exec_s = req_meta[req_id]["exec_s"]
        finish_time = now + exec_s
        req_meta[req_id]["start_s"] = now
        req_meta[req_id]["finish_s"] = finish_time
        req_meta[req_id]["cold"] = False
        req_meta[req_id]["latency_s"] = finish_time - req_meta[req_id]["arrival"]

        heapq.heappush(heap, _Event(
            time=finish_time,
            kind=_EventType.REQUEST_FINISH,
            request_id=req_id,
            instance_id=inst.id,
        ))

    # ----- helper: try to serve the next queued request -----
    def _try_dequeue(inst: _Instance, now: float) -> bool:
        while queue:
            req_id, _arr = queue[0]
            if req_id in dropped_set:
                queue.popleft()
                continue
            # Still valid — dispatch it
            queue.popleft()
            _dispatch_warm(req_id, inst, now)
            return True
        return False

    # ----- helper: get arrivals-in-window count -----
    def _arrivals_in_window(window_idx: int) -> int:
        if 0 <= window_idx < len(arrival_counts):
            return arrival_counts[window_idx]
        return 0

    # ----- helper: record arrival in the right window -----
    def _record_arrival(t: float) -> None:
        idx = int(t / decision_dt)
        while len(arrival_counts) <= idx:
            arrival_counts.append(0)
        arrival_counts[idx] += 1

    # ----- seed the event heap -----
    # Give proactive policies a causal bootstrap decision before traffic
    # starts.  The history is empty, so this cannot use future arrivals.
    heapq.heappush(heap, _Event(time=0.0, kind=_EventType.INITIAL_POLICY_TICK))
    for req in trace:
        req_meta[req.id] = {
            "arrival": req.arrival_s,
            "exec_s": req.exec_s,
            "start_s": None,
            "finish_s": None,
            "cold": False,
            "dropped": False,
            "latency_s": None,
        }
        heapq.heappush(heap, _Event(
            time=req.arrival_s,
            kind=_EventType.REQUEST_ARRIVAL,
            request_id=req.id,
        ))

    # Schedule policy ticks
    t_tick = decision_dt
    while t_tick <= cfg.duration_s + decision_dt:
        heapq.heappush(heap, _Event(
            time=t_tick,
            kind=_EventType.POLICY_TICK,
        ))
        t_tick += decision_dt

    # ----- main event loop -----
    while heap:
        event = heapq.heappop(heap)
        now = event.time

        if event.kind == _EventType.REQUEST_ARRIVAL:
            req_id = event.request_id
            _record_arrival(now)

            # 1) Try warm start on an existing instance
            free_inst = _find_free_instance()
            if free_inst is not None:
                _dispatch_warm(req_id, free_inst, now)

            # 2) Else create a new instance if under cap
            elif _total_instances() < cfg.max_instances:
                inst = _create_instance(now, pending_req_id=req_id)
                req_meta[req_id]["cold"] = True

            # 3) Else enqueue
            else:
                queue.append((req_id, now))
                # Schedule queue timeout check
                heapq.heappush(heap, _Event(
                    time=now + cfg.queue_timeout_s,
                    kind=_EventType.QUEUE_TIMEOUT,
                    request_id=req_id,
                ))

        elif event.kind == _EventType.INSTANCE_READY:
            inst_id = event.instance_id
            if inst_id not in instances:
                continue
            inst = instances[inst_id]
            if inst.state != _InstanceState.INITIALIZING:
                continue

            pending_req = inst.pending_request_id
            inst.pending_request_id = -1

            if pending_req >= 0 and not req_meta[pending_req]["dropped"]:
                # Serve the pending cold-start request
                _set_state(inst, _InstanceState.BUSY, now)
                inst.active_requests = 1

                exec_s = req_meta[pending_req]["exec_s"]
                finish_time = now + exec_s
                req_meta[pending_req]["start_s"] = now
                req_meta[pending_req]["finish_s"] = finish_time
                req_meta[pending_req]["cold"] = True
                req_meta[pending_req]["latency_s"] = (
                    finish_time - req_meta[pending_req]["arrival"]
                )

                heapq.heappush(heap, _Event(
                    time=finish_time,
                    kind=_EventType.REQUEST_FINISH,
                    request_id=pending_req,
                    instance_id=inst.id,
                ))
            else:
                # No pending request — go IDLE and try dequeue
                _set_state(inst, _InstanceState.IDLE, now)
                if not _try_dequeue(inst, now):
                    # Schedule idle expiry check
                    heapq.heappush(heap, _Event(
                        time=now + cfg.idle_timeout_s,
                        kind=_EventType.IDLE_EXPIRY_CHECK,
                        instance_id=inst.id,
                    ))

        elif event.kind == _EventType.REQUEST_FINISH:
            req_id = event.request_id
            inst_id = event.instance_id
            if inst_id not in instances:
                continue
            inst = instances[inst_id]

            inst.active_requests = max(0, inst.active_requests - 1)

            if inst.active_requests == 0:
                # Instance is now free — try to serve from queue
                if not _try_dequeue(inst, now):
                    _set_state(inst, _InstanceState.IDLE, now)
                    # Schedule idle expiry check
                    heapq.heappush(heap, _Event(
                        time=now + cfg.idle_timeout_s,
                        kind=_EventType.IDLE_EXPIRY_CHECK,
                        instance_id=inst.id,
                    ))
            # else: still BUSY with other requests

        elif event.kind == _EventType.QUEUE_TIMEOUT:
            req_id = event.request_id
            meta = req_meta[req_id]
            # Drop only if not yet started
            if meta["start_s"] is None and not meta["dropped"]:
                meta["dropped"] = True
                meta["latency_s"] = None
                dropped_set.add(req_id)

        elif event.kind == _EventType.IDLE_EXPIRY_CHECK:
            if now > cfg.duration_s:
                continue
            inst_id = event.instance_id
            if inst_id not in instances:
                continue
            inst = instances[inst_id]
            if inst.state != _InstanceState.IDLE:
                continue
            # Check if this instance has been idle long enough
            idle_duration = now - inst.idle_since
            if idle_duration < cfg.idle_timeout_s - 1e-9:
                continue

            # Check if instance is protected by the held target
            idle_instances = sorted(
                (i for i in instances.values() if i.state == _InstanceState.IDLE),
                key=lambda i: i.idle_since,  # oldest first
            )
            # Protect held_target most-recently-idle instances
            protected_ids: set[int] = set()
            if held_target > 0:
                # Keep the most recently idle ones (freshest)
                newest_idle = sorted(
                    idle_instances,
                    key=lambda i: i.idle_since,
                    reverse=True,
                )
                for pi in newest_idle[:held_target]:
                    protected_ids.add(pi.id)

            if inst.id in protected_ids:
                # Re-schedule the check — instance is protected
                if now + cfg.idle_timeout_s <= cfg.duration_s:
                    heapq.heappush(heap, _Event(
                        time=now + cfg.idle_timeout_s,
                        kind=_EventType.IDLE_EXPIRY_CHECK,
                        instance_id=inst.id,
                    ))
            else:
                _remove_instance(inst, now)

        elif event.kind in (_EventType.INITIAL_POLICY_TICK, _EventType.POLICY_TICK):
            # Build TrafficHistory: only completed past windows
            n_completed = int(now / decision_dt)
            completed_counts = [
                _arrivals_in_window(i)
                for i in range(n_completed)
            ]
            history = TrafficHistory(
                window_s=decision_dt,
                counts=completed_counts,
                now=now,
            )

            state = SimState(
                now=now,
                ready_instances=_count_by_state(_InstanceState.IDLE),
                busy_instances=_count_by_state(_InstanceState.BUSY),
                initializing_instances=_count_by_state(_InstanceState.INITIALIZING),
                queue_length=sum(
                    1 for rid, _ in queue if rid not in dropped_set
                ),
                held_target=held_target,
            )

            new_target = max(0, policy.decide(history, state))
            old_target = held_target
            held_target = new_target

            # Record interval
            current_window = n_completed  # the window that is in-progress
            intervals.append(IntervalRecord(
                t=now,
                target=new_target,
                ready=state.ready_instances,
                busy=state.busy_instances,
                initializing=state.initializing_instances,
                queue_length=state.queue_length,
                arrivals_in_window=_arrivals_in_window(
                    max(0, n_completed - 1)
                ),
                forecast_rate=getattr(policy, "last_forecast_rate", None),
                budget_clamped=getattr(policy, "last_budget_clamped", False),
            ))

            # If target exceeds current total instances, create new ones
            total = _total_instances()
            if new_target > total:
                for _ in range(new_target - total):
                    if _total_instances() < cfg.max_instances:
                        _create_instance(now)

    # ----- build final SimResult -----
    # Flush remaining instance times at the end of simulation
    end_time = cfg.duration_s
    # Find actual end time (max of all events processed)
    for rid, meta in req_meta.items():
        if meta["finish_s"] is not None:
            end_time = max(end_time, meta["finish_s"])

    for inst in list(instances.values()):
        _flush_instance_time(inst, end_time)

    request_records = [
        RequestRecord(
            id=rid,
            arrival_s=meta["arrival"],
            start_s=meta["start_s"],
            finish_s=meta["finish_s"],
            cold=meta["cold"],
            dropped=meta["dropped"],
            latency_s=meta["latency_s"],
        )
        for rid, meta in sorted(req_meta.items())
    ]

    interval_records = _complete_interval_records(
        intervals,
        request_records,
        interval_costs,
        cfg,
    )

    return SimResult(
        requests=request_records,
        intervals=interval_records,
        busy_seconds=total_busy_s,
        idle_warm_seconds=total_idle_s,
        init_seconds=total_init_s,
        policy_created_instances=policy_created_instances,
        on_demand_created_instances=on_demand_created_instances,
    )


def _complete_interval_records(
    intervals: list[IntervalRecord],
    requests: list[RequestRecord],
    interval_costs: dict[str, list[float]],
    cfg: SimConfig,
) -> list[IntervalRecord]:
    """Add request outcomes and exact state cost to each decision interval."""
    n_intervals = int(math.ceil(cfg.duration_s / cfg.decision_interval_s))
    snapshots = {int(round(record.t / cfg.decision_interval_s)): record for record in intervals}
    requests_by_interval: list[list[RequestRecord]] = [
        [] for _ in range(n_intervals)
    ]
    for request in requests:
        index = int(request.arrival_s / cfg.decision_interval_s)
        if 0 <= index < n_intervals:
            requests_by_interval[index].append(request)

    completed: list[IntervalRecord] = []
    for index in range(n_intervals):
        start = index * cfg.decision_interval_s
        end = min(cfg.duration_s, (index + 1) * cfg.decision_interval_s)
        snapshot = snapshots.get(index)
        target = snapshot.target if snapshot else 0
        ready = snapshot.ready if snapshot else 0
        forecast = snapshot.forecast_rate if snapshot else None
        budget_clamped = snapshot.budget_clamped if snapshot else False
        in_interval = requests_by_interval[index]
        latencies = [
            request.latency_s for request in in_interval
            if not request.dropped and request.latency_s is not None
        ]
        observed = len(in_interval)
        needed = math.ceil(
            observed / (end - start) * cfg.mean_exec_s
        ) if observed else 0
        cost = (
            interval_costs["busy"][index] * cfg.busy_cost_weight
            + (interval_costs["idle"][index] + interval_costs["init"][index])
            * cfg.warm_cost_weight
        )
        completed.append(IntervalRecord(
            t=start,
            target=target,
            ready=ready,
            busy=snapshot.busy if snapshot else 0,
            initializing=snapshot.initializing if snapshot else 0,
            queue_length=snapshot.queue_length if snapshot else 0,
            arrivals_in_window=observed,
            t_start=start,
            t_end=end,
            observed_requests=observed,
            predicted_requests=None if forecast is None else forecast * (end - start),
            recommended_warm=target,
            ready_instances=ready,
            cold_starts=sum(1 for request in in_interval if request.cold and not request.dropped),
            avg_latency_s=float(sum(latencies) / len(latencies)) if latencies else None,
            p95_latency_s=float(np.percentile(latencies, 95)) if latencies else None,
            dropped_requests=sum(1 for request in in_interval if request.dropped),
            interval_cost=cost,
            shortfall=max(0, needed - ready),
            forecast_rate=forecast,
            budget_clamped=budget_clamped,
        ))
    return completed
