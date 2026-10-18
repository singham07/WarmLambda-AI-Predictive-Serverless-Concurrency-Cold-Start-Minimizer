import React, { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ScatterChart,
  Scatter,
  ZAxis,
  BarChart,
  Bar,
  Cell,
} from "recharts";
import { API_BASE_URL } from "../config";

const PALETTE = ["#1f4e79", "#c05a00", "#2e7d32", "#8a8a8a", "#b00020"];

export default function Dashboard({ onDisclaimer }) {
  // Form state
  const [scenarios, setScenarios] = useState([]);
  const [availablePolicies, setAvailablePolicies] = useState([]);
  const [scenario, setScenario] = useState("moderate");
  const [selectedPolicies, setSelectedPolicies] = useState([
    "no_warming",
    "fixed",
    "reactive",
    "wl_full",
  ]);
  const [fixedN, setFixedN] = useState(5);
  const [headroom, setHeadroom] = useState(0.5);
  const [warmBudget, setWarmBudget] = useState("");
  const [seed, setSeed] = useState(42);
  const [initTimeS, setInitTimeS] = useState(1.0);
  const [meanExecS, setMeanExecS] = useState(0.2);
  const [durationS, setDurationS] = useState(100.0);

  // Status and results
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [comparisonResults, setComparisonResults] = useState(null);
  const [chartPolicy, setChartPolicy] = useState("wl_full");

  // Initial fetch of scenarios and policies
  useEffect(() => {
    async function loadMeta() {
      try {
        const [scRes, polRes] = await Promise.all([
          fetch(`${API_BASE_URL}/scenarios`),
          fetch(`${API_BASE_URL}/policies`),
        ]);
        if (scRes.ok) {
          const scData = await scRes.json();
          setScenarios(scData.scenarios || []);
          if (scData.disclaimer && onDisclaimer) onDisclaimer(scData.disclaimer);
        }
        if (polRes.ok) {
          const polData = await polRes.json();
          setAvailablePolicies(polData.policies || []);
        }
      } catch (err) {
        setErrorMessage("Could not connect to API backend: " + err.message);
      }
    }
    loadMeta();
  }, [onDisclaimer]);

  const togglePolicy = (pName) => {
    if (selectedPolicies.includes(pName)) {
      if (selectedPolicies.length > 1) {
        setSelectedPolicies(selectedPolicies.filter((p) => p !== pName));
      }
    } else {
      setSelectedPolicies([...selectedPolicies, pName]);
    }
  };

  const handleRunComparison = async (e) => {
    e.preventDefault();
    setErrorMessage("");

    // Input validations
    if (selectedPolicies.length === 0) {
      setErrorMessage("Please select at least one policy.");
      return;
    }
    if (durationS <= 0) {
      setErrorMessage("Duration must be greater than 0 seconds.");
      return;
    }
    if (headroom < 0) {
      setErrorMessage("Headroom cannot be negative.");
      return;
    }

    setLoading(true);
    try {
      const payload = {
        scenario,
        policies: selectedPolicies,
        fixed_n: Number(fixedN),
        headroom: Number(headroom),
        warm_budget: warmBudget === "" ? null : Number(warmBudget),
        seed: Number(seed),
        duration_s: Number(durationS),
        init_time_s: Number(initTimeS),
        mean_exec_s: Number(meanExecS),
      };

      const res = await fetch(`${API_BASE_URL}/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        const detail = errorData.detail || JSON.stringify(errorData);
        setErrorMessage(`Simulation failed with Status ${res.status}: ${detail}`);
        return;
      }

      const data = await res.json();
      setComparisonResults(data.results);
      if (data.disclaimer && onDisclaimer) {
        onDisclaimer(data.disclaimer);
      }

      // Default active chart policy
      if (!selectedPolicies.includes(chartPolicy)) {
        setChartPolicy(selectedPolicies[0]);
      }
    } catch (err) {
      setErrorMessage("Request error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  // CSV download function
  const downloadCSV = () => {
    if (!comparisonResults) return;
    const headers = [
      "policy",
      "n_requests",
      "n_dropped",
      "cold_start_count",
      "cold_start_rate_percent",
      "mean_latency_s",
      "p95_latency_s",
      "total_cost",
      "utilization_percent",
      "dropped_rate_percent",
    ];

    const rows = Object.entries(comparisonResults).map(([pName, pData]) => {
      const m = pData.metrics;
      return [
        pName,
        m.n_requests,
        m.n_dropped,
        m.cold_start_count,
        m.cold_start_rate !== null ? (m.cold_start_rate * 100).toFixed(4) : "0.0000",
        m.mean_latency_s !== null ? m.mean_latency_s.toFixed(4) : "0.0000",
        m.p95_latency_s !== null ? m.p95_latency_s.toFixed(4) : "0.0000",
        m.total_cost !== null ? m.total_cost.toFixed(2) : "0.00",
        m.utilization !== null ? (m.utilization * 100).toFixed(4) : "0.0000",
        m.dropped_rate !== null ? (m.dropped_rate * 100).toFixed(4) : "0.0000",
      ].join(",");
    });

    const csvContent = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `warm_lambda_comparison_${scenario}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Identify best values in comparison table
  const bestMap = React.useMemo(() => {
    if (!comparisonResults) return {};
    const entries = Object.entries(comparisonResults);
    if (entries.length === 0) return {};

    const minColdRate = Math.min(
      ...entries.map(([, d]) => d.metrics.cold_start_rate ?? Infinity)
    );
    const minMeanLat = Math.min(
      ...entries.map(([, d]) => d.metrics.mean_latency_s ?? Infinity)
    );
    const minP95Lat = Math.min(
      ...entries.map(([, d]) => d.metrics.p95_latency_s ?? Infinity)
    );
    const minCost = Math.min(
      ...entries.map(([, d]) => d.metrics.total_cost ?? Infinity)
    );
    const maxUtil = Math.max(
      ...entries.map(([, d]) => d.metrics.utilization ?? -Infinity)
    );
    const minDrop = Math.min(
      ...entries.map(([, d]) => d.metrics.dropped_rate ?? Infinity)
    );

    return { minColdRate, minMeanLat, minP95Lat, minCost, maxUtil, minDrop };
  }, [comparisonResults]);

  // Chart data extraction
  const activeIntervals =
    comparisonResults && comparisonResults[chartPolicy]
      ? comparisonResults[chartPolicy].intervals
      : [];

  const scatterData = comparisonResults
    ? Object.entries(comparisonResults).map(([pName, pData]) => ({
        policy: pName,
        coldStartRate:
          pData.metrics.cold_start_rate !== null
            ? Number((pData.metrics.cold_start_rate * 100).toFixed(3))
            : 0,
        totalCost:
          pData.metrics.total_cost !== null
            ? Number(pData.metrics.total_cost.toFixed(1))
            : 0,
      }))
    : [];

  const latencyBarData = comparisonResults
    ? Object.entries(comparisonResults).map(([pName, pData]) => ({
        policy: pName,
        p95:
          pData.metrics.p95_latency_s !== null
            ? Number(pData.metrics.p95_latency_s.toFixed(4))
            : 0,
      }))
    : [];

  const selectedScenarioDesc =
    scenarios.find((s) => s.name === scenario)?.description || "";

  return (
    <div className="two-col-layout">
      {/* Left Column Form */}
      <aside className="panel">
        <h2 className="panel-heading">Simulation Settings</h2>

        {errorMessage && <div className="error-box">{errorMessage}</div>}

        <form onSubmit={handleRunComparison}>
          <div className="form-field">
            <label className="form-label" htmlFor="scenario-select">
              Traffic Scenario:
            </label>
            <select
              id="scenario-select"
              className="form-select"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
            >
              {scenarios.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
            {selectedScenarioDesc && (
              <div className="field-description">{selectedScenarioDesc}</div>
            )}
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="seed-input">
              Random Seed:
            </label>
            <input
              id="seed-input"
              type="number"
              className="form-input"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              required
            />
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="duration-input">
              Duration (seconds):
            </label>
            <input
              id="duration-input"
              type="number"
              step="any"
              min="1"
              className="form-input"
              value={durationS}
              onChange={(e) => setDurationS(e.target.value)}
              required
            />
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="headroom-input">
              Headroom: {Number(headroom).toFixed(2)}
            </label>
            <input
              id="headroom-input"
              type="number"
              min="0.0"
              max="2.0"
              step="any"
              className="form-input"
              value={headroom}
              onChange={(e) => setHeadroom(e.target.value)}
              required
            />
            <div className="field-description">
              Proactive capacity multiplier above Little's Law.
            </div>
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="budget-input">
              Warm Budget (optional):
            </label>
            <input
              id="budget-input"
              type="number"
              min="0"
              placeholder="No ceiling"
              className="form-input"
              value={warmBudget}
              onChange={(e) => setWarmBudget(e.target.value)}
            />
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="init-time-input">
              Cold Start Init Time (s):
            </label>
            <input
              id="init-time-input"
              type="number"
              step="any"
              min="0.0"
              className="form-input"
              value={initTimeS}
              onChange={(e) => setInitTimeS(e.target.value)}
            />
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="exec-time-input">
              Mean Exec Time (s):
            </label>
            <input
              id="exec-time-input"
              type="number"
              step="any"
              min="0.01"
              className="form-input"
              value={meanExecS}
              onChange={(e) => setMeanExecS(e.target.value)}
            />
          </div>

          <div className="form-field">
            <span className="form-label">Policies to Compare:</span>
            <div className="checkbox-group">
              {availablePolicies.map((p) => (
                <label key={p.name} className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={selectedPolicies.includes(p.name)}
                    onChange={() => togglePolicy(p.name)}
                  />
                  <span>
                    <strong>{p.name}</strong>
                  </span>
                </label>
              ))}
            </div>
          </div>

          {selectedPolicies.includes("fixed") && (
            <div className="form-field">
              <label className="form-label" htmlFor="fixed-n-input">
                Fixed Policy Capacity (fixed_n):
              </label>
              <input
                id="fixed-n-input"
                type="number"
                min="0"
                className="form-input"
                value={fixedN}
                onChange={(e) => setFixedN(e.target.value)}
              />
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading}
            id="run-comparison-button"
          >
            {loading ? (
              <>
                <span className="loading-indicator"></span> Running...
              </>
            ) : (
              "Run comparison"
            )}
          </button>
        </form>
      </aside>

      {/* Right Column Results */}
      <section className="results-container">
        {!comparisonResults ? (
          <div className="empty-state">
            No results yet. Choose settings and run a comparison.
          </div>
        ) : (
          <>
            {/* Table Section */}
            <div className="panel">
              <div className="table-toolbar">
                <h3 className="panel-heading" style={{ margin: 0, border: "none" }}>
                  Policy Comparison Results
                </h3>
                <button
                  onClick={downloadCSV}
                  className="btn btn-sm"
                  id="download-csv-button"
                >
                  Download results as CSV
                </button>
              </div>

              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Policy</th>
                      <th>Cold Start Rate (%)</th>
                      <th>Mean Latency (s)</th>
                      <th>p95 Latency (s)</th>
                      <th>Total Cost (sim units)</th>
                      <th>Utilization (%)</th>
                      <th>Dropped Rate (%)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(comparisonResults).map(([pName, pData]) => {
                      const m = pData.metrics;
                      const isBestCold =
                        m.cold_start_rate !== null &&
                        Math.abs(m.cold_start_rate - bestMap.minColdRate) < 1e-6;
                      const isBestMeanLat =
                        m.mean_latency_s !== null &&
                        Math.abs(m.mean_latency_s - bestMap.minMeanLat) < 1e-6;
                      const isBestP95 =
                        m.p95_latency_s !== null &&
                        Math.abs(m.p95_latency_s - bestMap.minP95Lat) < 1e-6;
                      const isBestCost =
                        m.total_cost !== null &&
                        Math.abs(m.total_cost - bestMap.minCost) < 1e-6;
                      const isBestUtil =
                        m.utilization !== null &&
                        Math.abs(m.utilization - bestMap.maxUtil) < 1e-6;
                      const isBestDrop =
                        m.dropped_rate !== null &&
                        Math.abs(m.dropped_rate - bestMap.minDrop) < 1e-6;

                      return (
                        <tr key={pName}>
                          <td>
                            <strong>{pName}</strong>
                          </td>
                          <td className={isBestCold ? "best-value" : ""}>
                            {m.cold_start_rate !== null
                              ? (m.cold_start_rate * 100).toFixed(2) + "%"
                              : "N/A"}
                          </td>
                          <td className={isBestMeanLat ? "best-value" : ""}>
                            {m.mean_latency_s !== null
                              ? m.mean_latency_s.toFixed(3)
                              : "N/A"}
                          </td>
                          <td className={isBestP95 ? "best-value" : ""}>
                            {m.p95_latency_s !== null
                              ? m.p95_latency_s.toFixed(3)
                              : "N/A"}
                          </td>
                          <td className={isBestCost ? "best-value" : ""}>
                            {m.total_cost !== null ? m.total_cost.toFixed(1) : "N/A"}
                          </td>
                          <td className={isBestUtil ? "best-value" : ""}>
                            {m.utilization !== null
                              ? (m.utilization * 100).toFixed(1) + "%"
                              : "N/A"}
                          </td>
                          <td className={isBestDrop ? "best-value" : ""}>
                            {m.dropped_rate !== null
                              ? (m.dropped_rate * 100).toFixed(2) + "%"
                              : "N/A"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="table-legend">
                <strong>Column Definitions:</strong>
                <br />
                Cold Start Rate: Fraction of requests that experienced cold start
                initialization delay.
                <br />
                Mean Latency: Average round-trip execution latency in seconds.
                <br />
                p95 Latency: 95th percentile latency bound in seconds.
                <br />
                Total Cost: Dimensionless resource cost derived from busy and warm
                instance-seconds.
                <br />
                Utilization: Ratio of busy instance time over total active instance
                time.
                <br />
                Dropped Rate: Fraction of queued invocations that timed out prior to
                dispatch.
              </div>
            </div>

            {/* Chart 1: Arrivals and Forecast Rate */}
            <div className="chart-card">
              <div className="chart-header">
                <span className="chart-title">
                  Chart 1: Request Arrivals and Forecast Rate over Time
                </span>
              </div>
              <div className="chart-wrapper">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={activeIntervals}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                    <XAxis
                      dataKey="t"
                      unit="s"
                      tick={{ fontSize: 11, fill: "#495057" }}
                    />
                    <YAxis
                      unit=" req"
                      tick={{ fontSize: 11, fill: "#495057" }}
                    />
                    <Tooltip />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="arrivals_in_window"
                      name="Arrivals in Window (req)"
                      stroke="#1f4e79"
                      strokeWidth={1.5}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="forecast_rate"
                      name="Forecast Rate (req/s)"
                      stroke="#c05a00"
                      strokeWidth={1.5}
                      strokeDasharray="4 4"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Chart 2: Target vs Ready Instances */}
            <div className="chart-card">
              <div className="chart-header">
                <span className="chart-title">
                  Chart 2: Target Capacity vs Ready Instances over Time
                </span>
                <div>
                  <label htmlFor="chart-policy-select" style={{ fontSize: "12px", marginRight: "6px" }}>
                    Select policy:
                  </label>
                  <select
                    id="chart-policy-select"
                    className="form-select"
                    style={{ width: "auto", display: "inline-block", padding: "2px 6px" }}
                    value={chartPolicy}
                    onChange={(e) => setChartPolicy(e.target.value)}
                  >
                    {Object.keys(comparisonResults).map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="chart-wrapper">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={activeIntervals}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                    <XAxis
                      dataKey="t"
                      unit="s"
                      tick={{ fontSize: 11, fill: "#495057" }}
                    />
                    <YAxis
                      unit=" inst"
                      tick={{ fontSize: 11, fill: "#495057" }}
                    />
                    <Tooltip />
                    <Legend />
                    <Line
                      type="stepAfter"
                      dataKey="target"
                      name="Target Warm Instances"
                      stroke="#1f4e79"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="ready"
                      name="Ready Instances"
                      stroke="#2e7d32"
                      strokeWidth={1.5}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="busy"
                      name="Busy Instances"
                      stroke="#c05a00"
                      strokeWidth={1.5}
                      strokeDasharray="2 2"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Chart 3: Scatter Cold Start Rate vs Total Cost */}
            <div className="chart-card">
              <div className="chart-header">
                <span className="chart-title">
                  Chart 3: Cold Start Rate vs Total Cost Trade-Off
                </span>
              </div>
              <div className="chart-wrapper">
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 20, right: 30, bottom: 20, left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                    <XAxis
                      type="number"
                      dataKey="coldStartRate"
                      name="Cold Start Rate"
                      unit="%"
                      label={{ value: "Cold Start Rate (%)", position: "insideBottom", offset: -10, fill: "#495057", fontSize: 12 }}
                      tick={{ fontSize: 11, fill: "#495057" }}
                    />
                    <YAxis
                      type="number"
                      dataKey="totalCost"
                      name="Total Cost"
                      unit=" units"
                      label={{ value: "Total Cost (units)", angle: -90, position: "insideLeft", fill: "#495057", fontSize: 12 }}
                      tick={{ fontSize: 11, fill: "#495057" }}
                    />
                    <ZAxis range={[80, 80]} />
                    <Tooltip
                      formatter={(val, name) => [val, name]}
                      content={({ payload }) => {
                        if (!payload || !payload.length) return null;
                        const pt = payload[0].payload;
                        return (
                          <div style={{ background: "#ffffff", border: "1px solid #ced4da", padding: "6px 10px", fontSize: "12px" }}>
                            <strong>{pt.policy}</strong>
                            <div>Cold Start Rate: {pt.coldStartRate}%</div>
                            <div>Total Cost: {pt.totalCost} units</div>
                          </div>
                        );
                      }}
                    />
                    <Scatter name="Policies" data={scatterData} fill="#1f4e79">
                      {scatterData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={PALETTE[index % PALETTE.length]} />
                      ))}
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Chart 4: p95 Latency Bars */}
            <div className="chart-card">
              <div className="chart-header">
                <span className="chart-title">
                  Chart 4: 95th Percentile Latency by Policy
                </span>
              </div>
              <div className="chart-wrapper">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={latencyBarData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                    <XAxis
                      dataKey="policy"
                      tick={{ fontSize: 11, fill: "#495057" }}
                    />
                    <YAxis
                      unit="s"
                      label={{ value: "p95 Latency (s)", angle: -90, position: "insideLeft", fill: "#495057", fontSize: 12 }}
                      tick={{ fontSize: 11, fill: "#495057" }}
                    />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="p95" name="p95 Latency (s)" fill="#1f4e79">
                      {latencyBarData.map((entry, index) => (
                        <Cell key={`bar-${index}`} fill={PALETTE[index % PALETTE.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
