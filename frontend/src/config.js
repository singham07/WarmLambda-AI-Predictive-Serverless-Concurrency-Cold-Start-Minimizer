export const CONTACT_EMAIL = "";
const configuredApiUrl = import.meta.env.VITE_API_URL?.trim();
const runningInLocalDev = typeof window !== "undefined"
  && ["3000", "5173"].includes(window.location.port);
export const API_BASE_URL = configuredApiUrl
  || (runningInLocalDev ? "http://localhost:8000" : window.location.origin);
