const KEY_USER = "oran-dashboard:user";
const KEY_ROLE = "oran-dashboard:role";

export function getUser() {
  return window.localStorage.getItem(KEY_USER) || "";
}

export function setUser(name) {
  window.localStorage.setItem(KEY_USER, name);
}

export function clearUser() {
  window.localStorage.removeItem(KEY_USER);
  window.localStorage.removeItem(KEY_ROLE);
}

export function getRole() {
  return window.localStorage.getItem(KEY_ROLE) || "engineer";
}

export function setRole(role) {
  window.localStorage.setItem(KEY_ROLE, role || "engineer");
}