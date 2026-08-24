import { getToken } from "./auth.js";

const BASE = "/api";

// Helper: inject Authorization header ke semua request yang butuh auth.
// Token diambil dari localStorage lewat auth.js (satu sumber kebenaran).
function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchProviders(domain) {
  const res = await fetch(`${BASE}/${domain}/providers`);
  if (!res.ok) throw new Error(`Failed to load providers for ${domain}`);
  return res.json();
}

export async function fetchComponents(domain, provider) {
  const qs = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  const res = await fetch(`${BASE}/${domain}/components${qs}`);
  if (!res.ok) throw new Error(`Failed to load ${domain}`);
  return res.json();
}

export async function restartComponent(domain, id) {
  const res = await fetch(`${BASE}/${domain}/components/${id}/restart`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  if (!res.ok) throw new Error(`Failed to restart ${id}`);
  return res.json();
}

export async function fetchReservation(domain, id) {
  const res = await fetch(`${BASE}/${domain}/components/${id}/reservation`);
  if (!res.ok) throw new Error(`Failed to load reservation for ${id}`);
  return res.json();
}

export async function createReservation(domain, id, user, startAt, endAt, note = "") {
  const res = await fetch(`${BASE}/${domain}/components/${id}/reservation`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ user, start_at: startAt, end_at: endAt, note }),
  });
  const data = await res.json();
  if (!res.ok) {
    const err = new Error(data?.detail?.reason || "reserve_failed");
    err.payload = data?.detail;
    throw err;
  }
  return data;
}

export async function cancelReservation(domain, id, user, reservationId) {
  const res = await fetch(
    `${BASE}/${domain}/components/${id}/reservation/${reservationId}?user=${encodeURIComponent(user)}`,
    {
      method: "DELETE",
      headers: { ...authHeaders() },
    }
  );
  const data = await res.json();
  if (!res.ok) {
    const err = new Error(data?.detail?.reason || "cancel_failed");
    err.payload = data?.detail;
    throw err;
  }
  return data;
}

export async function fetchMyReservations(user) {
  const res = await fetch(`${BASE}/reservations/my?user=${encodeURIComponent(user)}`, {
    headers: { ...authHeaders() },
  });
  if (!res.ok) throw new Error("Failed to load my reservations");
  return res.json();
}

export async function fetchAllReservations() {
  const res = await fetch(`${BASE}/reservations/all`, {
    headers: { ...authHeaders() },
  });
  if (!res.ok) throw new Error("Failed to load all reservations");
  return res.json();
}

export async function fetchUsers() {
  const res = await fetch(`${BASE}/auth/users`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

export async function deleteUser(username) {
  const res = await fetch(`${BASE}/auth/users/${encodeURIComponent(username)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to delete user ${username}`);
  return res.json();
}

export async function fetchAuditLogs() {
  const res = await fetch(`${BASE}/audit-logs`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch audit logs");
  return res.json();
}

export async function fetchComponentLogs(domain, compId, provider = null, tail = 100) {
  const qs = provider ? `?provider=${encodeURIComponent(provider)}&tail=${tail}` : `?tail=${tail}`;
  const res = await fetch(`${BASE}/${domain}/components/${compId}/logs${qs}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load logs for ${compId}`);
  return res.json();
}

export function openTelemetrySocket(onSnapshot) {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const token = getToken();
  const qs = token ? `?token=${encodeURIComponent(token)}` : "";
  // Di dev mode (port 5173), konek langsung ke port 8000 backend
  // untuk menghindari bug proxy WebSocket Node.js (Vite ECONNABORTED error)
  const host =
    window.location.port === "5173"
      ? `${window.location.hostname}:8000`
      : window.location.host;
  const ws = new WebSocket(`${proto}://${host}/ws/telemetry${qs}`);
  ws.onmessage = (evt) => {
    try {
      onSnapshot(JSON.parse(evt.data));
    } catch (e) {
      console.error("Bad telemetry payload", e);
    }
  };
  return ws;
}

export async function requestPasswordReset(username) {
  const res = await fetch(`${BASE}/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  });
  if (!res.ok) throw new Error("Request failed");
  return res.json();
}

export async function verifyEmail(username, otpCode) {
  const res = await fetch(`${BASE}/auth/verify-email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, otp_code: otpCode }),
  });
  const data = await res.json();
  if (!res.ok) {
    const err = new Error(data?.detail || "verify_failed");
    err.status = res.status;
    throw err;
  }
  return data;
}

export async function resendOtp(username) {
  const res = await fetch(`${BASE}/auth/resend-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  });
  if (!res.ok) throw new Error("resend_failed");
  return res.json();
}
