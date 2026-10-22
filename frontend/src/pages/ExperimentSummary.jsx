import React, { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";

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
          setErrorMsg("Benchmark results are not available yet. Run the experiment scripts.");
          setSummaryData(null);
          return;
        }
        if (!res.ok) {
          setErrorMsg(`Error loading benchmark summary (status ${res.status}).`);
          return;
        }
        const data = await res.json();
        setSummaryData(data.summary);
      } catch (err) {
        setErrorMsg("Failed to connect to backend API: " + err.message);
      } finally {
        setLoading(false);
      }
    }
    fetchSummary();
  }, []);

  const formatVal = (metrics, key, isPercent = false) => {
    const item = metrics[key];
    if (!item || item.mean === null) return "Not available";
    const multiplier = isPercent ? 100 : 1;
    const mean = (item.mean * multiplier).toFixed(3);
    const std = item.std !== null ? (item.std * multiplier).toFixed(3) : "0.000";
    return `${mean} +/- ${std}${isPercent ? "%" : ""}`;
  };

  return (
    <div>
      <div className="page-heading">
        <div><p className="eyebrow">ARCHIVE / AGGREGATED RUNS</p><h1>Benchmark archive</h1><p>Summary statistics across the recorded benchmark seeds.</p></div>
        <span className="run-state"><span className="state-dot" /> read-only dataset</span>
      </div>
      {loading && <div className="empty-state">Loading benchmark results...</div>}
      {errorMsg && <div className="empty-state" style={{ color: "#9b3d32" }}>{errorMsg}</div>}
      {!loading && !errorMsg && summaryData && (
        <section className="card plan-card">
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Scenario</th><th>Policy</th><th>Cold start rate</th><th>Total cost</th><th>Utilization</th><th>Mean latency</th></tr></thead>
              <tbody>{Object.entries(summaryData).flatMap(([scenario, policies]) => Object.entries(policies).map(([policy, metrics]) => (
                <tr key={`${scenario}-${policy}`}><td><strong>{scenario}</strong></td><td>{policy}</td><td>{formatVal(metrics, "cold_start_rate", true)}</td><td>{formatVal(metrics, "total_cost")}</td><td>{formatVal(metrics, "utilization", true)}</td><td>{formatVal(metrics, "mean_latency_s")}</td></tr>
              )))}</tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
