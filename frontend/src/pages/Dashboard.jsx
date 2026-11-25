import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Bar, BarChart, Brush, CartesianGrid, Cell, ComposedChart, Line, ReferenceArea,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from "recharts";
import { getPolicies, getScenarios, postCompare, postRun } from "../lib/api";
import { clearHistory, loadHistory, saveHistory } from "../lib/history";
import { durationLabel, friendlyName, number, percent, seconds, time } from "../lib/format";
import { burstIndexes, littleLaw, normalizePlan } from "../lib/planMath";
import { defaults, readUrlState, writeUrlState } from "../lib/urlState";

const COLORS = {
  no_warming: "#8a97a3", fixed: "#4cb5d6", reactive: "#5cbf85", wl_full: "#f0a23b",
  wl_forecast_only: "#d9c35c", wl_correction_only: "#e0805a", oracle: "#e6ebf0",
};
const TAGS = {
  no_warming: "baseline", fixed: "baseline", reactive: "baseline", wl_full: "proposed",
  wl_forecast_only: "ablation", wl_correction_only: "ablation", oracle: "upper bound",
};
const LABELS = { scheduled_bursts: "Scheduled bursts", daily_cycle: "Daily cycle", moderate: "Moderate traffic", high_load: "High load", extreme: "Extreme spikes", periodic: "Repeating pattern" };
const TAB_NAMES = ["Timeline", "Summary", "Compare", "Pareto", "Capacity plan"];

function strategyColor(name) { return COLORS[name] || "#8a97a3"; }
function strategyLabel(name) { return friendlyName(name); }

function requestPayload(state, policyList, policy) {
  return {
    scenario: state.scenario, policies: policyList, policy, duration_s: state.duration,
    seed: state.seed, init_time_s: state.initTime, mean_exec_s: state.meanExec,
    idle_timeout_s: state.idleTimeout, headroom: state.headroom,
    warm_budget: state.warmBudget === "" ? null : Number(state.warmBudget),
    fixed_n: state.fixedN, model: state.model,
  };
}

