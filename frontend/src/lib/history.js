const KEY = "warmlambda.run.history";
let memory = [];

export function loadHistory() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(KEY) || "[]");
    memory = Array.isArray(parsed) ? parsed.slice(0, 10) : [];
  } catch {
    memory = [];
  }
  return memory;
}

export function saveHistory(item) {
  memory = [item, ...memory.filter((entry) => entry.id !== item.id)].slice(0, 10);
  try { window.localStorage.setItem(KEY, JSON.stringify(memory)); } catch { /* memory fallback */ }
  return memory;
}

export function clearHistory() {
  memory = [];
  try { window.localStorage.removeItem(KEY); } catch { /* memory fallback */ }
}
