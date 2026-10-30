import React, { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Line,
  ReferenceArea,
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
  oracle: "Oracle (uses future data)",
};
const STRATEGY_TAGS = {
  no_warming: "baseline",
  fixed: "baseline",
  reactive: "baseline",
  wl_full: "proposed",
  wl_forecast_only: "ablation",
  wl_correction_only: "ablation",
  oracle: "upper bound",
};
const STRATEGY_COLORS = {
  no_warming: "#8a97a3",
  fixed: "#4cb5d6",
  fixed_5: "#4cb5d6",
  reactive: "#5cbf85",
  wl_full: "#f0a23b",
  wl_forecast_only: "#d9c35c",
  wl_correction_only: "#e0805a",
  oracle: "#e6ebf0",
};
const PRIMARY_STRATEGIES = ["no_warming", "fixed", "reactive", "wl_full"];
const SECONDARY_STRATEGIES = ["wl_forecast_only", "wl_correction_only", "oracle"];
const SCENARIO_LABELS = {
  moderate: "Moderate traffic",
  high_load: "High load",
  extreme: "Extreme spikes",
  periodic: "Repeating pattern",
};
const LABEL_POSITIONS = { no_warming: "right", reactive: "top", oracle: "right" };
const AXIS = { stroke: "#6a7885", fontSize: 12, tickLine: false };
const GRID = "#26323d";

function formatNumber(value, digits = 2) {
  return value === null || value === undefined || Number.isNaN(Number(value))
    ? "Not available"
    : Number(value).toFixed(digits);
}

function formatPercent(value, digits = 1) {
  return value === null || value === undefined || Number.isNaN(Number(value))
    ? "Not available"
    : `${(Number(value) * 100).toFixed(digits)}%`;
}

function formatTime(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function strategyName(name) {
  return STRATEGY_NAMES[name] || name;
}

function strategyColor(name) {
  return STRATEGY_COLORS[name] || "#8a97a3";
}

function durationLabel(seconds) {
  return seconds >= 3600 ? `${seconds / 3600} hour` : `${seconds / 60} minutes`;
}

function makePlanRow(item, meanExecS = 0.2) {
  const start = item.t_start ?? item.time_start_s;
  const end = item.t_end ?? item.time_end_s;
  const recommended = item.recommended_warm_instances ?? item.recommended_warm ?? 0;
  const ready = item.ready_instances ?? item.ready ?? 0;
  const shortfall = item.shortfall_instances ?? item.shortfall ?? 0;
  const duration = Math.max(end - start, 1);
  const needed = Math.ceil((item.observed_requests / duration) * meanExecS);
  const status = shortfall > 0 ? "Short" : ready > needed * 1.5 ? "Over-provisioned" : "OK";
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

/* Returns the comparison sentence and whether the change is good (lower is better for every metric except peak). */
function compare(value, baseline, kind) {
  if (value === null || value === undefined || baseline === null || baseline === undefined || Number.isNaN(value - baseline)) {
    return { text: "No comparison available", tone: "" };
  }
  const delta = Number(value) - Number(baseline);
  if (Math.abs(delta) < 0.000001) return { text: "Same as No warming", tone: "" };
  const units = { rate: " points", cost: " units", instances: " instances", latency: " s" }[kind];
  const amount = kind === "rate" ? Math.abs(delta * 100).toFixed(2) : Math.abs(delta).toFixed(kind === "latency" ? 3 : 1);
  const direction = delta < 0 ? "lower" : "higher";
  const tone = kind === "instances" ? "" : delta < 0 ? "good" : "bad";
  return { text: `${amount}${units} ${direction} than No warming`, tone };
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="chart-tooltip">
      <strong>{formatTime(label)}</strong>
      {payload.filter((entry) => entry.value !== null && entry.value !== undefined).map((entry) => (
        <div key={entry.dataKey}>
          <span>{entry.name}</span>
          <b>{typeof entry.value === "number" ? Number(entry.value).toFixed(entry.value % 1 ? 1 : 0) : entry.value}</b>
        </div>
      ))}
    </div>
  );
}

function MetricCard({ label, value, unit, comparison, tone }) {
  const className = tone === "good" ? "is-good" : tone === "bad" ? "is-bad" : tone === "key" ? "is-key" : "";
  return (
    <article className={`metric-card ${className}`}>
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}{unit && <small>{unit}</small>}</p>
      <p className={`metric-comparison ${tone === "good" ? "delta-good" : tone === "bad" ? "delta-bad" : ""}`}>{comparison}</p>
    </article>
  );
}