function TooltipBox({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return <div className="chart-tooltip"><strong>{time(label)}</strong>{payload.map((entry) => (
    <div key={entry.dataKey}><span>{entry.name}</span><b>{number(entry.value, 2)}</b></div>
  ))}</div>;
}

function MetricTile({ title, value, unit, compare, tone = "" }) {
  return <article className={`metric-tile ${tone}`}><p>{title}</p><strong>{value}<small>{unit}</small></strong><span>{compare}</span></article>;
}

function ErrorBoundary({ children }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <div className="notice" role="alert">This view could not be rendered. Select another tab and try again.</div>;
  try { return children; } catch { setFailed(true); return null; }
}

function Controls({ state, setState, scenarios, policies, onRun, onCancel, running, error, onPareto }) {
  const update = (key, value) => setState((current) => ({ ...current, [key]: value }));
  const available = policies.length ? policies : ["no_warming", "fixed", "reactive", "wl_full", "wl_forecast_only", "wl_correction_only", "oracle"];
  return <aside className="controls" aria-label="Simulation settings">
    <div className="controls-section">
      <p className="eyebrow">Traffic</p>
      <label className="field-label" htmlFor="traffic">Scenario</label>
      <select id="traffic" value={state.scenario} onChange={(event) => update("scenario", event.target.value)}>
        {scenarios.map((scenario) => <option value={scenario.name} key={scenario.name}>{LABELS[scenario.name] || scenario.name}</option>)}
      </select>
      <p className="field-help">{scenarios.find((item) => item.name === state.scenario)?.description || "Choose a scenario from the API."}</p>
      <label className="field-label" htmlFor="duration">Duration</label>
      <select id="duration" value={state.duration} onChange={(event) => update("duration", Number(event.target.value))}>
        <option value="600">10 minutes</option><option value="1800">30 minutes</option><option value="3600">1 hour</option>
      </select>
    </div>
    <div className="controls-section">
      <p className="eyebrow">Strategies</p>
      <div className="strategy-list">{available.map((name) => <label className="strategy-row" key={name}>
        <input type="checkbox" checked={state.policies.includes(name)} onChange={() => update("policies", state.policies.includes(name) ? state.policies.filter((item) => item !== name) : [...state.policies, name])} />
        <i className="swatch" style={{ background: strategyColor(name) }} /><span>{strategyLabel(name)}</span><small>{TAGS[name] || "strategy"}</small>
      </label>)}</div>
    </div>
    <div className="controls-section">
      <details><summary>Advanced settings</summary><div className="advanced-grid">
        <label>Seed<input type="number" value={state.seed} onChange={(event) => update("seed", Number(event.target.value))} /></label>
        <label>Cold start (s)<input type="number" step="0.1" value={state.initTime} onChange={(event) => update("initTime", Number(event.target.value))} /></label>
        <label>Run time (s)<input type="number" step="0.1" value={state.meanExec} onChange={(event) => update("meanExec", Number(event.target.value))} /></label>
        <label>Idle timeout (s)<input type="number" step="0.1" min="0.1" value={state.idleTimeout} onChange={(event) => update("idleTimeout", Number(event.target.value))} /></label>
        <label>Headroom<input type="number" step="0.1" value={state.headroom} onChange={(event) => update("headroom", Number(event.target.value))} /></label>
        <label>Warm budget<input type="number" min="0" value={state.warmBudget} onChange={(event) => update("warmBudget", event.target.value)} placeholder="None" /></label>
        <label>Fixed instances<input type="number" min="0" value={state.fixedN} onChange={(event) => update("fixedN", Number(event.target.value))} /></label>
        <label className="wide">Forecast model<select value={state.model} onChange={(event) => update("model", event.target.value)}><option value="ewma">EWMA</option><option value="seasonal">Seasonal</option><option value="ridge_q90">Ridge q90</option><option value="ridge">Ridge</option><option value="xgboost">XGBoost</option><option value="gru">GRU</option></select></label>
      </div></details>
    </div>
    {error && <div className="error-box" role="alert">{error}</div>}
    <div className="run-bar"><button className="button primary-button" type="button" onClick={onRun} disabled={running || !state.policies.length}>{running ? "Running..." : "Run configuration"}</button>{running && <button className="button" type="button" onClick={onCancel}>Cancel</button>}<button className="button" type="button" onClick={onPareto} disabled={running}>Run Pareto sweep</button></div>
  </aside>;
}

function ChartCard({ title, children }) {
  return <section className="card chart-card"><div className="card-head"><h2>{title}</h2><span className="chart-note">Click a point to inspect</span></div>{children}</section>;
}

function Timeline({ plan, onPin }) {
  const bursts = burstIndexes(plan);
  const data = plan.map((row, index) => ({ ...row, time: row.t_start, predicted: row.predicted_requests, observed: row.observed_requests, recommended: row.recommended_warm_instances, ready: row.ready_instances, busy: row.busy ?? 0, cold: row.cold_starts, avg: row.avg_latency_s, p95: row.p95_latency_s, burst: bursts.has(index) }));
  const areas = data.filter((row) => row.shortfall_instances > 0 || row.burst).map((row) => ({ ...row, kind: row.shortfall_instances > 0 ? "short" : "burst" }));
  const common = { data, syncId: "timeline", margin: { top: 8, right: 12, left: 0, bottom: 4 } };
  const axis = <><CartesianGrid stroke="#26323d" vertical={false} /><XAxis dataKey="time" tickFormatter={time} stroke="#6a7885" /><YAxis stroke="#6a7885" width={42} /></>;
  return <div className="timeline">
    <ChartCard title="Observed and predicted requests"><ResponsiveContainer width="100%" height={210}><ComposedChart {...common}>{axis}<Tooltip content={<TooltipBox />} /><Line type="monotone" dataKey="observed" name="Observed req" stroke="#4cb5d6" dot={false} onClick={(point) => onPin(point?.payload)} /><Line type="monotone" dataKey="predicted" name="Predicted req" stroke="#f0a23b" strokeDasharray="5 4" dot={false} /></ComposedChart></ResponsiveContainer></ChartCard>
    <ChartCard title="Warm instances"><ResponsiveContainer width="100%" height={210}><ComposedChart {...common}>{axis}{areas.map((row) => <ReferenceArea key={`${row.time}-${row.kind}`} x1={row.t_start} x2={row.t_end} fill={row.kind === "short" ? "#e5645f" : "#f0a23b"} fillOpacity={0.12} />)}<Tooltip content={<TooltipBox />} /><Line type="stepAfter" dataKey="recommended" name="Recommended" stroke="#f0a23b" dot={false} onClick={(point) => onPin(point?.payload)} /><Line dataKey="ready" name="Ready" stroke="#4cb5d6" dot={false} /><Line dataKey="busy" name="Busy" stroke="#8a97a3" strokeDasharray="4 4" dot={false} /></ComposedChart></ResponsiveContainer></ChartCard>
    <ChartCard title="Cold starts per interval"><ResponsiveContainer width="100%" height={190}><BarChart {...common}>{axis}<Tooltip content={<TooltipBox />} /><Bar dataKey="cold" name="Cold starts" fill="#e0805a" onClick={(point) => onPin(point?.payload)} /></BarChart></ResponsiveContainer></ChartCard>
    <ChartCard title="Average and p95 latency"><ResponsiveContainer width="100%" height={190}><ComposedChart {...common}>{axis}<Tooltip content={<TooltipBox />} /><Line dataKey="avg" name="Average latency s" stroke="#4cb5d6" dot={false} /><Line dataKey="p95" name="p95 latency s" stroke="#f0a23b" dot={false} onClick={(point) => onPin(point?.payload)} /><Brush dataKey="time" height={18} stroke="#f0a23b" tickFormatter={time} /></ComposedChart></ResponsiveContainer></ChartCard>
  </div>;
}

function Inspector({ row, state, onClose, onMove }) {
  if (!row) return null;
  const math = littleLaw(row, state.meanExec, state.headroom);
  const fields = ["t_start", "t_end", "observed_requests", "predicted_requests", "recommended_warm_instances", "ready_instances", "cold_starts", "avg_latency_s", "p95_latency_s", "dropped_requests", "estimated_cost_units", "shortfall_instances"];
  return <aside className="inspector" aria-label="Interval inspector"><div className="inspector-head"><h2>Interval {time(row.t_start)}</h2><button className="button" type="button" onClick={onClose}>Close</button></div><dl>{fields.map((field) => <div key={field}><dt>{field.replaceAll("_", " ")}</dt><dd>{number(row[field], field.includes("latency") ? 3 : 2)}</dd></div>)}</dl><section className="worked-example"><h3>How the number was reached</h3><p>Forecast rate = {number(math.rate, 3)} req/s.</p><p>Little's Law N = ceil({number(math.rate, 3)} x {number(state.meanExec, 3)} s x (1 + {number(state.headroom, 2)})) = <b>{math.calculated} instances</b>.</p><p>Recommended warm = <b>{row.recommended_warm_instances} instances</b>. {math.difference === 0 ? "The forecast calculation matches." : `Reactive correction or budget changed it by ${math.difference} instances.`}</p></section><div className="inspector-nav"><button className="button" type="button" onClick={() => onMove(-1)}>Previous</button><button className="button" type="button" onClick={() => onMove(1)}>Next</button></div></aside>;
}

function Summary({ results, state: _state, selectedPolicy }) {
  const selected = results[selectedPolicy] || Object.values(results)[0];
  const baseline = results.no_warming?.metrics;
  const metrics = selected?.metrics || {};
  const comparison = (value, key, unit = "") => {
    if (!baseline || value === null || baseline[key] === null || value === undefined || baseline[key] === undefined) return { text: "Add No warming to compare", tone: "" };
    const delta = Number(value) - Number(baseline[key]);
    if (Math.abs(delta) < 0.000001) return { text: "Same as No warming", tone: "" };
    return { text: `${number(Math.abs(delta) * (key.includes("rate") ? 100 : 1), key.includes("rate") ? 2 : 2)}${unit} ${delta < 0 ? "lower" : "higher"} than No warming`, tone: delta < 0 ? "good" : "bad" };
  };
  const short = (selected?.capacity_plan || []).filter((row) => row.shortfall_instances > 0).length;
  return <div className="tab-content"><div className="metric-grid">
    <MetricTile title="Cold start rate" value={percent(metrics.cold_start_rate)} unit="" compare={comparison(metrics.cold_start_rate, "cold_start_rate", " points").text} tone={comparison(metrics.cold_start_rate, "cold_start_rate").tone} />
    <MetricTile title="p95 latency" value={seconds(metrics.p95_latency_s)} unit="" compare={comparison(metrics.p95_latency_s, "p95_latency_s").text} tone={comparison(metrics.p95_latency_s, "p95_latency_s").tone} />
    <MetricTile title="Estimated cost" value={number(metrics.total_cost, 1)} unit=" units" compare={comparison(metrics.total_cost, "total_cost", " units").text} tone={comparison(metrics.total_cost, "total_cost").tone} />
    <MetricTile title="Peak recommended warm" value={number(selected?.summary?.peak_recommended_warm, 0)} unit=" instances" compare={`Average ${number(selected?.summary?.average_recommended_warm, 1)} instances`} tone="key" />
  </div><section className="card"><h2>Findings</h2><ul className="plain-list"><li>{strategyLabel(selectedPolicy)} served {number(metrics.cold_start_count, 0)} cold starts.</li><li>{short} intervals had a capacity shortfall.</li><li>Cost was {number(metrics.total_cost, 1)} units under the selected configuration.</li>{baseline && <li>{Number(metrics.cold_start_rate) < Number(baseline.cold_start_rate) ? "Cold start rate was lower than No warming." : "Cold start rate was not lower than No warming."}</li>}</ul></section></div>;
}

function Compare({ results }) {
  const rows = Object.entries(results).map(([name, value]) => ({ name, ...value.metrics }));
  const fields = [["cold_start_rate", "Cold start rate"], ["p95_latency_s", "p95 latency"], ["total_cost", "Cost"], ["utilization", "Utilization"], ["dropped_rate", "Dropped rate"]];
  return <div className="tab-content"><section className="card table-wrap"><table className="data-table"><thead><tr><th>Strategy</th>{fields.map(([, label]) => <th key={label}>{label}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={row.name}><th>{strategyLabel(row.name)}</th>{fields.map(([field]) => <td key={field}>{field.includes("rate") || field === "utilization" ? percent(row[field]) : number(row[field], 3)}</td>)}</tr>)}</tbody></table></section><section className="card chart-card"><h2>Cold starts versus cost</h2><ResponsiveContainer width="100%" height={300}><ScatterChart><CartesianGrid stroke="#26323d" /><XAxis dataKey="total_cost" name="Cost" stroke="#6a7885" /><YAxis dataKey="cold_start_count" name="Cold starts" stroke="#6a7885" /><Tooltip cursor={{ strokeDasharray: "3 3" }} content={<TooltipBox />} /><Scatter data={rows} name="Strategies">{rows.map((row) => <Cell key={row.name} fill={strategyColor(row.name)} />)}</Scatter></ScatterChart></ResponsiveContainer></section></div>;
}

function CapacityPlan({ results, selectedPolicy, state, onPin }) {
  const [onlyShort, setOnlyShort] = useState(false);
  const [onlyCold, setOnlyCold] = useState(false);
  const [page, setPage] = useState(0);
  const rows = (results[selectedPolicy]?.capacity_plan || []).map((row) => normalizePlan(row, state.meanExec));
  const filtered = rows.filter((row) => (!onlyShort || row.shortfall_instances > 0) && (!onlyCold || row.cold_starts > 0));
  const visible = filtered.slice(page * 40, page * 40 + 40);
  const download = () => {
    const keys = ["t_start", "t_end", "observed_requests", "predicted_requests", "recommended_warm_instances", "ready_instances", "cold_starts", "avg_latency_s", "p95_latency_s", "estimated_cost_units", "shortfall_instances"];
    const csv = [keys.join(","), ...filtered.map((row) => keys.map((key) => row[key] ?? "").join(","))].join("\n");
    const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); link.download = `capacity_plan_${selectedPolicy}.csv`; link.click(); URL.revokeObjectURL(link.href);
  };
  return <section className="card plan-card"><div className="card-head"><h2>Capacity plan</h2><div className="toolbar"><label><input type="checkbox" checked={onlyShort} onChange={(event) => { setOnlyShort(event.target.checked); setPage(0); }} /> Short only</label><label><input type="checkbox" checked={onlyCold} onChange={(event) => { setOnlyCold(event.target.checked); setPage(0); }} /> Cold starts</label><button className="button" type="button" onClick={download}>Download CSV</button><button className="button" type="button" onClick={() => window.print()}>Print report</button></div></div><div className="table-scroll"><table className="data-table plan-table"><thead><tr><th>Interval</th><th>Requests</th><th>Predicted</th><th>Recommended</th><th>Ready</th><th>Cold starts</th><th>Average latency</th><th>p95 latency</th><th>Cost</th><th>Status</th></tr></thead><tbody>{visible.map((row) => <tr tabIndex="0" key={row.t_start} onClick={() => onPin(row)} onKeyDown={(event) => event.key === "Enter" && onPin(row)}><td>{time(row.t_start)} to {time(row.t_end)}</td><td>{number(row.observed_requests, 0)}</td><td>{number(row.predicted_requests, 0)}</td><td>{number(row.recommended_warm_instances, 0)}</td><td>{number(row.ready_instances, 0)}</td><td>{number(row.cold_starts, 0)}</td><td>{seconds(row.avg_latency_s)}</td><td>{seconds(row.p95_latency_s)}</td><td>{number(row.estimated_cost_units, 1)} units</td><td className={row.status === "Short" ? "bad-text" : row.status === "OK" ? "good-text" : ""}>{row.status}</td></tr>)}</tbody></table></div><div className="pager"><span>{filtered.length} intervals</span><button className="button" type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><button className="button" type="button" disabled={(page + 1) * 40 >= filtered.length} onClick={() => setPage((value) => value + 1)}>Next</button></div></section>;
}

