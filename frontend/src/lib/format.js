export function number(value, digits = 2) {
  return value === null || value === undefined || !Number.isFinite(Number(value)) ? "n/a" : Number(value).toFixed(digits);
}

export function percent(value, digits = 2) {
  return value === null || value === undefined || !Number.isFinite(Number(value)) ? "n/a" : `${(Number(value) * 100).toFixed(digits)}%`;
}

export function seconds(value, digits = 3) {
  const text = number(value, digits);
  return text === "n/a" ? text : `${text} s`;
}

export function time(value) {
  const total = Math.max(0, Math.round(Number(value) || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function durationLabel(value) {
  return Number(value) >= 3600 ? `${Number(value) / 3600} hour` : `${Number(value) / 60} minutes`;
}

export function friendlyName(value) {
  const names = {
    no_warming: "No warming",
    fixed: "Fixed warming",
    reactive: "Reactive",
    wl_full: "WarmLambda full",
    wl_forecast_only: "Forecast only",
    wl_correction_only: "Correction only",
    oracle: "Oracle",
  };
  return names[value] || value.replaceAll("_", " ");
}