function EmptyState() {
  const steps = [
    ["01", "Simulate traffic", "A request stream is generated for the chosen scenario, with steady load, ramps or sudden spikes."],
    ["02", "Predict demand", "A forecaster estimates the request rate for the next 20 second interval from what it has seen so far."],
    ["03", "Recommend warm instances", "Little's Law turns the forecast into a warm instance count, with headroom and a reactive correction."],
    ["04", "Report results", "Every strategy is replayed on the same traffic so cold starts, latency and cost compare fairly."],
  ];
  return (
    <section className="empty-state">
      <h2>Compare warm-capacity strategies on the same traffic</h2>
      <p>Pick a traffic type in the settings panel and run the simulation. Extreme spikes is the scenario where the strategies differ most.</p>
      <div className="pipeline">
        {steps.map(([number, title, body]) => (
          <div className="pipe-step" key={number}>
            <b>{number}</b>
            <h3>{title}</h3>
            <p>{body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Controls({ state, setState, onRun, loading, error, description }) {
  const update = (key, value) => setState((current) => ({ ...current, [key]: value }));
  const toggle = (name) => {
    setState((current) => {
      const policies = current.policies.includes(name)
        ? current.policies.filter((item) => item !== name)
        : [...current.policies, name];
      return { ...current, policies };
    });
  };
  const row = (name) => (
    <label key={name} className="strategy-row">
      <input type="checkbox" checked={state.policies.includes(name)} onChange={() => toggle(name)} />
      <span className="swatch" style={{ background: strategyColor(name) }} />
      <span className="strategy-name">{strategyName(name)}</span>
      <span className="strategy-tag">{STRATEGY_TAGS[name]}</span>
    </label>
  );
  return (
    <aside className="controls" aria-label="Simulation settings">
      <div className="controls-section">
        <p className="eyebrow">Traffic</p>
        <div className="field">
          <label htmlFor="traffic">Scenario</label>
          <select id="traffic" value={state.scenario} onChange={(event) => update("scenario", event.target.value)}>
            <option value="moderate">Moderate traffic</option>
            <option value="high_load">High load</option>
            <option value="extreme">Extreme spikes</option>
            <option value="periodic">Repeating pattern</option>
          </select>
          <span className="field-help">{description}</span>
        </div>
        <div className="field">
          <label htmlFor="duration">Duration</label>
          <select id="duration" value={state.duration} onChange={(event) => update("duration", Number(event.target.value))}>
            <option value="600">10 minutes</option>
            <option value="1800">30 minutes</option>
            <option value="3600">1 hour</option>
          </select>
        </div>
      </div>
      <div className="controls-section">
        <p className="eyebrow">Strategies to compare</p>
        <div className="strategy-list">{PRIMARY_STRATEGIES.map(row)}</div>
        <details style={{ marginTop: 10 }}>
          <summary>More strategies</summary>
          <div className="strategy-list">{SECONDARY_STRATEGIES.map(row)}</div>
        </details>
      </div>
      <div className="controls-section">
        <details>
          <summary>Advanced settings</summary>
          <div className="advanced-grid">
            <label>Seed<input type="number" value={state.seed} onChange={(event) => update("seed", Number(event.target.value))} /></label>
            <label>Cold start (s)<input type="number" step="0.1" value={state.initTime} onChange={(event) => update("initTime", Number(event.target.value))} /></label>
            <label>Run time (s)<input type="number" step="0.1" value={state.meanExec} onChange={(event) => update("meanExec", Number(event.target.value))} /></label>
            <label>Headroom<input type="number" step="0.1" value={state.headroom} onChange={(event) => update("headroom", Number(event.target.value))} /></label>
            <label>Warm budget<input type="number" min="0" value={state.warmBudget} onChange={(event) => update("warmBudget", event.target.value)} placeholder="No limit" /></label>
            <label>Fixed instances<input type="number" min="0" value={state.fixedN} onChange={(event) => update("fixedN", Number(event.target.value))} /></label>
            <label className="wide">Forecast model
              <select value={state.model} onChange={(event) => update("model", event.target.value)}>
                <option value="ridge_q90">Ridge q90 (trained)</option>
                <option value="ewma">EWMA (no training)</option>
                <option value="seasonal">Seasonal</option>
                <option value="ridge">Ridge (trained)</option>
                <option value="gru">GRU (trained)</option>
              </select>
            </label>
          </div>
        </details>
      </div>
      <div className="run-bar">
        {error && <div className="error-box" role="alert">{error}</div>}
        <button type="button" className="button primary-button" onClick={onRun} disabled={loading || state.policies.length === 0}>
          {loading ? "Running simulation..." : "Run simulation"}
        </button>
      </div>
    </aside>
  );
}

function Legend({ items }) {
  return (
    <div className="legend">
      {items.map(([label, color, kind]) => (
        <span key={label} style={{ color: kind === "dash" ? color : undefined }}>
          <i className={kind || ""} style={{ background: color }} />
          <em style={{ color: "#93a1ae", fontStyle: "normal" }}>{label}</em>
        </span>
      ))}
    </div>
  );
}

function SummaryTab({ result, policies, info }) {
  const warmKey = result.wl_full ? "wl_full" : policies[policies.length - 1];
  const warm = result[warmKey] || Object.values(result)[0];
  const baseline = result.no_warming;
  const warmMetrics = warm?.metrics || {};
  const baseMetrics = baseline?.metrics;
  const plans = (warm?.capacity_plan || []).map((item) => makePlanRow(item));
  const intervalByTime = Object.fromEntries((warm?.intervals || []).map((item) => [item.t, item]));
  const requestData = plans.map((item) => ({ time: item.t_start, observed: item.observed_requests, predicted: item.predicted_requests }));
  const capacityData = plans.map((item) => ({
    time: item.t_start,
    recommended: item.recommended_warm_instances,
    ready: item.ready_instances,
    busy: intervalByTime[item.t_start]?.busy ?? 0,
  }));
  const shortIntervals = plans.filter((item) => item.shortfall_instances > 0);
  const hasBaseline = Boolean(baseMetrics) && warmKey !== "no_warming";
  const rate = hasBaseline ? compare(warmMetrics.cold_start_rate, baseMetrics.cold_start_rate, "rate") : { text: "Add No warming to compare", tone: "" };
  const latency = hasBaseline ? compare(warmMetrics.p95_latency_s, baseMetrics.p95_latency_s, "latency") : { text: "Add No warming to compare", tone: "" };
  const cost = hasBaseline ? compare(warmMetrics.total_cost, baseMetrics.total_cost, "cost") : { text: "Add No warming to compare", tone: "" };
  const peak = warm?.summary?.peak_recommended_warm;
  const average = warm?.summary?.average_recommended_warm;

  const points = [];
  if (hasBaseline) {
    const rateChange = warmMetrics.cold_start_rate - baseMetrics.cold_start_rate;
    const costChange = warmMetrics.total_cost - baseMetrics.total_cost;
    points.push(rateChange < -0.000001
      ? { tone: "good", text: `${strategyName(warmKey)} cut the cold start rate by ${(Math.abs(rateChange) * 100).toFixed(2)} points compared with No warming.` }
      : { tone: "neutral", text: `${strategyName(warmKey)} did not reduce the cold start rate compared with No warming on this run.` });
    points.push(costChange <= 0
      ? { tone: "good", text: `Estimated cost was ${Math.abs(costChange).toFixed(1)} units lower than No warming.` }
      : { tone: "neutral", text: `Estimated cost was ${Math.abs(costChange).toFixed(1)} units higher than No warming, the price of holding warm capacity.` });
    points.push(warmMetrics.p95_latency_s < baseMetrics.p95_latency_s - 0.0005
      ? { tone: "good", text: "p95 latency improved under the recommended warm capacity." }
      : { tone: "neutral", text: "p95 latency did not improve under the recommended warm capacity." });
  }
  points.push(shortIntervals.length
    ? { tone: "bad", text: `${shortIntervals.length} of ${plans.length} intervals had fewer ready instances than needed. They are shaded red below.` }
    : { tone: "good", text: "No interval had a capacity shortfall." });

  const identical = Object.values(result).length > 1
    && Object.values(result).every((item) => JSON.stringify(item.metrics) === JSON.stringify(Object.values(result)[0].metrics));

  return (
    <div className="tab-content">
      <div className="metric-grid">
        <MetricCard label="Cold start rate" value={formatPercent(warmMetrics.cold_start_rate, 2)} comparison={rate.text} tone={rate.tone} />
        <MetricCard label="p95 latency" value={formatNumber(warmMetrics.p95_latency_s, 3)} unit="s" comparison={latency.text} tone={latency.tone} />
        <MetricCard label="Estimated cost" value={formatNumber(warmMetrics.total_cost, 0)} unit="units" comparison={cost.text} tone={cost.tone} />
        <MetricCard
          label="Peak recommended warm"
          value={formatNumber(peak, 0)}
          unit="instances"
          comparison={average !== undefined ? `Average ${formatNumber(average, 1)} across ${plans.length} intervals` : "Not available"}
          tone="key"
        />
      </div>

      <section className="card verdict">
        <h2>What happened with {strategyName(warmKey)}</h2>
        <ul>{points.map((point) => <li key={point.text} className={point.tone}>{point.text}</li>)}</ul>
      </section>

      {identical && <div className="notice-box">These strategies gave identical results for these settings. Try Extreme spikes or a longer duration.</div>}

      <section className="card chart-card">
        <div className="card-head">
          <div>
            <h2>Requests per interval</h2>
            <p className="card-sub">Each interval is 20 seconds. The dashed line is what the forecaster expected.{policies.length > 0 && info?.model === "hgb_q90" ? " The q90 model aims at the 90th percentile, so it sits above the observed line on purpose." : ""}</p>
          </div>
          <Legend items={[["Observed", "#4cb5d6"], ["Predicted", "#f0a23b", "dash"]]} />
        </div>
        <div className="chart-large">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={requestData} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="time" type="number" domain={["dataMin", "dataMax"]} tickFormatter={formatTime} {...AXIS} />
              <YAxis {...AXIS} width={44} axisLine={false} />
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#364553" }} />
              <Area type="monotone" dataKey="observed" name="Observed requests" stroke="#4cb5d6" strokeWidth={1.6} fill="#4cb5d6" fillOpacity={0.14} isAnimationActive={false} />
              <Line type="monotone" dataKey="predicted" name="Predicted requests" stroke="#f0a23b" strokeWidth={1.6} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-split">
          <div className="card-head">
            <div>
              <h2>Warm instances</h2>
              <p className="card-sub">The recommendation steps up before demand arrives. Ready instances trail it because new instances take time to start.</p>
            </div>
            <Legend items={[["Recommended", "#f0a23b"], ["Ready", "#4cb5d6"], ["Busy", "#8a97a3", "dash"], ["Shortfall", "#e5645f", "box"]]} />
          </div>
          <div className="chart-large">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={capacityData} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="time" type="number" domain={["dataMin", "dataMax"]} tickFormatter={formatTime} {...AXIS} />
                <YAxis allowDecimals={false} {...AXIS} width={44} axisLine={false} />
                <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#364553" }} />
                {shortIntervals.map((item) => (
                  <ReferenceArea key={item.t_start} x1={item.t_start} x2={item.t_end} fill="#e5645f" fillOpacity={0.22} stroke="none" ifOverflow="hidden" />
                ))}
                <Line type="stepAfter" dataKey="busy" name="Busy instances" stroke="#8a97a3" strokeWidth={1.2} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="ready" name="Ready instances" stroke="#4cb5d6" strokeWidth={1.6} dot={false} isAnimationActive={false} />
                <Line type="stepAfter" dataKey="recommended" name="Recommended warm" stroke="#f0a23b" strokeWidth={2.2} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>
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
  const scale = Math.max(1, ...data.map((item) => Math.max(item.recommended_warm_instances, item.ready_instances)));
  const download = () => {
    const rows = result[strategy]?.capacity_plan || [];
    const header = ["time_start_s", "time_end_s", "observed_requests", "predicted_requests", "recommended_warm_instances", "ready_instances", "cold_starts", "avg_latency_s", "p95_latency_s", "dropped_requests", "estimated_cost_units", "shortfall_instances"];
    const csv = [header.join(","), ...rows.map((item) => [item.t_start, item.t_end, item.observed_requests, item.predicted_requests ?? "", item.recommended_warm_instances, item.ready_instances, item.cold_starts, item.avg_latency_s ?? "", item.p95_latency_s ?? "", item.dropped_requests, item.estimated_cost_units, item.shortfall_instances].join(","))].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `capacity_plan_${strategy}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="tab-content">
      <section className="card plan-card">
        <div className="plan-toolbar">
          <label>
            Strategy
            <select value={strategy} onChange={(event) => { setStrategy(event.target.value); setPage(0); }}>
              {Object.keys(result).map((name) => <option key={name} value={name}>{strategyName(name)}</option>)}
            </select>
          </label>
          <div className="toolbar-actions">
            <label className="filter-label" style={{ minWidth: 0 }}>
              <input type="checkbox" checked={onlyShort} onChange={(event) => { setOnlyShort(event.target.checked); setPage(0); }} />
              Only short intervals
            </label>
            <button className="button" type="button" onClick={download}>Download CSV</button>
            <button className="button" type="button" onClick={() => { setPrintMode(true); window.setTimeout(() => window.print(), 0); window.addEventListener("afterprint", () => setPrintMode(false), { once: true }); }}>Print report</button>
          </div>
        </div>
        <div className="table-scroll">
          <table className="plan-table">
            <thead>
              <tr>
                <th>Interval</th>
                <th className="num">Requests</th>
                <th className="num">Predicted</th>
                <th className="num">Recommended</th>
                <th className="num">Ready</th>
                <th className="num">Capacity</th>
                <th className="num">Cold starts</th>
                <th className="num">Avg latency</th>
                <th className="num">Cost</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((item) => (
                <tr key={`${item.t_start}-${item.t_end}`}>
                  <td>{formatTime(item.t_start)} to {formatTime(item.t_end)}</td>
                  <td className="num">{item.observed_requests}</td>
                  <td className="num">{item.predicted_requests === null || item.predicted_requests === undefined ? "n/a" : formatNumber(item.predicted_requests, 1)}</td>
                  <td className="num">{item.recommended_warm_instances}</td>
                  <td className="num">{item.ready_instances}</td>
                  <td className="num">
                    <span className="cap-bars" title="Amber bar is recommended capacity, cyan tick is ready capacity">
                      <span className="cap-track">
                        <i className="rec" style={{ width: `${(item.recommended_warm_instances / scale) * 100}%` }} />
                        <i className="rdy" style={{ width: `${(item.ready_instances / scale) * 100}%` }} />
                      </span>
                    </span>
                  </td>
                  <td className="num">{item.cold_starts}</td>
                  <td className="num">{item.avg_latency_s === null || item.avg_latency_s === undefined ? "n/a" : formatNumber(item.avg_latency_s, 3)}</td>
                  <td className="num">{formatNumber(item.estimated_cost_units, 1)}</td>
                  <td><span className={`status status-${item.status.toLowerCase().replace("-", "")}`}>{item.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="column-help">Requests are observed arrivals. Predicted is the policy forecast for the interval. Recommended is the warm instance count the policy asked for; ready is what was actually available. Cost is in simulator units.</p>
        <div className="pagination">
          <span>Showing {pageRows.length} of {filtered.length} intervals</span>
          <div>
            <button className="button" type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button>
            <span>Page {page + 1} of {pages}</span>
            <button className="button" type="button" disabled={page + 1 >= pages} onClick={() => setPage((value) => value + 1)}>Next</button>
          </div>
        </div>
      </section>
    </div>
  );
}

function CompareTab({ result }) {
  const metrics = Object.entries(result).map(([name, item]) => ({ name, label: strategyName(name), color: strategyColor(name), ...item.metrics }));
  const best = (key, higher = false) => {
    const values = metrics.map((item) => item[key]).filter((value) => value !== null && value !== undefined);
    if (new Set(values).size < 2) return null;
    return higher ? Math.max(...values) : Math.min(...values);
  };
  const columns = [
    ["cold_start_rate", "Cold start rate", (v) => formatPercent(v, 2), false],
    ["mean_latency_s", "Avg latency", (v) => `${formatNumber(v, 3)} s`, false],
    ["p95_latency_s", "p95 latency", (v) => `${formatNumber(v, 3)} s`, false],
    ["total_cost", "Cost (units)", (v) => formatNumber(v, 0), false],
    ["utilization", "Utilization", (v) => formatPercent(v, 1), true],
    ["dropped_rate", "Dropped", (v) => formatPercent(v, 2), false],
  ];
  const rateBars = metrics.map((item) => ({ name: item.label, rate: item.cold_start_rate * 100, color: item.color }));
  return (
    <div className="tab-content">
      <section className="card table-card">
        <div className="table-scroll">
          <table className="compare-table">
            <thead>
              <tr>
                <th>Strategy</th>
                {columns.map(([key, label]) => <th key={key} className="num">{label}</th>)}
              </tr>
            </thead>
            <tbody>
              {metrics.map((item) => (
                <tr key={item.name}>
                  <td><span className="name-cell"><span className="swatch" style={{ background: item.color }} />{item.label}</span></td>
                  {columns.map(([key, , format, higher]) => (
                    <td key={key} className={`num ${item[key] === best(key, higher) ? "best-value" : ""}`}>{format(item[key])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="table-caption">Green marks the best value in each column. Lower is better except utilization.</p>
      </section>
      <div className="compare-charts">
        <section className="card chart-card">
          <div className="card-head"><div><h2>Cold starts against cost</h2><p className="card-sub">Closer to the bottom left is better.</p></div></div>
          <div className="chart-medium">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 18, right: 76, left: 0, bottom: 14 }}>
                <CartesianGrid stroke={GRID} />
                <XAxis type="number" dataKey="x" name="Cold start rate" unit="%" domain={["auto", "auto"]} tickFormatter={(v) => Number(v).toFixed(2)} label={{ value: "Cold start rate (%)", position: "insideBottom", offset: -8, fill: "#6a7885", fontSize: 12 }} {...AXIS} />
                <YAxis type="number" dataKey="y" name="Cost" domain={["auto", "auto"]} width={58} tickFormatter={(v) => Number(v).toFixed(0)} {...AXIS} />
                <Tooltip cursor={{ strokeDasharray: "3 3", stroke: "#364553" }} contentStyle={{ background: "#212c37", border: "1px solid #364553", borderRadius: 4, fontSize: 12.5 }} formatter={(value, name) => [formatNumber(value, 2), name]} />
                {metrics.map((item) => (
                  <Scatter key={item.name} name={item.label} data={[{ x: item.cold_start_rate * 100, y: item.total_cost, label: item.label }]} fill={item.color} isAnimationActive={false}>
                    <LabelList dataKey="label" position={LABEL_POSITIONS[item.name] || "top"} fill="#c4cdd5" fontSize={11} />
                  </Scatter>
                ))}
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </section>
        <section className="card chart-card">
          <div className="card-head"><div><h2>Cold start rate</h2><p className="card-sub">Share of requests that waited for a new instance.</p></div></div>
          <div className="chart-medium">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rateBars} layout="vertical" margin={{ top: 4, right: 52, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={GRID} horizontal={false} />
                <XAxis type="number" unit="%" tickFormatter={(v) => Number(v).toFixed(2)} {...AXIS} />
                <YAxis type="category" dataKey="name" width={150} {...AXIS} stroke="#93a1ae" />
                <Tooltip cursor={{ fill: "#1a232c" }} contentStyle={{ background: "#212c37", border: "1px solid #364553", borderRadius: 4, fontSize: 12.5 }} formatter={(value) => [`${Number(value).toFixed(3)}%`, "Cold start rate"]} />
                <Bar dataKey="rate" isAnimationActive={false}>
                  {rateBars.map((item) => <Cell key={item.name} fill={item.color} />)}
                  <LabelList dataKey="rate" position="right" fill="#c4cdd5" fontSize={11} formatter={(v) => `${Number(v).toFixed(2)}%`} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [descriptions, setDescriptions] = useState({});
  const [state, setState] = useState({ scenario: "extreme", duration: 3600, policies: PRIMARY_STRATEGIES, seed: 42, initTime: 1, meanExec: 0.2, headroom: 0.5, warmBudget: "", fixedN: 5, model: "ewma" });
  const [result, setResult] = useState(null);
  const [runInfo, setRunInfo] = useState(null);
  const [tab, setTab] = useState("summary");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE_URL}/scenarios`)
      .then((response) => response.json())
      .then((data) => setDescriptions(Object.fromEntries(data.scenarios.map((item) => [item.name, item.description]))))
      .catch(() => setError("Could not load traffic scenarios. Check that the backend is running."));
  }, []);

  const run = async () => {
    setError("");
    if (!state.policies.length) { setError("Select at least one strategy."); return; }
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario: state.scenario,
          policies: state.policies,
          duration_s: state.duration,
          seed: state.seed,
          init_time_s: state.initTime,
          mean_exec_s: state.meanExec,
          headroom: state.headroom,
          warm_budget: state.warmBudget === "" ? null : Number(state.warmBudget),
          fixed_n: state.fixedN,
          model: state.model,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail?.[0]?.msg || data.detail || "The simulation could not be completed.");
      setResult(data.results);
      setRunInfo({ scenario: state.scenario, duration: state.duration, seed: state.seed, model: state.model, meanExec: state.meanExec, policies: state.policies });
      setTab("summary");
    } catch (runError) {
      setError(runError.message);
    } finally {
      setLoading(false);
    }
  };

  const selectedResult = result ? result.wl_full || result[Object.keys(result)[0]] : null;
  const info = useMemo(() => runInfo, [runInfo]);

  return (
    <div className="workbench">
      <Controls state={state} setState={setState} onRun={run} loading={loading} error={error} description={descriptions[state.scenario] || ""} />
      <div className="results-shell">
        {loading && <div className="loading-line" role="status" aria-label="Running simulation" />}
        {!result && <EmptyState />}
        {result && selectedResult && info && (
          <>
            <div className="run-head">
              <h1 className="run-title">{SCENARIO_LABELS[info.scenario] || info.scenario}</h1>
              <div className="chip-row">
                <span className="chip">{durationLabel(info.duration)}</span>
                <span className="chip">seed {info.seed}</span>
                <span className="chip">model {info.model}</span>
                <span className="chip">{info.policies.length} strategies</span>
              </div>
            </div>
            <div className="tab-list" role="tablist">
              {[["summary", "Summary"], ["plan", "Warm capacity plan"], ["compare", "Compare strategies"]].map(([value, label]) => (
                <button type="button" role="tab" aria-selected={tab === value} className={tab === value ? "tab active" : "tab"} onClick={() => setTab(value)} key={value}>{label}</button>
              ))}
            </div>
            {tab === "summary" && <SummaryTab result={result} policies={info.policies} info={info} />}
            {tab === "plan" && <CapacityPlanTab result={result} meanExecS={info.meanExec} />}
            {tab === "compare" && <CompareTab result={result} />}
          </>
        )}
      </div>
    </div>
  );
}