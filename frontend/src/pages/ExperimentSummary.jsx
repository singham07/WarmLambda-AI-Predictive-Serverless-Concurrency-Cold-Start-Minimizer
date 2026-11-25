import React, { useEffect, useMemo, useState } from "react";
import { getSummary } from "../lib/api";
import { friendlyName, number } from "../lib/format";

const METRICS = [
  ["cold_start_rate", "Cold start rate", true],
  ["total_cost", "Cost", false],
  ["mean_latency_s", "Mean latency", false],
  ["utilization", "Utilization", true],
];

function order(name) {
  if (name === "no_warming") return 0;
  if (name.startsWith("fixed")) return 1;
  if (name === "reactive") return 2;
  if (name.startsWith("wl")) return 3;
  return 4;
}

function display(stat, isPercent) {
  if (!stat || stat.mean === null || stat.mean === undefined) return "n/a";
  const scale = isPercent ? 100 : 1;
  return `${number(stat.mean * scale, isPercent ? 2 : 3)}${isPercent ? "%" : ""} ± ${number((stat.std || 0) * scale, isPercent ? 2 : 3)}`;
}

export default function ExperimentSummary() {
  const [summary, setSummary] = useState(null);
  const [metric, setMetric] = useState("cold_start_rate");
  const [error, setError] = useState("");
  useEffect(() => { const controller = new AbortController(); getSummary(controller.signal).then((data) => setSummary(data.summary || {})).catch((requestError) => setError(requestError.message)); return () => controller.abort(); }, []);
  const selected = METRICS.find(([key]) => key === metric) || METRICS[0];
  const scenarios = useMemo(() => Object.entries(summary || {}), [summary]);
  return <section className="document-page"><p className="eyebrow">Experiments</p><h1>Experiment results</h1><p className="lede">Means and standard deviations are read from the API summary.</p><div className="metric-switcher">{METRICS.map(([key, label]) => <button className={`button ${metric === key ? "active-control" : ""}`} type="button" key={key} onClick={() => setMetric(key)}>{label}</button>)}</div>{error && <div className="notice" role="alert">{error}</div>}{!summary && !error && <div className="card loading-block" role="status">Loading experiment summary...</div>}{summary && scenarios.map(([scenario, policies]) => { const names = Object.keys(policies).sort((a, b) => order(a) - order(b) || a.localeCompare(b, undefined, { numeric: true })); const values = names.map((name) => policies[name][selected[0]]?.mean).filter((value) => Number.isFinite(value)); const low = values.length ? Math.min(...values) : 0; const high = values.length ? Math.max(...values) : 1; return <section className="card experiment-card" key={scenario}><div className="card-head"><h2>{scenario.replaceAll("_", " ")}</h2><span className="chart-note">{names.length} strategies</span></div><div className="table-scroll"><table className="data-table"><thead><tr><th>Strategy</th>{METRICS.map(([, label]) => <th key={label}>{label}</th>)}</tr></thead><tbody>{names.map((name) => <tr key={name}><th>{friendlyName(name)}</th>{METRICS.map(([key, , isPercent]) => <td className={key === selected[0] ? `heat-${Math.min(4, Math.max(0, Math.round(((policies[name][key]?.mean || low) - low) / Math.max(high - low, 0.000001) * 4)))}` : ""} key={key}>{display(policies[name][key], isPercent)}</td>)}</tr>)}</tbody></table></div></section>; })}</section>;
}
