const defaults = {
  scenario: "scheduled_bursts", duration: 3600, policies: ["no_warming", "fixed", "reactive", "wl_full"],
  seed: 42, initTime: 1, meanExec: 0.2, idleTimeout: 10, headroom: 0.5,
  warmBudget: "", fixedN: 5, model: "ewma",
};

function validNumber(value, fallback, min = -Infinity) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= min ? parsed : fallback;
}

export function readUrlState() {
  const params = new URLSearchParams(window.location.search);
  return {
    ...defaults,
    scenario: params.get("scenario") || defaults.scenario,
    duration: validNumber(params.get("duration"), defaults.duration, 1),
    policies: (params.get("policies") || defaults.policies.join(",")).split(",").filter(Boolean),
    seed: validNumber(params.get("seed"), defaults.seed, 0),
    initTime: validNumber(params.get("initTime"), defaults.initTime, 0.001),
    meanExec: validNumber(params.get("meanExec"), defaults.meanExec, 0.001),
    idleTimeout: validNumber(params.get("idleTimeout"), defaults.idleTimeout, 0.1),
    headroom: validNumber(params.get("headroom"), defaults.headroom, 0),
    warmBudget: params.get("warmBudget") || "",
    fixedN: validNumber(params.get("fixedN"), defaults.fixedN, 0),
    model: params.get("model") || defaults.model,
  };
}

export function writeUrlState(state) {
  const params = new URLSearchParams();
  Object.entries(state).forEach(([key, value]) => {
    if (Array.isArray(value)) params.set(key, value.join(","));
    else if (value !== "" && value !== null && value !== undefined) params.set(key, String(value));
  });
  window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
}

export { defaults };