function Pareto({ state }) {
  const [rows, setRows] = useState([]);
  const [running, setRunning] = useState(false);
  const controller = useRef(null);
  const run = async () => {
    controller.current = new AbortController(); setRunning(true); setRows([]);
    const settings = [[0, "wl_full"], [0.25, "wl_full"], [0.5, "wl_full"], [1, "wl_full"], [2, "wl_full"], [0, "fixed"], [1, "fixed"], [2, "fixed"], [5, "fixed"], [10, "fixed"], [20, "fixed"]];
    for (let index = 0; index < settings.length; index += 1) {
      const [setting, policy] = settings[index];
      try {
        const next = { ...state, headroom: policy === "wl_full" ? setting : state.headroom, fixedN: policy === "fixed" ? setting : state.fixedN };
        const data = await postRun(requestPayload(next, [], policy), controller.current.signal);
        setRows((current) => [...current, { policy, setting, cost: data.metrics.total_cost, cold: data.metrics.cold_start_count }]);
      } catch (error) { if (error.message !== "Request cancelled.") setRows((current) => [...current, { policy, setting, error: error.message }]); break; }
    }
    setRunning(false);
  };
  return <section className="tab-content"><div className="card"><div className="card-head"><div><h2>Cost versus cold starts</h2><p className="card-sub">{running ? `${rows.length} of 11 runs` : `${rows.length} runs completed`}</p></div><div><button className="button primary-button compact" type="button" onClick={run} disabled={running}>{running ? "Running..." : "Start sweep"}</button>{running && <button className="button" type="button" onClick={() => controller.current?.abort()}>Cancel</button>}</div></div><ResponsiveContainer width="100%" height={360}><ScatterChart><CartesianGrid stroke="#26323d" /><XAxis dataKey="cost" name="Cost" stroke="#6a7885" /><YAxis dataKey="cold" name="Cold starts" stroke="#6a7885" /><Tooltip content={<TooltipBox />} /><Scatter data={rows.filter((row) => !row.error)} name="Sweep">{rows.map((row) => <Cell key={`${row.policy}-${row.setting}`} fill={strategyColor(row.policy)} />)}</Scatter></ScatterChart></ResponsiveContainer></div></section>;
}

