import React, { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";

const SCENARIO_LABELS = {
  moderate: "Moderate traffic",
  high_load: "High load",
  extreme: "Extreme spikes",
  periodic: "Repeating pattern",
};

function policyLabel(name) {
  if (name === "no_warming") return "No warming";
  if (name === "reactive") return "Reactive";
  if (name === "oracle") return "Oracle (uses future data)";
  if (name.startsWith("fixed_")) return `Fixed warming, ${name.slice(6)} instances`;
  if (name.startsWith("warmlambda_h")) return `WarmLambda AI, headroom ${name.slice(12)}`;
  return name;
}

function policyOrder(name) {
  if (name === "no_warming") return 0;
  if (name.startsWith("fixed_")) return 1;
  if (name === "reactive") return 2;
  if (name.startsWith("warmlambda")) return 3;
  return 4;
}

const COLUMNS = [
  ["cold_start_rate", "Cold start rate", true, 3, false],
  ["mean_latency_s", "Mean latency (s)", false, 3, false],
  ["total_cost", "Cost (units)", false, 0, false],
  ["utilization", "Utilization", true, 1, true],
];

function cell(metrics, key, percent, digits) {
  const stat = metrics[key];
  if (!stat || stat.mean === null || stat.mean === undefined) return "n/a";
  const scale = percent ? 100 : 1;
  const suffix = percent ? "%" : "";
  const mean = (stat.mean * scale).toFixed(digits);
  const spread = stat.std !== null && stat.std !== undefined ? (stat.std * scale).toFixed(digits) : (0).toFixed(digits);
  return `${mean}${suffix} ± ${spread}`;
}

export default function ExperimentSummary() {
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState("");
  const [summaryData, setSummaryData] = useState(null);

  useEffect(() => {
    async function fetchSummary() {
      setLoading(true);
      setErrorMsg("");
      try {
        const res = await fetch(`${API_BASE_URL}/results/summary`);
        if (res.status === 404) {
          setErrorMsg("Experiment results are not available yet. Run the experiment scripts first.");
          return;
        }
        if (!res.ok) {
          setErrorMsg(`Error loading summary (status ${res.status}).`);
          return;
        }
        const data = await res.json();
        setSummaryData(data.summary);
      } catch (err) {
        setErrorMsg(`Could not reach the backend: ${err.message}`);
      } finally {
        setLoading(false);
      }
    }
    fetchSummary();
  }, []);

  return (
    <div>
      <div className="page-head">
        <h1>Experiment results</h1>
        <p>
          Mean and standard deviation across all benchmark seeds, read from results/final_metrics.csv.
          The best value in each column is shown in green.
        </p>
      </div>

      {loading && <div className="loading-line" role="status" aria-label="Loading experiment results" />}
      {errorMsg && <div className="notice-box">{errorMsg}</div>}

      {!loading && !errorMsg && summaryData && (
        <div className="scenario-stack">
          {Object.entries(summaryData).map(([scenario, policies]) => {
            const names = Object.keys(policies).sort((a, b) => policyOrder(a) - policyOrder(b) || a.localeCompare(b, undefined, { numeric: true }));
            const best = {};
            COLUMNS.forEach(([key, , , , higher]) => {
              const values = names.map((name) => policies[name][key]?.mean).filter((v) => v !== null && v !== undefined);
              best[key] = values.length && new Set(values).size > 1 ? (higher ? Math.max(...values) : Math.min(...values)) : null;
            });
            return (
              <section className="card table-card" key={scenario}>
                <div className="card-head">
                  <div>
                    <h2>{SCENARIO_LABELS[scenario] || scenario}</h2>
                    <p className="card-sub">{names.length} strategies</p>
                  </div>
                </div>
                <div className="table-scroll">
                  <table className="exp-table">
                    <thead>
                      <tr>
                        <th>Strategy</th>
                        {COLUMNS.map(([key, label]) => <th key={key} className="num">{label}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {names.map((name) => (
                        <tr key={name}>
                          <td>{policyLabel(name)}</td>
                          {COLUMNS.map(([key, , percent, digits]) => (
                            <td key={key} className={`num ${policies[name][key]?.mean === best[key] ? "best-value" : ""}`}>
                              {cell(policies[name], key, percent, digits)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}