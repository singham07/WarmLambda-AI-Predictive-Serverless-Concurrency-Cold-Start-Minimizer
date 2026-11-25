import { API_BASE_URL } from "../config";

const DEFAULT_TIMEOUT = 30000;

export async function apiFetch(path, options = {}) {
  const controller = options.signal ? null : new AbortController();
  const signal = options.signal || controller.signal;
  const timeout = window.setTimeout(() => controller?.abort(), options.timeout || DEFAULT_TIMEOUT);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, { ...options, signal });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = Array.isArray(body.detail) ? body.detail.map((item) => item.msg).join(", ") : body.detail;
      throw new Error(detail || `Request failed with status ${response.status}.`);
    }
    return body;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("Request cancelled.");
    throw new Error(error.message || "The API request could not be completed.");
  } finally {
    window.clearTimeout(timeout);
  }
}

export const getScenarios = (signal) => apiFetch("/scenarios", { signal });
export const getPolicies = (signal) => apiFetch("/policies", { signal });
export const getSummary = (signal) => apiFetch("/results/summary", { signal });

export function postCompare(payload, signal) {
  return apiFetch("/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
    timeout: 120000,
  });
}

export function postRun(payload, signal) {
  return apiFetch("/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
    timeout: 120000,
  });
}
