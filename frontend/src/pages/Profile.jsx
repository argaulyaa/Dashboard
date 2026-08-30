import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getToken, fetchProfile, updateProfile, changePassword, logout } from "../auth.js";
import { fetchUsers, deleteUser, updateUserRole } from "../api.js";
import { getRole } from "../user.js";

function formatDateTime(ts) {
  if (!ts) return "-";
  return new Date(ts).toLocaleString("en-US", {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function formatRemaining(seconds) {
  if (seconds == null) return "-";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m remaining`;
}

function formatAgo(ts) {
  if (!ts) return "-";
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diffSec < 60) return "Just now";
  const m = Math.floor(diffSec / 60);
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"} ago`;
  return `${Math.floor(m / 60)} hour${Math.floor(m / 60) === 1 ? "" : "s"} ago`;
}

const ERROR_MESSAGES = {
  current_password_incorrect: "Current password is incorrect.",
  password_too_short: "New password must be at least 8 characters long.",
  password_needs_uppercase: "New password must contain at least one uppercase letter.",
  password_needs_digit: "New password must contain at least one digit.",
  builtin_account_password_fixed:
    "Built-in accounts (e.g. admin) are managed via ORAN_USERS environment variable and cannot change password here.",
  builtin_account_not_editable:
    "Built-in accounts do not have an editable display name.",
};

function humanizeError(message) {
  return ERROR_MESSAGES[message] || "An error occurred. Please try again.";
}

function SessionRow({ label, value, valueClass = "text-on-surface", bold = false }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-outline-variant/10">
      <span className="text-on-surface-variant text-body-md">{label}</span>
      <span className={`font-code-md text-code-md ${valueClass} ${bold ? "font-bold" : ""}`}>{value}</span>
    </div>
  );
}

export default function Profile({ currentUser, onUserChange, onLogout, opsCount = 0, lastTelemetryAt }) {
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [sessionError, setSessionError] = useState(false);
  const [profile, setProfile] = useState(null); // { username, full_name, editable }
  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState("");
  const [nameBusy, setNameBusy] = useState(false);
  const [nameError, setNameError] = useState(null);
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [pwMessage, setPwMessage] = useState(null);
  const [pwBusy, setPwBusy] = useState(false);

  // Admin user management state
  const [usersList, setUsersList] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [deletingUser, setDeletingUser] = useState(null);
  const [changingRole, setChangingRole] = useState(null);

  const isAdmin = currentUser === "admin" || getRole() === "admin";

  const loadUsersList = async () => {
    if (!isAdmin) return;
    setLoadingUsers(true);
    try {
      const list = await fetchUsers();
      setUsersList(list);
    } catch {
      setUsersList([]);
    } finally {
      setLoadingUsers(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/auth/session", {
          headers: { Authorization: `Bearer ${getToken()}` },
        });
        if (!res.ok) throw new Error("session_fetch_failed");
        const data = await res.json();
        if (!cancelled) setSession(data);
      } catch {
        if (!cancelled) setSessionError(true);
      }
    })();
    fetchProfile()
      .then((p) => !cancelled && setProfile(p))
      .catch(() => {});
    if (isAdmin) {
      loadUsersList();
    }
    return () => { cancelled = true; };
  }, [isAdmin]);

  const handleRemoveUser = async (targetUsername) => {
    if (!window.confirm(`Are you sure you want to delete user account "${targetUsername}"?`)) {
      return;
    }
    setDeletingUser(targetUsername);
    try {
      await deleteUser(targetUsername);
      await loadUsersList();
    } catch (e) {
      alert(e.message || "Failed to delete user.");
    } finally {
      setDeletingUser(null);
    }
  };

  const handleChangeRole = async (targetUsername, newRole, currentRole) => {
    if (currentRole === newRole) return;
    setChangingRole(targetUsername);
    try {
      await updateUserRole(targetUsername, newRole);
      await loadUsersList();
    } catch (e) {
      alert(e.message || "Failed to update user role.");
    } finally {
      setChangingRole(null);
    }
  };

  const displayName = profile?.full_name || currentUser || "Admin";

  const handleLogoutClick = () => {
    if (!window.confirm("Are you sure you want to logout?")) return;
    // Prefer parent handler (App.jsx::handleLogout clears user+token and reloads)
    if (typeof onLogout === "function") {
      onLogout();
      return;
    }
    // Fallback: direct logout then navigate to login and clear full_name state
    try { logout(); } catch (_) {}
    if (typeof onUserChange === "function") onUserChange("");
    setProfile(null);
    setSession(null);
    navigate("/login", { replace: true });
    window.location.reload();
  };

  const saveName = async () => {
    const name = nameValue.trim();
    if (!name) return;
    setNameBusy(true);
    setNameError(null);
    try {
      const updated = await updateProfile(name);
      setProfile(updated);
      setEditingName(false);
    } catch (e) {
      setNameError(humanizeError(e.message));
    } finally {
      setNameBusy(false);
    }
  };

  const handlePasswordSubmit = async (e) => {
    e.preventDefault();
    setPwMessage(null);
    if (!form.next || form.next !== form.confirm) {
      setPwMessage({ type: "error", text: "New password and confirmation do not match." });
      return;
    }
    setPwBusy(true);
    try {
      await changePassword(form.current, form.next);
      setPwMessage({
        type: "success",
        text: "Password changed successfully. Redirecting to login page...",
      });
      setForm({ current: "", next: "", confirm: "" });
      setTimeout(() => {
        logout();
        navigate("/login", { replace: true });
        window.location.reload();
      }, 1800);
    } catch (e) {
      setPwMessage({ type: "error", text: humanizeError(e.message) });
    } finally {
      setPwBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter">
      <div className="lg:col-span-8">
        <div className="bg-white p-8 rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant/30 flex flex-col md:flex-row gap-8 items-start md:items-center relative overflow-hidden h-full">
          <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full -mr-16 -mt-16" />
          <div className="w-32 h-32 rounded-2xl bg-primary-container flex items-center justify-center text-white font-display-lg text-display-lg shrink-0 shadow-lg border-4 border-white">
            {(displayName || "?").trim().slice(0, 2).toUpperCase()}
          </div>
          <div className="flex-1 space-y-2 min-w-0">
            {editingName ? (
              <div className="flex items-center gap-2 flex-wrap">
                <input
                  className="font-headline-md text-headline-md bg-surface-container-low rounded-lg px-3 py-1 outline-none focus:ring-2 focus:ring-primary-container"
                  value={nameValue}
                  onChange={(e) => setNameValue(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && saveName()}
                  autoFocus
                  disabled={nameBusy}
                />
                <button
                  className="px-3 py-1.5 rounded-lg bg-primary-container text-white text-label-sm font-semibold disabled:opacity-50"
                  onClick={saveName}
                  disabled={nameBusy}
                >
                  {nameBusy ? "..." : "Save"}
                </button>
                <button
                  className="px-3 py-1.5 rounded-lg text-on-surface-variant text-label-sm font-semibold"
                  onClick={() => { setEditingName(false); setNameError(null); }}
                  disabled={nameBusy}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <h2
                className={`font-headline-md text-headline-md text-on-surface ${
                  profile?.editable ? "cursor-pointer hover:underline decoration-dotted" : ""
                }`}
                title={profile?.editable ? "Click to edit display name" : "Built-in account, display name cannot be changed"}
                onClick={() => {
                  if (!profile?.editable) return;
                  setNameValue(displayName);
                  setEditingName(true);
                }}
              >
                {displayName}
              </h2>
            )}
            <p className="font-code-md text-code-md text-on-surface-variant">@{currentUser || "admin"}</p>
            {nameError && <p className="text-error text-xs">{nameError}</p>}
            <div className="pt-2">
              <button
                onClick={handleLogoutClick}
                aria-label="Logout"
                title="Logout from dashboard"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-error text-white font-label-lg text-label-lg hover:bg-error/90 active:scale-95 transition-all shadow-sm focus:outline-none focus:ring-2 focus:ring-error/40"
              >
                <span className="material-symbols-outlined text-[18px]">logout</span>
                Logout
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="lg:col-span-4">
        <div className="bg-white p-6 rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant/30 h-full flex flex-col justify-between">
          <h3 className="font-title-md text-title-md text-on-surface mb-4">Active Session</h3>
          {sessionError ? (
            <p className="text-on-surface-variant text-body-md">Session details not available.</p>
          ) : !session ? (
            <p className="text-on-surface-variant text-body-md">Loading session...</p>
          ) : (
            <div className="space-y-1">
              <SessionRow label="Username" value={session.user} bold />
              <SessionRow label="IP Address" value={session.ip} />
              <SessionRow
                label="Session Expires"
                value={`in ${Math.round(session.remaining_seconds / 60)} min`}
                valueClass="text-secondary"
              />
            </div>
          )}
        </div>
      </div>

      <div className="lg:col-span-7">
        <div className="bg-white p-8 rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant/30">
          <h3 className="font-title-lg text-title-lg text-on-surface mb-2">Security Settings</h3>
          <p className="text-on-surface-variant text-body-md mb-6">Update your password to keep your account secure.</p>
          <form className="space-y-6" onSubmit={handlePasswordSubmit}>
            <div>
              <label className="block font-label-lg text-label-lg text-on-surface-variant mb-2">Current Password</label>
              <input
                className="w-full p-3 rounded-xl border border-outline-variant focus:ring-2 focus:ring-primary focus:border-primary transition-all outline-none"
                placeholder="••••••••••••"
                type="password"
                value={form.current}
                onChange={(e) => setForm({ ...form, current: e.target.value })}
              />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block font-label-lg text-label-lg text-on-surface-variant mb-2">New Password</label>
                <input
                  className="w-full p-3 rounded-xl border border-outline-variant focus:ring-2 focus:ring-primary focus:border-primary transition-all outline-none"
                  placeholder="••••••••••••"
                  type="password"
                  value={form.next}
                  onChange={(e) => setForm({ ...form, next: e.target.value })}
                />
              </div>
              <div>
                <label className="block font-label-lg text-label-lg text-on-surface-variant mb-2">Confirm Password</label>
                <input
                  className="w-full p-3 rounded-xl border border-outline-variant focus:ring-2 focus:ring-primary focus:border-primary transition-all outline-none"
                  placeholder="••••••••••••"
                  type="password"
                  value={form.confirm}
                  onChange={(e) => setForm({ ...form, confirm: e.target.value })}
                />
              </div>
            </div>
            <div className="bg-surface-container-low p-4 rounded-lg flex items-start gap-3">
              <span className="material-symbols-outlined text-primary text-sm mt-0.5">info</span>
              <p className="text-xs text-on-surface-variant">
                New password must be at least 8 characters long, containing at least one uppercase letter and one digit.
                Changing your password will sign out all active sessions.
              </p>
            </div>
            {pwMessage && (
              <p className={`text-label-sm ${pwMessage.type === "error" ? "text-error" : "text-secondary"}`}>
                {pwMessage.text}
              </p>
            )}
            <div className="flex justify-end gap-4">
              <button
                type="button"
                className="px-6 py-2 rounded-xl text-on-surface-variant font-label-lg text-label-lg hover:bg-surface-container transition-colors"
                onClick={() => setForm({ current: "", next: "", confirm: "" })}
              >
                Discard
              </button>
              <button
                type="submit"
                className="px-8 py-2 rounded-xl bg-primary text-on-primary font-label-lg text-label-lg hover:shadow-lg active:scale-95 transition-all"
              >
                Update Password
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Stats */}
      <div className="lg:col-span-5 grid grid-rows-2 gap-gutter">
        <div className="bg-white p-6 rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant/30 flex items-center justify-between">
          <div>
            <p className="text-on-surface-variant font-label-lg text-label-lg">Total Operations Logged</p>
            <h4 className="text-display-lg font-display-lg text-primary mt-1">{opsCount}</h4>
          </div>
          <span className="material-symbols-outlined text-primary/30 text-[48px]">bar_chart</span>
        </div>
        <div className="bg-white p-6 rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant/30 flex items-center justify-between">
          <div>
            <p className="text-on-surface-variant font-label-lg text-label-lg">Last Topology Update</p>
            <h4 className="text-title-lg font-title-lg text-on-surface mt-1">{formatAgo(lastTelemetryAt)}</h4>
          </div>
          <div className="w-12 h-12 rounded-full bg-secondary-container flex items-center justify-center text-on-secondary-container">
            <span className="material-symbols-outlined">sync</span>
          </div>
        </div>
      </div>

      {/* User Management Section (Admin Only) */}
      {isAdmin && (
        <div className="lg:col-span-12 bg-white rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant/30 overflow-hidden">
          <div className="px-8 py-5 border-b border-outline-variant/30 flex items-center justify-between bg-surface-bright flex-wrap gap-3">
            <div>
              <h3 className="font-title-lg text-title-lg text-on-surface flex items-center gap-2">
                <span className="material-symbols-outlined text-primary">admin_panel_settings</span>
                User Management (Admin Only)
              </h3>
              <p className="text-body-md text-on-surface-variant opacity-70">
                Manage registered user accounts and remove inactive users from the system.
              </p>
            </div>
            <button
              className="px-4 py-1.5 border border-outline-variant text-on-surface text-xs font-bold rounded-lg hover:bg-surface-container transition-colors flex items-center gap-1.5"
              onClick={loadUsersList}
              disabled={loadingUsers}
            >
              <span className={`material-symbols-outlined text-sm ${loadingUsers ? "animate-spin" : ""}`}>
                refresh
              </span>
              Refresh Users
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-container-low text-[11px] uppercase tracking-wider font-bold text-on-surface-variant whitespace-nowrap">
                  <th className="px-8 py-3">Network ID (Username)</th>
                  <th className="px-8 py-3">Full Name</th>
                  <th className="px-8 py-3">Role</th>
                  <th className="px-8 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant text-sm whitespace-nowrap">
                {usersList.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-8 py-6 text-center text-on-surface-variant text-xs italic">
                      {loadingUsers ? "Loading registered accounts..." : "No self-registered accounts found."}
                    </td>
                  </tr>
                )}
                {usersList.map((u) => (
                  <tr key={u.username} className="hover:bg-surface-container-low transition-colors">
                    <td className="px-8 py-3 font-bold text-on-surface">
                      @{u.username}
                    </td>
                    <td className="px-8 py-3 text-on-surface-variant font-medium">
                      {u.full_name || "-"}
                    </td>
                    <td className="px-8 py-3">
                      <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                        u.role === "admin" ? "bg-primary/10 text-primary" : "bg-surface-container-high text-on-surface-variant"
                      }`}>
                        {/* RBAC 2-role: nilai lama ('engineer'/'viewer') sudah dinormalisasi backend jadi 'user' */}
                        {u.role || "user"}
                      </span>
                    </td>
                    <td className="px-8 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {u.role !== "admin" && (
                          <button
                            className="px-3 py-1 bg-primary/10 text-primary text-xs font-bold rounded-lg hover:bg-primary hover:text-white transition-all active:scale-95 disabled:opacity-50 flex items-center gap-1.5"
                            onClick={() => handleChangeRole(u.username, "admin", u.role)}
                            disabled={changingRole === u.username}
                          >
                            <span className="material-symbols-outlined text-sm">shield_person</span>
                            {changingRole === u.username ? "Updating..." : "Jadikan Admin"}
                          </button>
                        )}
                        {u.role !== "user" && (
                          <button
                            className="px-3 py-1 bg-surface-container-high text-on-surface-variant text-xs font-bold rounded-lg hover:bg-outline hover:text-white transition-all active:scale-95 disabled:opacity-50 flex items-center gap-1.5"
                            onClick={() => handleChangeRole(u.username, "user", u.role)}
                            disabled={changingRole === u.username}
                          >
                            <span className="material-symbols-outlined text-sm">person</span>
                            {changingRole === u.username ? "Updating..." : "Jadikan User"}
                          </button>
                        )}
                        <button
                          className="px-3 py-1 bg-error-container text-on-error-container text-xs font-bold rounded-lg hover:bg-error hover:text-white transition-all active:scale-95 disabled:opacity-50 flex items-center gap-1.5"
                          onClick={() => handleRemoveUser(u.username)}
                          disabled={deletingUser === u.username}
                        >
                          <span className="material-symbols-outlined text-sm">delete</span>
                          {deletingUser === u.username ? "Deleting..." : "Delete Account"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}