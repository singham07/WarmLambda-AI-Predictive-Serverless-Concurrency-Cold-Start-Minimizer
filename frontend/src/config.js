export const CONTACT_EMAIL = "";
// In development the API runs on port 8000. When the build is served by the API itself, calls stay on the same origin.
export const API_BASE_URL = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");