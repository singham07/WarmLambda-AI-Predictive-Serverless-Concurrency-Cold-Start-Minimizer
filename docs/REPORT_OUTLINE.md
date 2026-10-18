# WarmLambda AI: Research Report Outline

This document outlines the structure, contents, and figure placements for the final project research report and academic evaluation.

---

## Section Outline and Content Guidelines

### Section 1: Problem Formulation
- **Contents**:
  - The fundamental tension in Function-as-a-Service (FaaS): cold start latency penalties versus idle resource waste.
  - Why naive keep-alive pings and static provisioned capacity fail under non-stationary traffic.
  - Formal definition of the warm-capacity allocation problem under budget and latency constraints.
- **Figures / Tables**: None (introductory conceptual framing).

---

### Section 2: Related Work
- **Contents**:
  - Serverless cold start mitigation techniques (e.g. AWS Provisioned Concurrency, Google Cloud Min Instances).
  - Predictive auto-scaling literature: time-series forecasting (ARIMA, EWMA, Prophet) applied to cloud workloads.
  - Heuristic keep-alive approaches and their cost-efficiency trade-offs.
  - Positioning WarmLambda as an adaptive, causal, Little's Law-driven proactive policy with reactive fallback.
- **Figures / Tables**: Comparative literature summary table.

---

### Section 3: Method and Architecture
- **Contents**:
  - The WarmLambda policy architecture:
    1. Online traffic rate forecasting using Exponentially Weighted Moving Average (EWMA) and Seasonal Naive estimators.
    2. Capacity determination via Little's Law: $L = \lambda \cdot W$.
    3. Headroom safety buffer ($1 + \text{headroom}$) to accommodate intra-window variance.
    4. Reactive concurrency correction: $\max(\text{Capacity}_{\text{forecast}}, \lceil (\text{busy} + \text{queue}) \cdot (1 + \text{headroom}) \rceil)$.
    5. Warm budget ceiling enforcement.
- **Figures / Tables**:
  - Architecture block diagram (Mermaid flowchart matching `README.md`).

---

### Section 4: Simulator Design
- **Contents**:
  - Discrete-event simulation architecture: event priority queue, state transitions (cold boot, warm idle, executing, expired).
  - Mathematical formulation of Lewis-Shedler thinning algorithm for Non-Homogeneous Poisson Processes (NHPP).
  - Log-normal execution time sampling and instance concurrency enforcement.
  - Causal isolation guarantees: proving zero future-data leakage in policy decision loops.
- **Figures / Tables**:
  - State machine transition diagram for container lifecycle (Init -> Ready -> Busy -> Evicted).

---

### Section 5: Warm-Capacity Policies
- **Contents**:
  - Baseline 1: `no_warming` (pure on-demand scaling with standard idle timeout).
  - Baseline 2: `fixed_n` (static provisioned concurrency holding $n \in \{1, 2, 5, 10, 20\}$ instances).
  - Baseline 3: `reactive` (load-tracking with safety margin, max step limit, and scale-down cooldown).
  - WarmLambda Variants: `wl_forecast_only`, `wl_correction_only`, `wl_full`.
  - Theoretical Upper Bound: `oracle` (cheating lookahead policy with perfect knowledge of next-window arrivals).
- **Figures / Tables**: Summary table of policy parameters and decision formulas.

---

### Section 6: Traffic Scenarios and Workload Profiles
- **Contents**:
  - Detailed mathematical definition of the four evaluation workloads:
    - Moderate (sinusoidal diurnal pattern, period 1200 s).
    - High Load (heavy traffic with 0.6x to 1.4x linear ramp over 3600 s).
    - Extreme (background baseline with unpredictable 15x bursts).
    - Periodic (high-amplitude sinusoidal cycles, period 600 s).
- **Figures / Tables**:
  - **Figure 1**: `results/figures/traffic_preview.png` (Four-panel time-series preview of instantaneous arrival rates across all scenarios).

---

### Section 7: Evaluation Metrics and Trade-off Dimensions
- **Contents**:
  - Formal definitions of key evaluation metrics:
    - Cold Start Rate (%): Fraction of requests incurring `init_time_s`.
    - Mean Latency and 95th Percentile Latency (p95): Tail latency exposure.
    - Total Cost (dimensionless simulation units): Weighted sum of busy, idle warm, and initialization instance-seconds.
    - Resource Utilization (%): Efficiency ratio of productive execution time to total allocated container time.
    - Dropped Rate (%): Invocations timing out in the admission queue.
- **Figures / Tables**: Metric formulation reference table.

---

### Section 8: Empirical Results
- **Contents**:
  - Comprehensive performance comparison across all 4 scenarios and 11 policy configurations over 5 random seeds (from `results/final_metrics.csv`).
  - Analysis of the cold-start vs total-cost Pareto frontier.
  - Analysis of latency percentiles under bursty load.
  - Comparison of WarmLambda against the theoretical Oracle bound.
- **Figures / Tables**:
  - **Table 1**: Aggregated benchmark results table (mean +- standard deviation for cold start rate, total cost, utilization, and p95 latency).
  - **Figure 2**: `results/figures/policy_comparison_pareto.png` (Scatter plot of cold start rate vs total cost highlighting Pareto-optimal policies).
  - **Figure 3**: `results/figures/target_vs_ready_timeseries.png` (Time-series tracking showing WarmLambda pre-warming before bursts and scaling down during lulls).
  - **Figure 4**: `results/figures/p95_latency_bar.png` (Bar chart comparing 95th percentile latency across policies).

---

### Section 9: Sensitivity Analysis
- **Contents**:
  - Impact of the headroom multiplier ($\text{headroom} \in \{0.2, 0.5, 1.0\}$) on cold start reduction and warm holding costs.
  - Impact of warm budget caps under budget-constrained operational regimes.
  - Forecaster parameter sensitivity: comparison of EWMA alpha values (0.2, 0.4, 0.7) and Holt's trend tracking.
- **Figures / Tables**:
  - **Figure 5**: `results/figures/headroom_sensitivity.png` (Trade-off curve of cold start rate versus cost as a function of headroom).

---

### Section 10: Limitations and Threats to Validity
- **Contents**:
  - Differences between the discrete-event model and real AWS Lambda infrastructure (SnapStart, VPC routing, microVM startup variance).
  - Synthetic workload limitations and absence of heterogeneous multi-tenant noise.
  - Restatement of explicit non-claims (no guarantee of real-world dollar savings).
- **Figures / Tables**: None (critical discussion).

---

### Section 11: Conclusion and Future Directions
- **Contents**:
  - Summary of major findings: WarmLambda reduces cold starts significantly compared to reactive scaling while avoiding the catastrophic cost overhead of static fixed provisioning.
  - Future extensions: reinforcement learning for dynamic headroom adjustment, integration with Kubernetes Knative / OpenWhisk, and multi-tenant trace evaluation.
