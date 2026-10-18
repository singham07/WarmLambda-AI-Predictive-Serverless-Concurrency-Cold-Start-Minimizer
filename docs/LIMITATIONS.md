# WarmLambda AI: Simulator Limitations and Non-Claims

This document outlines the architectural simplifications of the WarmLambda AI simulator compared to production cloud environments, identifies unmodelled phenomena, and clearly defines the non-claims of this project.

---

## 1. Simplifications Versus Real AWS Lambda

While the simulator takes inspiration from AWS Lambda container lifecycles, it intentionally simplifies platform mechanics for clear mathematical evaluation:

1. **Single Invocation Concurrency Model**:
   - The simulator assumes one invocation per instance (`concurrency_per_instance = 1`). While this reflects standard AWS Lambda behavior, commercial platforms use sophisticated internal multiplexing and container pooling heuristics.
2. **Fixed Cold Start Initialization Latency**:
   - In the simulator, cold start latency is a constant value (`init_time_s = 1.0` seconds by default). In real AWS Lambda, cold start duration varies significantly based on deployment package size, programming language runtime (e.g. JVM vs Go/Node), container image layers, and VPC Elastic Network Interface (ENI) attachment delays.
3. **Absence of SnapStart and Snapshot Caching**:
   - Real-world serverless platforms deploy optimizations such as AWS Lambda SnapStart, which restores initialized microVM snapshots in tens of milliseconds rather than executing full cold boots. The simulator models traditional cold starts without microVM snapshotting.
4. **Instantaneous Centralized Dispatch and Routing**:
   - All invocations are scheduled via a centralized, instantaneous discrete-event queue with zero platform overhead. In reality, serverless architectures rely on distributed load balancers, front-end routers, and placement services across multiple availability zones, introducing scheduling jitter and network transit latency.
5. **Log-Normal Execution Time Assumption**:
   - Execution times in the simulator follow a unimodal log-normal distribution. Real-world serverless execution durations are often multimodal, displaying distinct clusters corresponding to database connection pool hits, cache misses, network timeouts, or payload size variations.
6. **Abstract Cost Modeling**:
   - The simulator applies uniform dimensionless weights (`warm_cost_weight = 1.0`, `busy_cost_weight = 1.0`) per instance-second. Commercial cloud billing involves millisecond-granularity metering, memory allocation tiers (128 MB to 10 GB), per-request charges ($0.20 per 1M requests), Provisioned Concurrency pricing tiers, and egress data transfer costs.

---

## 2. Unmodelled Phenomena

The following physical and operational factors are not simulated:

- **Hardware Heterogeneity**: Differing CPU generations, memory bus architectures, and noisy-neighbor contention across shared physical servers.
- **Garbage Collection (GC) Pauses**: Java or Node.js runtime garbage collection cycles that cause transient latency spikes in warm containers.
- **Memory Exhaustion (OOM) and Restarts**: Instances terminating due to memory leaks or exceeding provisioned memory boundaries.
- **Worker Node Failure and Eviction**: Physical host reboots, maintenance evictions, or hypervisor rescheduling events.
- **Concurrency Burst Limits**: AWS Lambda imposes account-level regional burst limits (e.g. 500 to 3,000 instances/minute depending on region). The simulator only enforces a global `max_instances` ceiling.
- **Firecracker MicroVM Internals**: Kernel initialization, jailer confinement, and virtio device emulation delays.

---

## 3. Explicit Non-Claims

To maintain academic and scientific integrity, this project explicitly states:

1. **No Superiority Claim Over Commercial Systems**:
   - We do not claim that WarmLambda or any implemented algorithm is superior to AWS Lambda, Google Cloud Functions, or Azure Functions in production environments. Commercial systems employ complex proprietary fleet-wide telemetry across millions of concurrent users.
2. **No Real-World Dollar Savings**:
   - The cost values reported by the simulator are dimensionless resource units designed for controlled comparative experiments. They do not correlate directly with specific dollar amounts or guarantee financial savings on real AWS bills.
3. **No General Workload Universality**:
   - The four synthetic scenarios (moderate, high load, extreme, periodic) represent specific idealized stress tests. Real enterprise serverless workloads exhibit diverse patterns that may not align with these mathematical generators.
4. **No Affiliation with Amazon Web Services**:
   - WarmLambda AI is an independent academic research and education project at GLA University. It is not affiliated with, sponsored by, or endorsed by Amazon Web Services (AWS) or Amazon.com, Inc.
