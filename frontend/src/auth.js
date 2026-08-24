import { setUser, setRole, clearUser } from "./user.js";

const KEY = "oran-dashboard:token";

export function getToken() {
  return window.localStorage.getItem(KEY) || "";
}
export function setToken(token) {
  window.localStorage.setItem(KEY, token);
}
export function clearToken() {
  window.localStorage.removeItem(KEY);
}
export function isAuthenticated() {
  return !!getToken();
}
export async function login(username, password) {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detailMsg = typeof body.detail === "string" ? body.detail : (body.detail?.[0]?.msg || "login_failed");
    const err = new Error(detailMsg);
    err.status = res.status;
    throw err;
  }
  const data = await res.json();
  setToken(data.token);
  setUser(data.user || username);
  setRole(data.role || "engineer");
  return data;
}

export async function register(fullName, username, email, password, role = "engineer") {
  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ full_name: fullName, username, email, password, role }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detailMsg = typeof body.detail === "string" ? body.detail : (body.detail?.[0]?.msg || "register_failed");
    const err = new Error(detailMsg);
    err.status = res.status;
    throw err;
  }
  // Backend sekarang return { ok, username, message } — akun belum aktif,
  // user harus verifikasi OTP dulu. JANGAN set token di sini.
  return res.json();
}

export function logout() {
  clearToken();
  clearUser();
}

function authHeaders() {
  return { Authorization: `Bearer ${getToken()}` };
}

export async function fetchProfile() {
  const res = await fetch("/api/auth/profile", { headers: authHeaders() });
  if (!res.ok) throw new Error("profile_fetch_failed");
  return res.json();
}

export async function updateProfile(fullName) {
  const res = await fetch("/api/auth/profile", {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ full_name: fullName }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.detail || "profile_update_failed");
    err.status = res.status;
    throw err;
  }
  return data;
}

export async function changePassword(currentPassword, newPassword) {
  const res = await fetch("/api/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.detail || "change_password_failed");
    err.status = res.status;
    throw err;
  }
  // Backend meng-invalidate semua sesi user ini begitu password berhasil
  // diganti -- bersihkan token lokal juga.
  clearToken();
  return data;
}