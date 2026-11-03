// Base path deployment. Default = perilaku lama ("/api", "/ws").
// Subpath deploy: VITE_API_BASE=/oran/api VITE_WS_BASE=/oran/ws vite build --base=/oran/
export const API_BASE = (import.meta.env.VITE_API_BASE || "/api").replace(/\/+$/, "");
export const WS_BASE = (import.meta.env.VITE_WS_BASE || "/ws").replace(/\/+$/, "");
