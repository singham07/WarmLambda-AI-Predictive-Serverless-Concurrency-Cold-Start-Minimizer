export function normalizePlan(item, meanExec = 0.2) {
  const start = item.t_start ?? item.time_start_s ?? 0;
  const end = item.t_end ?? item.time_end_s ?? start;
  const duration = Math.max(end - start, 0.000001);
  const recommended = item.recommended_warm_instances ?? item.recommended_warm ?? 0;
  const ready = item.ready_instances ?? item.ready ?? 0;
  const shortfall = item.shortfall_instances ?? item.shortfall ?? 0;
  const needed = Math.ceil((Number(item.observed_requests || 0) / duration) * meanExec);
  return {
    ...item,
    t_start: start,
    t_end: end,
    recommended_warm_instances: recommended,
    ready_instances: ready,
    shortfall_instances: shortfall,
    needed,
    status: shortfall > 0 ? "Short" : ready > needed * 1.5 ? "Over-provisioned" : "OK",
  };
}

export function burstIndexes(rows) {
  const rates = rows.map((row) => row.observed_requests / Math.max(row.t_end - row.t_start, 0.000001));
  const sorted = [...rates].sort((a, b) => a - b);
  const median = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
  return new Set(rates.map((rate, index) => rate > median * 3 ? index : -1).filter((index) => index >= 0));
}

export function littleLaw(row, meanExec, headroom) {
  const rate = Number(row.predicted_requests ?? 0) / Math.max(row.t_end - row.t_start, 0.000001);
  const calculated = Math.ceil(rate * meanExec * (1 + headroom));
  return { rate, calculated, difference: Number(row.recommended_warm_instances || 0) - calculated };
}
