export const CONTACT_EMAIL = "";
const runningFromApi = typeof window !== "undefined" && window.location.port === "8000";
export const API_BASE_URL = runningFromApi
  ? window.location.origin
  : import.meta.env.VITE_API_URL || "http://localhost:8000";
