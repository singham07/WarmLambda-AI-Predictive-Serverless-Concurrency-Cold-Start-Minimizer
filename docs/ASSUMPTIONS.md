# WarmLambda AI: Simulation Assumptions

This document enumerates the core modeling assumptions, parameter values, and design rationale of the WarmLambda AI simulator.

> [!NOTE]
> All simulation outputs, instance counts, and cost metrics are simulated mathematical estimates under stated theoretical assumptions. They are not real AWS Lambda measurements, telemetry, or AWS billing invoices.

---

## 1. Summary of Simulation Parameters

The table below maps all configurable simulation parameters from `SimConfig` ([warmlambda/core/config.py](file:///c:/warmlambda/warmlambda/core/config.py)) to their default values, units, and engineering rationales.

| Parameter | Default Value | Units | Rationale |
|---|---|---|---|
| `duration_s` | `3600.0` | seconds | Standard 1-hour simulation window. Sufficient to capture multiple cycles of periodic traffic and observe warm instance expiration dynamics. |
| `init_time_s` | `1.0` | seconds | Cold start initialization penalty. Models container creation, language runtime boot, and dependency initialization before invocation handling begins. |
| `mean_exec_s` | `0.2` | seconds | Mean invocation execution duration (log-normal parameter mu). Typical of I/O-bound microservices or lightweight API handlers (200 ms). |
| `exec_sigma` | `0.5` | seconds | Standard deviation of invocation execution duration (log-normal parameter sigma). Captures variance and right-skewed latency tails in web requests. |
| `idle_timeout_s` | `300.0` | seconds | Inactivity duration before an idle warm container is evicted. Matches historical default keep-alive behaviors observed in serverless platforms (5 minutes). |
| `max_instances` | `100` | instances | Platform-level concurrency ceiling. Prevents unbounded instance allocation and simulates resource limits or account concurrency quotas. |
| `concurrency_per_instance` | `1` | invocations | Invocations handled concurrently per instance container. Matches standard AWS Lambda container concurrency semantics (single request per worker). |
| `queue_timeout_s` | `10.0` | seconds | Maximum queue dwell time before invocation drop. Represents API Gateway or client request timeout thresholds (HTTP 504 / 429 throttle error). |
| `decision_interval_s` | `20.0` | seconds | Policy evaluation tick period. Balances control-loop responsiveness against excessive churn in instance provisioning. |
| `warm_cost_weight` | `1.0` | unit / instance-second | Dimensionless resource consumption multiplier for an instance held idle in the warm state. |
| `busy_cost_weight` | `1.0` | unit / instance-second | Dimensionless resource consumption multiplier for an instance actively executing invocations. Baseline reference cost. |

---

## 2. Traffic Scenario Assumptions

All traffic traces are generated using a non-homogeneous Poisson process (NHPP) via Lewis-Shedler thinning ([warmlambda/core/traffic.py](file:///c:/warmlambda/warmlambda/core/traffic.py)).

| Scenario | Rate Function Formula | Peak Rate | Total Expected Invocations | Workload Characteristics |
|---|---|---|---|---|
| `moderate` | `3.0 * (1.0 + 0.30 * sin(2*pi*t / 1200))` | 3.90 req/s | 10,800 req / hour | Gentle diurnal-style oscillation (+-30% sinusoidal wave with 20-minute cycle). Tests baseline tracking. |
| `high_load` | `30.0 * (0.6 + 0.8 * (t / 3600))` | 42.0 req/s | 108,000 req / hour | Sustained heavy traffic with linear ramp (0.6x at start to 1.4x at end). Tests scaling under sustained saturation. |
| `extreme` | `2.0 req/s` base + 3 to 6 spikes of `15x` (`30.0 req/s`) | 30.0 req/s | ~13,000 to 20,000 req / hour | Low background traffic interrupted by unannounced, massive bursts lasting 30 to 120 seconds each. Tests reactive and forecast resilience. |
| `periodic` | `5.0 * (1.0 + 0.60 * sin(2*pi*t / 600))` | 8.0 req/s | 18,000 req / hour | High-amplitude oscillation (+-60% sinusoidal wave with 10-minute cycle). Completes 6 full cycles per hour. Tests seasonal naive forecasters. |

---

## 3. Policy Assumptions and Little's Law

The WarmLambda predictive policy relies on Little's Law from queueing theory:

$$L = \lambda \cdot W$$

Where:
- $L$ is the required concurrency (average active instances).
- $\lambda$ is the forecasted arrival rate (requests per second) predicted for the upcoming window.
- $W$ is the mean service time (`mean_exec_s`).

The target warm instance capacity is computed as:

$$\text{Target} = \min\left(\text{max\_instances}, \lceil \lambda \cdot W \cdot (1 + \text{headroom}) \rceil\right)$$

- **Headroom**: Multiplier (default 0.5, representing 50% safety buffer) above raw theoretical concurrency to absorb within-window arrival variance.
- **Warm Budget**: Optional upper bound on proactively maintained warm containers to prevent cost overruns.
- **Reactive Correction**: In hybrid mode (`wl_full`), the policy takes the maximum of proactive capacity and reactive concurrency demand: $\max(\text{Capacity}_{\text{forecast}}, \lceil (\text{busy} + \text{queue}) \cdot (1 + \text{headroom}) \rceil)$.

---

## 4. Cost Model Assumptions

1. **Dimensionless Units**: Costs are computed as total instance-seconds weighted by state:
   $$\text{Total Cost} = (\text{busy\_seconds} \cdot \text{busy\_cost\_weight}) + (\text{idle\_warm\_seconds} \cdot \text{warm\_cost\_weight}) + (\text{init\_seconds} \cdot \text{busy\_cost\_weight})$$
2. **Billing Equivalence**: We assume maintaining an idle warm container incurs resource cost comparable to an active container (`warm_cost_weight = 1.0`). In platforms with discounted provisioned pricing, `warm_cost_weight` can be adjusted downward (e.g. 0.25 to 0.50).
3. **No Financial Claims**: The calculated cost is an internal relative metric to evaluate cost-performance trade-offs across policies under equal assumptions. It does not map to dollar pricing on any public cloud.
