"""Capacity-plan accounting and API export tests."""

from __future__ import annotations

import csv
import io
import math

from fastapi.testclient import TestClient

from api.main import app
from warmlambda.core.config import SimConfig
from warmlambda.core.metrics import compute_metrics
from warmlambda.core.policies.no_warming import NoWarming
from warmlambda.core.simulator import simulate
from warmlambda.core.traffic import Request


def test_hand_computed_capacity_plan_and_invariants() -> None:
    """Two requests produce exact interval counts, latency, and cost totals."""
    cfg = SimConfig(
        duration_s=40.0,
        decision_interval_s=20.0,
        init_time_s=1.0,
        idle_timeout_s=300.0,
    )
    result = simulate(
        [Request(0, 0.0, 1.0), Request(1, 25.0, 1.0)],
        NoWarming(),
        cfg,
    )
    metrics = compute_metrics(result, cfg)

    assert len(result.intervals) == 2
    assert result.intervals[0].t_start == 0.0
    assert result.intervals[0].t_end == 20.0
    assert result.intervals[0].observed_requests == 1
    assert result.intervals[0].cold_starts == 1
    assert result.intervals[0].avg_latency_s == 2.0
    assert result.intervals[1].observed_requests == 1
    assert result.intervals[1].cold_starts == 0
    assert result.intervals[1].avg_latency_s == 1.0
    assert sum(item.cold_starts for item in result.intervals) == metrics["cold_start_count"]
    assert sum(item.observed_requests for item in result.intervals) == metrics["n_requests"]
    assert math.isclose(
        sum(item.interval_cost for item in result.intervals),
        metrics["total_cost"],
        abs_tol=1e-6,
    )


def test_api_capacity_plan_and_csv_export() -> None:
    """Run responses contain full plans and CSV has the documented columns."""
    client = TestClient(app)
    payload = {
        "scenario": "moderate",
        "policy": "no_warming",
        "duration_s": 600.0,
        "seed": 0,
    }
    response = client.post("/run", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert len(body["capacity_plan"]) == 30
    assert body["summary"]["total_cold_starts"] >= 0
    assert body["plan_resolution_s"] == 20.0

    exported = client.post("/plan/export", json=payload)
    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert len(rows) == 30
    assert list(rows[0]) == [
        "time_start_s", "time_end_s", "observed_requests", "predicted_requests",
        "recommended_warm_instances", "ready_instances", "cold_starts",
        "avg_latency_s", "p95_latency_s", "dropped_requests",
        "estimated_cost_units", "shortfall_instances",
    ]
