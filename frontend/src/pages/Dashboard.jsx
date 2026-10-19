import React, { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { API_BASE_URL } from "../config";

const STRATEGY_NAMES = {
  no_warming: "No warming",
  fixed: "Fixed warming",
  fixed_5: "Fixed warming",
  reactive: "Reactive",
  wl_full: "WarmLambda AI",
  wl_forecast_only: "Forecast only",
  wl_correction_only: "Correction only",
  oracle: "Oracle (uses future data, upper bound)",
};
const PRIMARY_STRATEGIES = ["no_warming", "fixed", "reactive", "wl_full"];
const SECONDARY_STRATEGIES = ["wl_forecast_only", "wl_correction_only", "oracle"];
const COLORS = ["#1f4e79", "#c05a00", "#2e7d32", "#66717e", "#8c4f28", "#506b57", "#263b52"];
const MARKERS = ["circle", "triangle", "square", "diamond", "cross", "star", "wye"];

function formatNumber(value, digits = 2) {
  return value === null || value === undefined || Number.isNaN(Number(value))
    ? "Not available"
    : Number(value).toFixed(digits);
}

function formatPercent(value, digits = 1) {
  return value === null || value === undefined ? "Not available" : `${(Number(value) * 100).toFixed(digits)}%`;
}

function formatTime(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function strategyName(name) {
  return STRATEGY_NAMES[name] || name;
}

function makePlanRow(item, meanExecS = 0.2) {
  const start = item.t_start ?? item.time_start_s;
  const end = item.t_end ?? item.time_end_s;
  const recommended = item.recommended_warm_instances ?? item.recommended_warm ?? 0;
  const ready = item.ready_instances ?? item.ready ?? 0;
  const shortfall = item.shortfall_instances ?? item.shortfall ?? 0;
  const duration = Math.max(end - start, 1);
  const needed = Math.ceil((item.observed_requests / duration) * meanExecS);
  const status = shortfall > 0
    ? "Short"
    : ready > needed * 1.5
      ? "Over-provisioned"
      : "OK";
  return {
    ...item,
    t_start: start,
    t_end: end,
    recommended_warm_instances: recommended,
    ready_instances: ready,
    shortfall_instances: shortfall,
    needed,
    status,
  };
}

function comparisonText(value, baseline, kind) {
  if (value === null || baseline === null || baseline === undefined || value === undefined) return "No comparison available";
  const delta = Number(value) - Number(baseline);
  const suffix = kind === "rate" ? " points" : kind === "cost" ? " units" : kind === "instances" ? " instances" : " s";
  const amount = kind === "rate" ? Math.abs(delta * 100).toFixed(1) : Math.abs(delta).toFixed(2);
  if (Math.abs(delta) < 0.000001) return "Same as No warming";
  return `${delta < 0 ? "down" : "up"} ${amount}${suffix} from No warming`;
}

function MetricCard({ label, value, comparison }) {
  return (
    <article className="metric-card">
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
      <p className="metric-comparison">{comparison}</p>
    </article>
  );
}

function EmptyState() {
  return <section className="empty-state">Choose a traffic type and run the simulation.</section>;
}

function SetupCard({ state, setState, onRun, loading, error }) {
  const update = (key, value) => setState((current) => ({ ...current, [key]: value }));
  const toggle = (name) => {
    setState((current) => {
      const policies = current.policies.includes(name)
        ? current.policies.filter((item) => item !== name)
        : [...current.policies, name];
      return { ...current, policies };
    });
  };
  return (
    <section className="card setup-card">
      <div className="setup-main">
        <div className="field">
          <label htmlFor="traffic">Traffic</label>
          <select id="traffic" value={state.scenario} onChange={(event) => update("scenario", event.target.value)}>
            <option value="moderate">Moderate traffic</option>
            <option value="high_load">High load</option>
            <option value="extreme">Extreme spikes</option>
            <option value="periodic">Repeating pattern</option>
          </select>
          <span className="field-help">{state.scenarioDescription}</span>
        </div>
        <div className="field">
          <label htmlFor="duration">Duration</label>
          <select id="duration" value={state.duration} onChange={(event) => update("duration", Number(event.target.value))}>
            <option value="600">10 minutes</option>
            <option value="1800">30 minutes</option>
            <option value="3600">1 hour</option>
          </select>
        </div>
        <fieldset className="strategy-field">
          <legend>Compare</legend>
          <div className="check-grid">
            {PRIMARY_STRATEGIES.map((name) => (
              <label key={name} className="check-label">
                <input type="checkbox" checked={state.policies.includes(name)} onChange={() => toggle(name)} />
                {strategyName(name)}
              </label>
            ))}
          </div>
          <details className="more-strategies">
            <summary>More strategies</summary>
            <div className="check-grid">
              {SECONDARY_STRATEGIES.map((name) => (
                <label key={name} className="check-label">
                  <input type="checkbox" checked={state.policies.includes(name)} onChange={() => toggle(name)} />
                  {strategyName(name)}
                </label>
              ))}
            </div>
          </details>
        </fieldset>
      </div>
      <details className="advanced-settings">
        <summary>Advanced settings</summary>
        <div className="advanced-grid">
          <label>Seed<input type="number" value={state.seed} onChange={(event) => update("seed", Number(event.target.value))} /></label>
          <label>Cold start time (s)<input type="number" step="0.1" value={state.initTime} onChange={(event) => update("initTime", Number(event.target.value))} /></label>
          <label>Average run time (s)<input type="number" step="0.1" value={state.meanExec} onChange={(event) => update("meanExec", Number(event.target.value))} /></label>
          <label>Headroom<input type="number" step="0.1" value={state.headroom} onChange={(event) => update("headroom", Number(event.target.value))} /></label>
          <label>Warm budget<input type="number" min="0" value={state.warmBudget} onChange={(event) => update("warmBudget", event.target.value)} placeholder="No limit" /></label>
          <label>Fixed instances<input type="number" min="0" value={state.fixedN} onChange={(event) => update("fixedN", Number(event.target.value))} /></label>
          <label>Forecast model<select value={state.model} onChange={(event) => update("model", event.target.value)}><option value="hgb_q90">HGB q90</option><option value="ewma">EWMA</option><option value="seasonal">Seasonal</option><option value="hgb">HGB</option><option value="gru">GRU</option></select></label>
        </div>
      </details>
      {error && <div className="error-box" role="alert">{error}</div>}
      <button type="button" className="button primary-button" onClick={onRun} disabled={loading || state.policies.length === 0}>
        {loading ? "Running simulation..." : "Run simulation"}
      </button>
    </section>
  );
}

function SummaryTab({ result, settings }) {
  const warm = result.wl_full || result[settings.policies[settings.policies.length - 1]];
  const baseline = result.no_warming;
  const warmMetrics = warm?.metrics || {};
  const baselineMetrics = baseline?.metrics || {};
  const plans = (warm?.capacity_plan || []).map(makePlanRow);
  const requestData = plans.map((item) => ({ time: item.t_start, observed: item.observed_requests, predicted: item.predicted_requests }));
  const intervalByTime = Object.fromEntries((warm?.intervals || []).map((item) => [item.t, item]));
  const capacityData = plans.map((item) => ({ time: item.t_start, recommended: item.recommended_warm_instances, ready: item.ready_instances, busy: intervalByTime[item.t_start]?.busy ?? 0 }));
  const shortfallCount = plans.filter((item) => item.shortfall_instances > 0).length;
  const rateChange = warmMetrics.cold_start_rate - baselineMetrics.cold_start_rate;
  const costChange = warmMetrics.total_cost - baselineMetrics.total_cost;
  const whatHappened = [
    rateChange < 0
      ? `WarmLambda AI reduced the cold start rate by ${(Math.abs(rateChange) * 100).toFixed(1)} points compared with No warming.`
      : "WarmLambda AI did not reduce the cold start rate compared with No warming.",
    costChange < 0
      ? `The estimated cost was ${Math.abs(costChange).toFixed(1)} units lower than No warming.`
      : `The estimated cost was ${Math.abs(costChange).toFixed(1)} units higher than No warming.`,
    `${shortfallCount} intervals had a capacity shortfall.`,
    warmMetrics.p95_latency_s < baselineMetrics.p95_latency_s
      ? "The p95 latency improved under the recommended warm capacity."
      : "The p95 latency did not improve under the recommended warm capacity.",
  ];
  return (
    <div className="tab-content">
      <div className="metric-grid">
        <MetricCard label="Cold start rate" value={formatPercent(warmMetrics.cold_start_rate)} comparison={comparisonText(warmMetrics.cold_start_rate, baselineMetrics.cold_start_rate, "rate")} />
        <MetricCard label="p95 latency" value={`${formatNumber(warmMetrics.p95_latency_s, 3)} s`} comparison={comparisonText(warmMetrics.p95_latency_s, baselineMetrics.p95_latency_s, "latency")} />
        <MetricCard label="Estimated cost" value={`${formatNumber(warmMetrics.total_cost, 1)} units`} comparison={comparisonText(warmMetrics.total_cost, baselineMetrics.total_cost, "cost")} />
        <MetricCard label="Peak recommended warm" value={formatNumber(warm?.summary?.peak_recommended_warm, 0)} comparison={comparisonText(warm?.summary?.peak_recommended_warm, baseline?.summary?.peak_recommended_warm, "instances")} />
      </div>
      <section className="card narrative">
        <h2>What happened</h2>
        {whatHappened.map((sentence) => <p key={sentence}>{sentence}</p>)}
      </section>
      <section className="card chart-card">
        <h2>Requests per interval</h2>
        <div className="chart-large"><ResponsiveContainer width="100%" height="100%"><LineChart data={requestData}><CartesianGrid stroke="#e2e6ea" /><XAxis dataKey="time" tickFormatter={formatTime} /><YAxis /><Tooltip labelFormatter={(value) => formatTime(value)} /><Legend /><Line type="monotone" dataKey="observed" name="Observed requests" stroke="#1f4e79" dot={false} /><Line type="monotone" dataKey="predicted" name="Predicted requests" stroke="#c05a00" dot={false} /></LineChart></ResponsiveContainer></div>
        <h2 className="chart-subtitle">Warm instances</h2>
        <div className="chart-large"><ResponsiveContainer width="100%" height="100%"><LineChart data={capacityData}><CartesianGrid stroke="#e2e6ea" /><XAxis dataKey="time" tickFormatter={formatTime} /><YAxis allowDecimals={false} /><Tooltip labelFormatter={(value) => formatTime(value)} /><Legend /><Line type="stepAfter" dataKey="recommended" name="Recommended warm" stroke="#1f4e79" dot={false} /><Line type="monotone" dataKey="ready" name="Ready instances" stroke="#2e7d32" dot={false} /><Line type="monotone" dataKey="busy" name="Busy instances" stroke="#c05a00" dot={false} /></LineChart></ResponsiveContainer></div>
        <p className="chart-caption">Ready instances lag the recommendation because new instances take time to start.</p>
      </section>
      {Object.values(result).length > 1 && Object.values(result).every((item) => JSON.stringify(item.metrics) === JSON.stringify(Object.values(result)[0].metrics)) && <div className="notice-box">These strategies gave identical results for these settings. Try Extreme spikes or a longer duration.</div>}
    </div>
  );
}

function CapacityPlanTab({ result, meanExecS }) {
  const [strategy, setStrategy] = useState(result.wl_full ? "wl_full" : Object.keys(result)[0]);
  const [page, setPage] = useState(0);
  const [onlyShort, setOnlyShort] = useState(false);
  const [printMode, setPrintMode] = useState(false);
  const data = (result[strategy]?.capacity_plan || []).map((item) => makePlanRow(item, meanExecS));
  const filtered = onlyShort ? data.filter((item) => item.shortfall_instances > 0) : data;
  const pageRows = filtered.slice(page * 50, (page + 1) * 50);
  const visibleRows = printMode ? filtered : pageRows;
  const pages = Math.max(1, Math.ceil(filtered.length / 50));
  const download = () => {
    const rows = result[strategy]?.capacity_plan || [];
    const header = ["time_start_s", "time_end_s", "observed_requests", "predicted_requests", "recommended_warm_instances", "ready_instances", "cold_starts", "avg_latency_s", "p95_latency_s", "dropped_requests", "estimated_cost_units", "shortfall_instances"];
    const csv = [header.join(","), ...rows.map((item) => [item.t_start, item.t_end, item.observed_requests, item.predicted_requests ?? "", item.recommended_warm_instances, item.ready_instances, item.cold_starts, item.avg_latency_s ?? "", item.p95_latency_s ?? "", item.dropped_requests, item.estimated_cost_units, item.shortfall_instances].join(","))].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `capacity_plan_${strategy}.csv`; link.click(); URL.revokeObjectURL(url);
  };
  return (
    <div className="tab-content">
      <section className="card plan-card">
        <div className="plan-toolbar">
          <label>Strategy<select value={strategy} onChange={(event) => { setStrategy(event.target.value); setPage(0); }}>{Object.keys(result).map((name) => <option key={name} value={name}>{strategyName(name)}</option>)}</select></label>
          <div className="toolbar-actions"><label className="filter-label"><input type="checkbox" checked={onlyShort} onChange={(event) => { setOnlyShort(event.target.checked); setPage(0); }} /> Only short intervals</label><button className="button" type="button" onClick={download}>Download CSV</button><button className="button" type="button" onClick={() => { setPrintMode(true); window.setTimeout(() => window.print(), 0); window.addEventListener("afterprint", () => setPrintMode(false), { once: true }); }}>Print report</button></div>
        </div>
        <p className="column-help">Requests are observed arrivals. Predicted requests are the policy forecast for the interval. Recommended and ready show planned versus available capacity. Cold starts and latency show the observed outcome. Cost is in simulator units.</p>
        <div className="table-scroll"><table className="plan-table"><thead><tr><th>Time</th><th>Requests</th><th>Predicted requests</th><th>Recommended warm instances</th><th>Ready instances</th><th>Cold starts</th><th>Avg latency (s)</th><th>Cost (units)</th><th>Status</th></tr></thead><tbody>{visibleRows.map((item) => <tr key={`${item.t_start}-${item.t_end}`}><td>{formatTime(item.t_start)} to {formatTime(item.t_end)}</td><td>{item.observed_requests}</td><td>{item.predicted_requests === null ? "Not available" : formatNumber(item.predicted_requests, 1)}</td><td>{item.recommended_warm_instances}</td><td>{item.ready_instances}</td><td>{item.cold_starts}</td><td>{item.avg_latency_s === null ? "Not available" : formatNumber(item.avg_latency_s, 3)}</td><td>{formatNumber(item.estimated_cost_units, 1)}</td><td><span className={`status status-${item.status.toLowerCase().replace("-", "")}`}>{item.status}</span></td></tr>)}</tbody></table></div>
        <div className="pagination"><span>Showing {pageRows.length} of {filtered.length} intervals</span><div><button className="button" type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {page + 1} of {pages}</span><button className="button" type="button" disabled={page + 1 >= pages} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
      </section>
    </div>
  );
}

function CompareTab({ result }) {
  const entries = Object.entries(result);
  const metrics = entries.map(([name, item], index) => ({ name, label: strategyName(name), color: COLORS[index % COLORS.length], marker: MARKERS[index % MARKERS.length], ...item.metrics }));
  const best = (key, descending = false) => {
    const values = metrics.map((item) => item[key]).filter((value) => value !== null);
    return descending ? Math.max(...values) : Math.min(...values);
  };
  const scatter = metrics.map((item) => ({ ...item, x: item.cold_start_rate * 100, y: item.total_cost }));
  const latency = metrics.map((item) => ({ name: item.label, p95: item.p95_latency_s, fill: item.color }));
  return (
    <div className="tab-content">
      <section className="card">
        <div className="table-scroll"><table className="compare-table"><thead><tr><th>Strategy</th><th>Cold start rate</th><th>Avg latency</th><th>p95 latency</th><th>Cost</th><th>Utilization</th><th>Dropped</th></tr></thead><tbody>{metrics.map((item) => <tr key={item.name}><td>{item.label}</td>{[["cold_start_rate", formatPercent(item.cold_start_rate)], ["mean_latency_s", `${formatNumber(item.mean_latency_s, 3)} s`], ["p95_latency_s", `${formatNumber(item.p95_latency_s, 3)} s`], ["total_cost", formatNumber(item.total_cost, 1)], ["utilization", formatPercent(item.utilization)], ["dropped_rate", formatPercent(item.dropped_rate)]].map(([key, value]) => <td key={key} className={item[key] === best(key) ? "best-value" : ""}>{value}</td>)}</tr>)}</tbody></table></div>
        <p className="table-caption">Lower cold start rate, latency, cost, and dropped rate are better. Higher utilization is better.</p>
      </section>
      <div className="compare-charts">
        <section className="card chart-card"><h2>Cold starts and cost</h2><div className="chart-medium"><ResponsiveContainer width="100%" height="100%"><ScatterChart><CartesianGrid stroke="#e2e6ea" /><XAxis type="number" dataKey="x" name="Cold start rate" unit="%" /><YAxis type="number" dataKey="y" name="Cost" /><Tooltip cursor={{ strokeDasharray: "3 3" }} formatter={(value, name) => [formatNumber(value, 2), name]} /><Scatter data={scatter} name="Strategies" fill="#1f4e79" /></ScatterChart></ResponsiveContainer></div><p className="chart-caption">Closer to the bottom left is better.</p></section>
        <section className="card chart-card"><h2>p95 latency</h2><div className="chart-medium"><ResponsiveContainer width="100%" height="100%"><BarChart data={latency} layout="vertical"><CartesianGrid stroke="#e2e6ea" /><XAxis type="number" /><YAxis type="category" dataKey="name" width={110} /><Tooltip /><Bar dataKey="p95" name="p95 latency" fill="#c05a00"><LabelList dataKey="p95" position="right" formatter={(value) => formatNumber(value, 3)} /></Bar></BarChart></ResponsiveContainer></div></section>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [descriptions, setDescriptions] = useState({});
  const [state, setState] = useState({ scenario: "moderate", scenarioDescription: "Moderate traffic", duration: 3600, policies: PRIMARY_STRATEGIES, seed: 42, initTime: 1, meanExec: 0.2, headroom: 0.5, warmBudget: "", fixedN: 5, model: "hgb_q90" });
  const [result, setResult] = useState(null);
  const [tab, setTab] = useState("summary");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    fetch(`${API_BASE_URL}/scenarios`).then((response) => response.json()).then((data) => {
      const map = Object.fromEntries(data.scenarios.map((item) => [item.name, item.description]));
      setDescriptions(map);
      setState((current) => ({ ...current, scenarioDescription: map[current.scenario] || current.scenarioDescription }));
    }).catch(() => setError("Could not load traffic scenarios. Check that the backend is running."));
  }, []);
  useEffect(() => {
    setState((current) => ({ ...current, scenarioDescription: descriptions[current.scenario] || current.scenarioDescription }));
  }, [descriptions, state.scenario]);
  const run = async () => {
    setError("");
    if (!state.policies.length) { setError("Select at least one strategy."); return; }
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/compare`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario: state.scenario, policies: state.policies, duration_s: state.duration, seed: state.seed, init_time_s: state.initTime, mean_exec_s: state.meanExec, headroom: state.headroom, warm_budget: state.warmBudget === "" ? null : Number(state.warmBudget), fixed_n: state.fixedN, model: state.model }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail?.[0]?.msg || data.detail || "The simulation could not be completed.");
      setResult(data.results);
      setTab("summary");
    } catch (runError) {
      setError(runError.message);
    } finally {
      setLoading(false);
    }
  };
  const selectedResult = result ? result.wl_full || result[Object.keys(result)[0]] : null;
  const settings = useMemo(() => ({ ...state }), [state]);
  return (
    <div className="dashboard">
      <section className="process-strip" aria-label="Simulation steps">{["Simulate traffic", "Predict demand", "Recommend warm instances", "Report results"].map((step, index) => <div className="process-step" key={step}><span>{index + 1}</span>{step}</div>)}</section>
      <SetupCard state={state} setState={setState} onRun={run} loading={loading} error={error} />
      {!result && <EmptyState />}
      {result && selectedResult && <section className="results-shell">
        <div className="tab-list" role="tablist">{[["summary", "Summary"], ["plan", "Warm capacity plan"], ["compare", "Compare strategies"]].map(([value, label]) => <button type="button" role="tab" aria-selected={tab === value} className={tab === value ? "tab active" : "tab"} onClick={() => setTab(value)} key={value}>{label}</button>)}</div>
        {tab === "summary" && <SummaryTab result={result} settings={settings} />}
        {tab === "plan" && <CapacityPlanTab result={result} meanExecS={settings.meanExec} />}
        {tab === "compare" && <CompareTab result={result} />}
      </section>}
    </div>
  );
}
