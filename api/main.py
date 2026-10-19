"""
api.main
========
FastAPI application for WarmLambda AI.
"""

from __future__ import annotations

import sys
import csv
import io
from pathlib import Path

# Ensure workspace root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from api.schemas import (
    DISCLAIMER,
    CompareRequest,
    CompareResponse,
    HealthResponse,
    PoliciesResponse,
    PolicyItem,
    PolicyRunResult,
    RunRequest,
    RunResponse,
    ScenarioItem,
    ScenariosResponse,
    SummaryResponse,
)
from api.services import build_capacity_plan, get_results_summary, run_comparison, run_single_simulation

app = FastAPI(
    title="WarmLambda AI API",
    description="Discrete-event serverless warm-capacity policy simulation and benchmarking API.",
    version="1.0.0",
)

# Enable CORS for local web frontends
origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", include_in_schema=False)
def serve_dashboard():
    """Serve the interactive WarmLambda simulation dashboard."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "WarmLambda API is running. Visit /docs for OpenAPI specs."}


@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check() -> HealthResponse:
    """Return system operational status and assumptions disclaimer."""
    return HealthResponse(status="ok", disclaimer=DISCLAIMER)


@app.get("/scenarios", response_model=ScenariosResponse, tags=["Scenarios"])
def get_scenarios() -> ScenariosResponse:
    """List available traffic scenarios with one-line descriptions."""
    scenarios = [
        ScenarioItem(
            name="moderate",
            description="Base 3 req/s ± 30 % sine wave with a 1200 s period.",
        ),
        ScenarioItem(
            name="high_load",
            description="Base 30 req/s with a linear ramp from 0.6× to 1.4× over the duration.",
        ),
        ScenarioItem(
            name="extreme",
            description="Base 2 req/s with 3-6 random unpredictable spikes of 15× lasting 30-120 s each.",
        ),
        ScenarioItem(
            name="periodic",
            description="Base 5 req/s with 60 % sine wave amplitude and a 600 s period.",
        ),
    ]
    return ScenariosResponse(scenarios=scenarios, disclaimer=DISCLAIMER)


@app.get("/policies", response_model=PoliciesResponse, tags=["Policies"])
def get_policies() -> PoliciesResponse:
    """List available warm-capacity policies and their parameter descriptions."""
    policies = [
        PolicyItem(
            name="no_warming",
            description="On-demand baseline maintaining 0 warm instances; every idle expiry causes a cold start.",
            parameters={},
        ),
        PolicyItem(
            name="fixed",
            description="Holds a constant number of warm instances regardless of traffic fluctuations.",
            parameters={"fixed_n": "Number of warm instances to hold (int >= 0, default 5)"},
        ),
        PolicyItem(
            name="reactive",
            description="Scales warm capacity in response to observed current load with bounded step sizes and cooldown.",
            parameters={},
        ),
        PolicyItem(
            name="wl_forecast_only",
            description="WarmLambda proactive sizing using EWMA arrival rate forecasting and Little's Law.",
            parameters={
                "headroom": "Proactive safety margin multiplier above Little's Law (float >= 0.0, default 0.5)",
                "warm_budget": "Optional ceiling capping max warm instances (int >= 0)",
                "model": "Forecaster model name; defaults to trained hgb_q90 when available, otherwise ewma.",
            },
        ),
        PolicyItem(
            name="wl_correction_only",
            description="WarmLambda reactive concurrency adjustment tracking instantaneous active + queued load.",
            parameters={
                "headroom": "Headroom margin multiplier on current concurrency (float >= 0.0, default 0.5)",
                "warm_budget": "Optional ceiling capping max warm instances (int >= 0)",
                "model": "Forecaster model name; defaults to trained hgb_q90 when available, otherwise ewma.",
            },
        ),
        PolicyItem(
            name="wl_full",
            description="Complete WarmLambda hybrid policy combining proactive EWMA forecast with reactive concurrency correction.",
            parameters={
                "headroom": "Safety margin multiplier on both forecast and load (float >= 0.0, default 0.5)",
                "warm_budget": "Optional ceiling capping max warm instances (int >= 0)",
                "model": "Forecaster model name; defaults to trained hgb_q90 when available, otherwise ewma.",
            },
        ),
        PolicyItem(
            name="oracle",
            description="Theoretical upper bound that peeks 2 decision intervals into true future arrivals (unreachable in practice).",
            parameters={},
        ),
    ]
    return PoliciesResponse(policies=policies, disclaimer=DISCLAIMER)


@app.post("/run", response_model=RunResponse, tags=["Simulation"])
def run_simulation(req: RunRequest) -> RunResponse:
    """Run one simulation scenario and return config, metrics, and downsampled intervals."""
    sim_data = run_single_simulation(req)
    return RunResponse(
        config=sim_data["config"],
        metrics=sim_data["metrics"],
        intervals=sim_data["intervals"],
        capacity_plan=sim_data["capacity_plan"],
        summary=sim_data["summary"],
        plan_resolution_s=sim_data["plan_resolution_s"],
        disclaimer=DISCLAIMER,
    )


@app.post("/compare", response_model=CompareResponse, tags=["Simulation"])
def compare_policies(req: CompareRequest) -> CompareResponse:
    """Benchmark multiple policies side-by-side on the exact same generated trace."""
    comp_data = run_comparison(req)
    results_map: dict[str, PolicyRunResult] = {
        pol_name: PolicyRunResult(
            metrics=data["metrics"],
            intervals=data["intervals"],
            capacity_plan=data["capacity_plan"],
            summary=data["summary"],
            plan_resolution_s=data["plan_resolution_s"],
        )
        for pol_name, data in comp_data["results"].items()
    }
    return CompareResponse(
        scenario=comp_data["scenario"],
        seed=comp_data["seed"],
        results=results_map,
        disclaimer=DISCLAIMER,
    )


@app.post("/plan/export", tags=["Simulation"])
def export_capacity_plan(req: RunRequest) -> StreamingResponse:
    """Export one policy's complete capacity plan as an Excel-compatible CSV."""
    sim_data = run_single_simulation(req)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "time_start_s", "time_end_s", "observed_requests", "predicted_requests",
        "recommended_warm_instances", "ready_instances", "cold_starts",
        "avg_latency_s", "p95_latency_s", "dropped_requests",
        "estimated_cost_units", "shortfall_instances",
    ])
    for point in sim_data["capacity_plan"]:
        writer.writerow([
            point.t_start, point.t_end, point.observed_requests,
            point.predicted_requests, point.recommended_warm_instances,
            point.ready_instances, point.cold_starts, point.avg_latency_s,
            point.p95_latency_s, point.dropped_requests,
            point.estimated_cost_units, point.shortfall_instances,
        ])
    headers = {"Content-Disposition": 'attachment; filename="capacity_plan.csv"'}
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


@app.get("/results/summary", response_model=SummaryResponse, tags=["Results"])
def get_summary() -> SummaryResponse:
    """Return aggregated benchmark metrics (mean, std) from results/final_metrics.csv."""
    summary_data = get_results_summary()
    return SummaryResponse(summary=summary_data, disclaimer=DISCLAIMER)