export default function Dashboard() {
  const [state, setState] = useState(() => ({ ...defaults, ...readUrlState() }));
  const [scenarios, setScenarios] = useState([]);
  const [policies, setPolicies] = useState([]);
  const [results, setResults] = useState(null);
  const [selectedPolicy, setSelectedPolicy] = useState("wl_full");
  const [tab, setTab] = useState("Timeline");
  const [pinned, setPinned] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState(() => loadHistory());
  const controller = useRef(null);
  useEffect(() => { const controller = new AbortController(); Promise.all([getScenarios(controller.signal), getPolicies(controller.signal)]).then(([scenarioData, policyData]) => { setScenarios(scenarioData.scenarios || []); setPolicies((policyData.policies || []).map((item) => item.name)); setState((current) => ({ ...current, scenario: scenarioData.scenarios?.some((item) => item.name === current.scenario) ? current.scenario : (scenarioData.scenarios?.some((item) => item.name === "scheduled_bursts") ? "scheduled_bursts" : "extreme") })); }).catch((requestError) => setError(requestError.message)); return () => controller.abort(); }, []);
  useEffect(() => { writeUrlState(state); }, [state]);
  const run = async () => { if (!state.policies.length) { setError("Select at least one strategy."); return; } controller.current = new AbortController(); setRunning(true); setError(""); try { const data = await postCompare(requestPayload(state, state.policies), controller.current.signal); setResults(data.results); setSelectedPolicy(data.results.wl_full ? "wl_full" : state.policies[0]); const item = { id: Date.now(), timestamp: new Date().toISOString(), state, metrics: Object.fromEntries(Object.entries(data.results).map(([key, value]) => [key, value.metrics])) }; setHistory(saveHistory(item)); } catch (requestError) { if (requestError.message !== "Request cancelled.") setError(requestError.message); } finally { setRunning(false); } };
  useEffect(() => { const handler = (event) => { if (event.key === "r" && !["INPUT", "SELECT"].includes(document.activeElement?.tagName)) run(); if (event.key >= "1" && event.key <= "5") setTab(TAB_NAMES[Number(event.key) - 1]); if (event.key === "Escape") setPinned(null); }; window.addEventListener("keydown", handler); return () => window.removeEventListener("keydown", handler); });
  const selected = results?.[selectedPolicy] || (results ? Object.values(results)[0] : null);
  const plan = useMemo(() => (selected?.capacity_plan || []).map((row) => normalizePlan(row, state.meanExec)), [selected, state.meanExec]);
  const movePinned = (direction) => { const index = plan.findIndex((row) => row.t_start === pinned?.t_start); setPinned(plan[Math.max(0, Math.min(plan.length - 1, index + direction))]); };
  return <><section className="workspace-heading"><div><p className="eyebrow">Analysis workbench</p><h1>Serverless concurrency simulator</h1><p>Replay the same traffic against competing warm-capacity strategies.</p></div><span className="workspace-status"><i /> {running ? "RUNNING" : results ? "RESULTS READY" : "READY FOR INPUT"}</span></section><div className="workbench"><Controls state={state} setState={setState} scenarios={scenarios} policies={policies} onRun={run} onCancel={() => controller.current?.abort()} running={running} error={error} onPareto={() => setTab("Pareto")} /><main className="results-shell">{!results ? <section className="empty-state card"><h2>Run a configuration to inspect the timeline</h2><p>Every value in the analysis is returned by the simulation API or derived from its response.</p></section> : <><div className="run-head"><div><h2 className="run-title">{LABELS[state.scenario] || state.scenario}</h2><div className="chip-row"><span className="chip">{durationLabel(state.duration)}</span><span className="chip">seed {state.seed}</span><span className="chip">idle timeout {state.idleTimeout} s</span><span className="chip">{state.policies.length} strategies</span></div></div><label className="strategy-switcher">Plot<select value={selectedPolicy} onChange={(event) => setSelectedPolicy(event.target.value)}>{Object.keys(results).map((name) => <option value={name} key={name}>{strategyLabel(name)}</option>)}</select></label></div><div className="tab-list" role="tablist">{TAB_NAMES.map((name) => <button className={`tab ${tab === name ? "active" : ""}`} role="tab" aria-selected={tab === name} key={name} onClick={() => setTab(name)}>{name}</button>)}</div><div aria-live="polite" className="sr-only">{running ? "Simulation running" : ""}</div><ErrorBoundary>{tab === "Timeline" && <Timeline plan={plan} onPin={setPinned} />}{tab === "Summary" && <Summary results={results} state={state} selectedPolicy={selectedPolicy} />}{tab === "Compare" && <Compare results={results} />}{tab === "Pareto" && <Pareto state={state} />}{tab === "Capacity plan" && <CapacityPlan results={results} selectedPolicy={selectedPolicy} state={state} onPin={setPinned} />}</ErrorBoundary></>}</main></div>{history.length > 0 && <section className="history-strip"><span>History: {history.length} saved runs</span><button className="button" type="button" onClick={() => { clearHistory(); setHistory([]); }}>Clear history</button></section>}{pinned && <Inspector row={pinned} state={state} onClose={() => setPinned(null)} onMove={movePinned} />}</>;
}
