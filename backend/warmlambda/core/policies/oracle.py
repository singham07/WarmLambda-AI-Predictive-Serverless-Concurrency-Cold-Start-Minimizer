"""Oracle upper bound using future arrival and execution durations."""

from __future__ import annotations

import math

from backend.warmlambda.core.config import SimConfig
from backend.warmlambda.core.policies.base import Policy, SimState, TrafficHistory
from backend.warmlambda.core.traffic import Request


class Oracle(Policy):
    """Unreachable policy that knows the next interval's true concurrency peak.

    It uses future arrival times and execution durations, and assumes
    instantaneous proactive provisioning. This is intentionally not causal
    and must never be treated as a deployable policy.
    """

    instant_provisioning = True

    def __init__(self, trace: list[Request], cfg: SimConfig) -> None:
        self.cfg = cfg
        self.name = "oracle"
        self._events = sorted(
            event
            for request in trace
            for event in (
                (request.arrival_s, 1),
                (request.arrival_s + request.exec_s, -1),
            )
        )
        self._interval_peaks = self._build_interval_peaks()

    def _build_interval_peaks(self) -> list[int]:
        interval_s = self.cfg.decision_interval_s
        interval_count = math.ceil(self.cfg.duration_s / interval_s) + 2
        peaks: list[int] = []
        current = 0
        event_index = 0

        for interval_index in range(interval_count):
            interval_start = interval_index * interval_s
            interval_end = interval_start + interval_s

            def apply_next_timestamp() -> None:
                nonlocal current, event_index
                timestamp = self._events[event_index][0]
                change = 0
                while (
                    event_index < len(self._events)
                    and self._events[event_index][0] == timestamp
                ):
                    change += self._events[event_index][1]
                    event_index += 1
                current += change

            while (
                event_index < len(self._events)
                and self._events[event_index][0] <= interval_start
            ):
                apply_next_timestamp()
            peak = current
            while (
                event_index < len(self._events)
                and self._events[event_index][0] < interval_end
            ):
                apply_next_timestamp()
                peak = max(peak, current)
            peaks.append(peak)
        return peaks

    def _peak_for_unaligned_interval(self, start: float, end: float) -> int:
        active = 0
        peak = 0
        interval_started = False
        event_index = 0
        while event_index < len(self._events):
            event_time = self._events[event_index][0]
            change = 0
            while event_index < len(self._events) and self._events[event_index][0] == event_time:
                change += self._events[event_index][1]
                event_index += 1

            if event_time < start:
                active += change
            elif event_time == start:
                active += change
                peak = active
                interval_started = True
            elif event_time < end:
                if not interval_started:
                    peak = active
                    interval_started = True
                active += change
                peak = max(peak, active)
            else:
                break
        if not interval_started:
            peak = active
        return peak

    def decide(self, history: TrafficHistory, state: SimState) -> int:  # noqa: ARG002
        """Return peak concurrent demand in the next decision interval."""
        interval_s = self.cfg.decision_interval_s
        index = round(state.now / interval_s)
        if math.isclose(state.now, index * interval_s, abs_tol=1e-9):
            peak_requests = (
                self._interval_peaks[index]
                if 0 <= index < len(self._interval_peaks)
                else 0
            )
        else:
            peak_requests = self._peak_for_unaligned_interval(
                state.now, state.now + interval_s
            )

        target = math.ceil(peak_requests / self.cfg.concurrency_per_instance)
        return min(self.cfg.max_instances, target)
