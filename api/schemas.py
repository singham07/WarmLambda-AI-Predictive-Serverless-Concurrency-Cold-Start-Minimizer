"""
api.schemas
===========
Pydantic models and request validation for the WarmLambda AI API.
"""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from warmlambda.core.forecaster_registry import default_model_name

DISCLAIMER: str = "Simulated estimates under stated assumptions; not real AWS costs."

VALID_SCENARIOS = {"moderate", "high_load", "extreme", "periodic"}
PolicyType = Literal[
    "no_warming",
    "fixed",
    "reactive",
    "wl_forecast_only",
    "wl_correction_only",
    "wl_full",
    "oracle",
]


class BaseResponse(BaseModel):
    """Base response model including the required simulated disclaimer."""
    disclaimer: str = DISCLAIMER


class HealthResponse(BaseResponse):
    status: str = "ok"


class ScenarioItem(BaseModel):
    name: str
    description: str


class ScenariosResponse(BaseResponse):
    scenarios: list[ScenarioItem]


class PolicyItem(BaseModel):
    name: str
    description: str
    parameters: dict[str, str]


class PoliciesResponse(BaseResponse):
    policies: list[PolicyItem]


class RunRequest(BaseModel):
    """Request payload for /run."""
    scenario: str = Field(..., description="Traffic scenario name")
    policy: PolicyType = Field(..., description="Warming policy type")
    fixed_n: Optional[int] = Field(default=None, ge=0, description="Instances for fixed policy")
    headroom: float = Field(default=0.5, ge=0.0, le=10.0, description="Safety headroom margin")
    warm_budget: Optional[int] = Field(default=None, ge=0, description="Max warm instance ceiling")
    model: str = Field(default_factory=default_model_name, description="Forecaster: ewma, seasonal, ridge, ridge_q90, or gru")
    seed: int = Field(default=42, ge=0, description="PRNG seed for trace reproducibility")

    # Optional SimConfig overrides
    init_time_s: Optional[float] = Field(default=None, gt=0.0, description="Cold start initialization time")
    mean_exec_s: Optional[float] = Field(default=None, gt=0.0, description="Mean execution duration")
    duration_s: float = Field(default=3600.0, gt=0.0, le=86400.0, description="Simulation duration (minimum 600 unless allow_short_runs is true)")
    allow_short_runs: bool = Field(default=False, description="Allow diagnostic runs shorter than 600 seconds")
    idle_timeout_s: Optional[float] = Field(default=None, gt=0.0, description="Idle instance timeout")
    max_instances: Optional[int] = Field(default=None, ge=1, le=10000, description="Max concurrent instance limit")

    @model_validator(mode="after")
    def validate_duration(self) -> "RunRequest":
        if self.duration_s < 600.0 and not self.allow_short_runs:
            raise ValueError(
                "duration_s must be at least 600 seconds unless allow_short_runs=true"
            )
        return self

    @field_validator("scenario")
    @classmethod
    def validate_scenario(cls, v: str) -> str:
        if v not in VALID_SCENARIOS:
            raise ValueError(
                f"Unknown scenario '{v}'. Valid scenarios are: {sorted(VALID_SCENARIOS)}"
            )
        return v

    @field_validator("fixed_n")
    @classmethod
    def validate_fixed_n(cls, v: Optional[int], info: Any) -> Optional[int]:
        # If policy is 'fixed', fixed_n should be non-negative integer
        policy = info.data.get("policy")
        if policy == "fixed" and v is None:
            # Default to 5 if not provided
            return 5
        return v


class CompareRequest(BaseModel):
    """Request payload for /compare."""
    scenario: str = Field(..., description="Traffic scenario name")
    policies: list[PolicyType] = Field(
        default=["no_warming", "fixed", "reactive", "wl_full"],
        min_length=1,
        description="List of policies to benchmark",
    )
    fixed_n: Optional[int] = Field(default=5, ge=0, description="Instances for fixed policy")
    headroom: float = Field(default=0.5, ge=0.0, le=10.0, description="Safety headroom margin")
    warm_budget: Optional[int] = Field(default=None, ge=0, description="Max warm instance ceiling")
    model: str = Field(default_factory=default_model_name, description="Forecaster name")
    seed: int = Field(default=42, ge=0, description="PRNG seed for trace reproducibility")

    # Optional SimConfig overrides
    init_time_s: Optional[float] = Field(default=None, gt=0.0)
    mean_exec_s: Optional[float] = Field(default=None, gt=0.0)
    duration_s: float = Field(default=3600.0, gt=0.0, le=86400.0)
    allow_short_runs: bool = Field(default=False, description="Allow diagnostic runs shorter than 600 seconds")
    idle_timeout_s: Optional[float] = Field(default=None, gt=0.0)
    max_instances: Optional[int] = Field(default=None, ge=1, le=10000)

    @model_validator(mode="after")
    def validate_duration(self) -> "CompareRequest":
        if self.duration_s < 600.0 and not self.allow_short_runs:
            raise ValueError(
                "duration_s must be at least 600 seconds unless allow_short_runs=true"
            )
        return self

    @field_validator("scenario")
    @classmethod
    def validate_scenario(cls, v: str) -> str:
        if v not in VALID_SCENARIOS:
            raise ValueError(
                f"Unknown scenario '{v}'. Valid scenarios are: {sorted(VALID_SCENARIOS)}"
            )
        return v


class IntervalPoint(BaseModel):
    t: float
    arrivals_in_window: int
    forecast_rate: Optional[float]
    target: int
    ready: int
    busy: int
    queue_length: int


class CapacityPlanPoint(BaseModel):
    t_start: float
    t_end: float
    observed_requests: int
    predicted_requests: Optional[float]
    recommended_warm_instances: int
    ready_instances: int
    cold_starts: int
    avg_latency_s: Optional[float]
    p95_latency_s: Optional[float]
    dropped_requests: int
    estimated_cost_units: float
    shortfall_instances: int


class RunResponse(BaseResponse):
    config: dict[str, Any]
    metrics: dict[str, Any]
    intervals: list[IntervalPoint]
    capacity_plan: list[CapacityPlanPoint]
    summary: dict[str, Any]
    plan_resolution_s: float


class PolicyRunResult(BaseModel):
    metrics: dict[str, Any]
    intervals: list[IntervalPoint]
    capacity_plan: list[CapacityPlanPoint]
    summary: dict[str, Any]
    plan_resolution_s: float


class CompareResponse(BaseResponse):
    scenario: str
    seed: int
    results: dict[str, PolicyRunResult]


class SummaryResponse(BaseResponse):
    summary: dict[str, Any]
