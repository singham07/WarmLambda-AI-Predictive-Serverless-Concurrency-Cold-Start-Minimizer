# WarmLambda AI: Simulation Assumptions

This document enumerates the core modeling assumptions, parameter values, and design rationale of the WarmLambda AI simulator.

> [!NOTE]
> All simulation outputs, instance counts, and cost metrics are simulated mathematical estimates under stated theoretical assumptions. They are not real AWS Lambda measurements, telemetry, or AWS billing invoices.

---

## 1. Summary of Simulation Parameters

The table below maps all configurable simulation parameters from `SimConfig` ([backend/warmlambda/core/config.py](../backend/warmlambda/core/config.py)) to their default values, units, and engineering rationales.

| Parameter | Default Value | Units | Rationale |
|---|---|---|---|
| `duration_s` | `3600.0` | seconds | Standard 1-hour simulation window. Sufficient to capture multiple cycles of periodic traffic and observe warm instance expiration dynamics. |
| `init_time_s` | `1.0` | seconds | Cold start initialization penalty. Models container creation, language runtime boot, and dependency initialization before invocation handling begins. |
| `mean_exec_s` | `0.2` | seconds | Mean invocation execution duration (log-normal parameter mu). Typical of I/O-bound microservices or lightweight API handlers (200 ms). |
| `exec_sigma` | `0.5` | seconds | Standard deviation of invocation execution duration (log-normal parameter sigma). Captures variance and right-skewed latency tails in web requests. |
| `idle_timeout_s` | `60.0` | seconds | Inactivity duration before an idle warm container is evicted. A long timeout can make `no_warming` behave like keep-warm by retaining on-demand instances. |
| `max_instances` | `100` | instances | Platform-level concurrency ceiling. Prevents unbounded instance allocation and simulates resource limits or account concurrency quotas. |
| `concurrency_per_instance` | `1` | invocations | Invocations handled concurrently per instance container. Matches standard AWS Lambda container concurrency semantics (single request per worker). |
| `queue_timeout_s` | `10.0` | seconds | Maximum queue dwell time before invocation drop. Represents API Gateway or client request timeout thresholds (HTTP 504 / 429 throttle error). |
| `decision_interval_s` | `20.0` | seconds | Policy evaluation tick period. Defaults to 20; the dashboard offers 1, 5, 10, and 20 second presets, and the API accepts any positive value. |
| `lead_time_s` | `21.0` | seconds | Derived provisioning horizon: `init_time_s + decision_interval_s`. |
| `warm_cost_weight` | `1.0` | unit / instance-second | Dimensionless resource consumption multiplier for an instance held idle in the warm state. |
| `busy_cost_weight` | `1.0` | unit / instance-second | Dimensionless resource consumption multiplier for an instance actively executing invocations. Baseline reference cost. |

---

## 2. Traffic Scenario Assumptions

All traffic traces are generated using a non-homogeneous Poisson process (NHPP) via Lewis-Shedler thinning ([backend/warmlambda/core/traffic.py](../backend/warmlambda/core/traffic.py)).

| Scenario | Rate Function Formula | Peak Rate | Total Expected Invocations | Workload Characteristics |
|---|---|---|---|---|
| `moderate` | `3.0 * (1.0 + 0.30 * sin(2*pi*t / 1200))` | 3.90 req/s | 10,800 req / hour | Gentle diurnal-style oscillation (+-30% sinusoidal wave with 20-minute cycle). Tests baseline tracking. |
| `high_load` | `30.0 * (0.6 + 0.8 * (t / 3600))` | 42.0 req/s | 108,000 req / hour | Sustained heavy traffic with linear ramp (0.6x at start to 1.4x at end). Tests scaling under sustained saturation. |
| `extreme` | `2.0 req/s` base + 3 to 6 spikes of `15x` (`30.0 req/s`) | 30.0 req/s | ~13,000 to 20,000 req / hour | Low background traffic interrupted by unannounced, massive bursts lasting 30 to 120 seconds each. Tests reactive and forecast resilience. |
| `periodic` | `5.0 * (1.0 + 0.60 * sin(2*pi*t / 600))` | 8.0 req/s | 18,000 req / hour | High-amplitude oscillation (+-60% sinusoidal wave with 10-minute cycle). Completes 6 full cycles per hour. Tests seasonal naive forecasters. |

---

The realistic experiment adds `scheduled_bursts` and `daily_cycle`. It uses
`idle_timeout_s=10.0` to model a scale-to-zero platform. Its seasonal
forecaster is given the known cycle as a stated assumption: 600 seconds for
`scheduled_bursts` and 1800 seconds for `daily_cycle`.

## 3. Policy Assumptions and Capacity Quantiles

The `wl_littles_law` baseline uses Little's Law from queueing theory:

$$L = \lambda \cdot W$$

Where:
- $L$ is the required concurrency (average active instances).
- $\lambda$ is the forecasted arrival rate (requests per second) predicted for the upcoming window.
- $W$ is the mean service time (`mean_exec_s`).

The quantile policies model concurrent demand as Poisson with mean
`forecast_rate * min(mean_exec_s, lead_time_s)`, and choose the smallest
integer capacity `N` such that the probability of demand exceeding `N` is at
most the configured epsilon (default 0.05):

$$P(X > N) \leq \epsilon,\quad X \sim \text{Poisson}(\lambda \cdot \min(W,L))$$

- **Lead time**: `L` is `init_time_s + decision_interval_s`, the horizon during which capacity changes become available.
- **Epsilon**: Maximum tolerated Poisson tail probability (default 0.05).
- **Warm Budget**: Optional upper bound on proactively maintained warm containers to prevent cost overruns.
- **Reactive Correction**: Hybrid quantile mode takes the maximum of quantile forecast capacity and current busy + queued load.
- **Oracle**: Uses the actual request arrival and execution times to provision the next interval's peak concurrency immediately. It cheats and is only an unattainable upper bound.

---

## 4. Cost Model Assumptions

1. **Dimensionless Units**: Costs are computed as total instance-seconds weighted by state:
   $$\text{Total Cost} = (\text{busy\_seconds} \cdot \text{busy\_cost\_weight}) + (\text{idle\_warm\_seconds} \cdot \text{warm\_cost\_weight}) + (\text{init\_seconds} \cdot \text{busy\_cost\_weight})$$
2. **Billing Equivalence**: We assume maintaining an idle warm container incurs resource cost comparable to an active container (`warm_cost_weight = 1.0`). In platforms with discounted provisioned pricing, `warm_cost_weight` can be adjusted downward (e.g. 0.25 to 0.50).
3. **No Financial Claims**: The calculated cost is an internal relative metric to evaluate cost-performance trade-offs across policies under equal assumptions. It does not map to dollar pricing on any public cloud.
