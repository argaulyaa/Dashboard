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

// ---- Provider activation (satu provider aktif eksklusif per domain) ----

// Provider yang sedang aktif untuk domain ini: {provider, username,
// activated_at} atau {provider: null} kalau belum ada yang diaktifkan.
export async function getActiveProvider(domain) {
  const res = await fetch(`${BASE}/${domain}/active-provider`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load active provider for ${domain}`);
  return res.json();
}

export async function activateProvider(domain, provider) {
  const res = await fetch(`${BASE}/${domain}/activate-provider`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ provider }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(typeof data.detail === "string" ? data.detail : "activate_failed");
    err.payload = data?.detail;
    throw err;
  }
  return data;
}

export async function deactivateProvider(domain) {
  const res = await fetch(`${BASE}/${domain}/deactivate-provider`, {
    method: "POST",
    headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(typeof data.detail === "string" ? data.detail : "deactivate_failed");
    err.payload = data?.detail;
    throw err;
  }
  return data;
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

// Admin-only: change a user's role ("user" | "admin").
export async function updateUserRole(username, role) {
  const res = await fetch(`${BASE}/auth/users/${encodeURIComponent(username)}/role`, {
    method: "PUT",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  if (!res.ok) throw new Error(`Failed to update role for ${username}`);
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

// ---- LIVE logs via WebSocket ----
// Helper: build WS URL for logs streaming per provider
export function getLogsLiveUrl(domain, provider, compId, tail = 100) {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const host =
    window.location.port === "5173"
      ? `${window.location.hostname}:8000`
      : window.location.host;
  const prov = provider || "oai";
  return `${proto}://${host}/ws/logs/${encodeURIComponent(domain)}/${encodeURIComponent(prov)}/${encodeURIComponent(compId)}?tail=${encodeURIComponent(tail)}`;
}

// Open live logs WebSocket; returns WebSocket instance
export function openLogsSocket(domain, provider, compId, tail = 100) {
  const url = getLogsLiveUrl(domain, provider, compId, tail);
  return new WebSocket(url);
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
      onSnapshot(normalizeSnapshot(JSON.parse(evt.data)));
    } catch (e) {
      console.error("Bad telemetry payload", e);
    }
  };
  return ws;
}

// ---- Normalisasi snapshot WS (F1 plan exclusive-core-ran) ----
// Payload v2 dari backend: {meta:{ts,active,bindings}, domains:{core:[...]}}
// Payload v1 lama (backend versi sebelum deploy): {core:[...], ran:[...]}.
// normalizeSnapshot menerima KEDUANYA dan selalu mengembalikan bentuk yang
// sama utk state App.jsx — aman urutan deploy backend/frontend.
export function normalizeSnapshot(payload) {
  if (!payload || typeof payload !== "object") {
    return { data: { core: [], ran: [], ric: [] }, meta: null };
  }
  if (payload.domains && typeof payload.domains === "object") {
    return {
      data: {
        core: payload.domains.core || [],
        ran: payload.domains.ran || [],
        ric: payload.domains.ric || [],
      },
      meta: payload.meta || null,
    };
  }
  // v1: snapshot = {domain: [components]} tanpa meta
  const { core, ran, ric } = payload;
  return {
    data: { core: core || [], ran: ran || [], ric: ric || [] },
    meta: null,
  };
}

// Label ramah utk key provider (fallback kalau daftar provider belum ke-load)
export function providerLabel(key) {
  const LABELS = { oai: "OAI", open5gs: "open5gs", magma: "Magma", srsran: "srsRAN" };
  return LABELS[key] || key || "-";
}

// ---- Forgot credentials: password reset via email OTP ----

export async function requestPasswordReset(username) {
  const res = await fetch(`${BASE}/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail?.reason || "request_failed");
  return data;
}

export async function verifyPasswordResetOtp(username, otpCode) {
  const res = await fetch(`${BASE}/auth/forgot-password/verify-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, otp_code: otpCode }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // detail bisa string (ValueError dari backend) atau array validasi pydantic
    const reason = typeof data.detail === "string" ? data.detail : "verify_failed";
    throw new Error(reason);
  }
  return data; // { ok, reset_token, username }
}

export async function confirmPasswordReset(resetToken, newPassword, confirmPassword) {
  const res = await fetch(`${BASE}/auth/forgot-password/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      reset_token: resetToken,
      new_password: newPassword,
      confirm_password: confirmPassword,
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const reason = typeof data.detail === "string" ? data.detail : "confirm_failed";
    throw new Error(reason);
  }
  return data;
}

export async function resendPasswordResetOtp(username) {
  const res = await fetch(`${BASE}/auth/forgot-password/resend-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  });
  if (!res.ok) throw new Error("resend_failed");
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

// ---- Hybrid Core↔RAN connect ----
export async function fetchRanStatus() {
  const res = await fetch(`${BASE}/ran/status`, { headers: authHeaders() });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(typeof data.detail === "string" ? data.detail : "fetchRanStatus_failed");
    err.payload = data?.detail;
    err.status = res.status;
    throw err;
  }
  return data;
}

export async function connectRan(coreProvider, ranProvider, dryRun = false) {
  const res = await fetch(`${BASE}/ran/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ core_provider: coreProvider, ran_provider: ranProvider, dry_run: dryRun }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data);
    const err = new Error(msg || "connect_failed");
    err.payload = data?.detail;
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}
