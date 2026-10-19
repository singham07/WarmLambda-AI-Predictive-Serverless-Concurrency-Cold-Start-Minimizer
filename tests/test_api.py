"""
tests.test_api
==============
Integration tests for the WarmLambda AI FastAPI backend using TestClient.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from api.main import app
from api.schemas import DISCLAIMER, VALID_SCENARIOS

client = TestClient(app)


def test_health() -> None:
    """GET /health returns 200, status ok, and disclaimer."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["disclaimer"] == DISCLAIMER


def test_scenarios() -> None:
    """GET /scenarios returns all 4 valid scenario descriptions."""
    response = client.get("/scenarios")
    assert response.status_code == 200
    data = response.json()
    assert "scenarios" in data
    assert data["disclaimer"] == DISCLAIMER

    scenario_names = {s["name"] for s in data["scenarios"]}
    assert scenario_names == VALID_SCENARIOS
    for s in data["scenarios"]:
        assert len(s["description"]) > 5


def test_policies() -> None:
    """GET /policies returns available policies and descriptions."""
    response = client.get("/policies")
    assert response.status_code == 200
    data = response.json()
    assert "policies" in data
    assert data["disclaimer"] == DISCLAIMER

    policy_names = {p["name"] for p in data["policies"]}
    expected = {
        "no_warming",
        "fixed",
        "reactive",
        "wl_forecast_only",
        "wl_correction_only",
        "wl_full",
        "oracle",
    }
    assert expected.issubset(policy_names)


@pytest.mark.parametrize(
    "policy",
    [
        "no_warming",
        "fixed",
        "reactive",
        "wl_forecast_only",
        "wl_correction_only",
        "wl_full",
        "oracle",
    ],
)
def test_run_per_policy(policy: str) -> None:
    """POST /run works for each policy and returns valid downsampled intervals."""
    payload = {
        "scenario": "moderate",
        "policy": policy,
        "fixed_n": 3,
        "headroom": 0.5,
        "seed": 42,
        "duration_s": 100.0,
        "allow_short_runs": True,
    }
    response = client.post("/run", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["disclaimer"] == DISCLAIMER
    assert "config" in data
    assert "metrics" in data
    assert "intervals" in data

    # Check metrics keys
    metrics = data["metrics"]
    assert "n_requests" in metrics
    assert "cold_start_rate" in metrics
    assert "total_cost" in metrics
    assert metrics["n_requests"] > 0

    # Downsampling constraint: at most 500 points
    intervals = data["intervals"]
    assert len(intervals) <= 500
    if len(intervals) > 0:
        first = intervals[0]
        assert "t" in first
        assert "target" in first
        assert "ready" in first
        assert "busy" in first
        assert "queue_length" in first
        assert "arrivals_in_window" in first


def test_bad_scenario_422() -> None:
    """POST /run returns 422 Unprocessable Entity for invalid scenario."""
    payload = {
        "scenario": "non_existent_scenario",
        "policy": "no_warming",
    }
    response = client.post("/run", json=payload)
    assert response.status_code == 422


def test_bad_headroom_422() -> None:
    """POST /run returns 422 for negative headroom."""
    payload = {
        "scenario": "moderate",
        "policy": "wl_full",
        "headroom": -1.0,
    }
    response = client.post("/run", json=payload)
    assert response.status_code == 422


def test_short_run_requires_opt_in() -> None:
    """Durations below 600 seconds require an explicit diagnostic opt-in."""
    response = client.post(
        "/run",
        json={"scenario": "moderate", "policy": "no_warming", "duration_s": 100.0},
    )
    assert response.status_code == 422
    assert "allow_short_runs=true" in response.json()["detail"][0]["msg"]


def test_short_run_opt_in_is_accepted() -> None:
    """The opt-in allows focused short diagnostic simulations."""
    response = client.post(
        "/run",
        json={
            "scenario": "moderate",
            "policy": "no_warming",
            "duration_s": 100.0,
            "allow_short_runs": True,
        },
    )
    assert response.status_code == 200


def test_api_default_duration_is_one_hour() -> None:
    """Omitting duration_s uses the standard 3600-second simulation window."""
    response = client.post(
        "/run",
        json={"scenario": "moderate", "policy": "no_warming"},
    )
    assert response.status_code == 200
    assert response.json()["config"]["duration_s"] == 3600.0


def test_compare_identical_traffic_totals() -> None:
    """POST /compare benchmarks policies on identical traffic."""
    policies = ["no_warming", "fixed", "reactive", "wl_full"]
    payload = {
        "scenario": "moderate",
        "policies": policies,
        "fixed_n": 4,
        "headroom": 0.5,
        "seed": 42,
        "duration_s": 100.0,
        "allow_short_runs": True,
    }
    response = client.post("/compare", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["scenario"] == "moderate"
    assert data["seed"] == 42
    assert data["disclaimer"] == DISCLAIMER
    assert "results" in data

    results = data["results"]
    assert set(results.keys()) == set(policies)

    # All policies must be evaluated on the EXACT same traffic total
    request_counts = [results[pol]["metrics"]["n_requests"] for pol in policies]
    assert len(set(request_counts)) == 1, f"Expected identical traffic totals, got {request_counts}"

    # Verify total arrivals sum across intervals is identical
    total_arrivals = [
        sum(pt["arrivals_in_window"] for pt in results[pol]["intervals"])
        for pol in policies
    ]
    assert len(set(total_arrivals)) == 1, f"Interval arrivals differ: {total_arrivals}"


def test_results_summary(tmp_path, monkeypatch) -> None:
    """GET /results/summary returns aggregated data or 404 when file is missing."""
    # Test existing file
    response = client.get("/results/summary")
    assert response.status_code in (200, 404)
    if response.status_code == 200:
        data = response.json()
        assert "summary" in data
        assert data["disclaimer"] == DISCLAIMER

    # Test missing file gives 404
    missing_file = tmp_path / "non_existent.csv"
    monkeypatch.setattr("api.services.Path", lambda *args, **kwargs: missing_file)
    response_404 = client.get("/results/summary")
    assert response_404.status_code == 404
