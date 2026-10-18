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
          setErrorMsg("Experiment results are not available yet. Run the experiment scripts.");
          setSummaryData(null);
          return;
        }
        if (!res.ok) {
          setErrorMsg(`Error loading summary (Status ${res.status}).`);
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

  return (
    <div className="panel">
      <h2 className="panel-heading">Aggregated Experiment Benchmark Results</h2>
      <p className="field-description" style={{ marginBottom: "16px" }}>
        Summary statistics computed across all benchmark seeds from results/final_metrics.csv.
      </p>

      {loading && (
        <div className="empty-state">
          <span className="loading-indicator"></span> Loading experiment results...
        </div>
      )}

      {errorMsg && (
        <div className="empty-state" style={{ color: "#795548" }}>
          {errorMsg}
        </div>
      )}

      {!loading && !errorMsg && summaryData && (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Policy</th>
                <th>Cold Start Rate (mean &plusmn; std)</th>
                <th>Total Cost (mean &plusmn; std)</th>
                <th>Utilization (mean &plusmn; std)</th>
                <th>Mean Latency (mean &plusmn; std)</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(summaryData).flatMap(([scenario, policies]) =>
                Object.entries(policies).map(([policy, metrics]) => {
                  const formatVal = (mKey, isPercent = false) => {
                    const obj = metrics[mKey];
                    if (!obj || obj.mean === null) return "N/A";
                    const mult = isPercent ? 100 : 1;
                    const suffix = isPercent ? "%" : "";
                    const m = (obj.mean * mult).toFixed(3);
                    const s = obj.std !== null ? (obj.std * mult).toFixed(3) : "0.000";
                    return `${m} &plusmn; ${s}${suffix}`;
                  };

                  return (
                    <tr key={`${scenario}-${policy}`}>
                      <td style={{ fontWeight: 600 }}>{scenario}</td>
                      <td>{policy}</td>
                      <td dangerouslySetInnerHTML={{ __html: formatVal("cold_start_rate", true) }} />
                      <td dangerouslySetInnerHTML={{ __html: formatVal("total_cost", false) }} />
                      <td dangerouslySetInnerHTML={{ __html: formatVal("utilization", true) }} />
                      <td dangerouslySetInnerHTML={{ __html: formatVal("mean_latency_s", false) }} />
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
