import React, { useEffect, useState } from "react";
import { fetchAuditLogs } from "../api.js";
import { getRole } from "../user.js";
import { Navigate } from "react-router-dom";

function formatTimestamp(ts) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString("en-US", {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

const ACTION_BADGES = {
  LOGIN: "bg-blue-100 text-blue-800 border-blue-200",
  REGISTER: "bg-indigo-100 text-indigo-800 border-indigo-200",
  CREATE_RESERVATION: "bg-emerald-100 text-emerald-800 border-emerald-200",
  CANCEL_RESERVATION: "bg-amber-100 text-amber-800 border-amber-200",
  RESTART_COMPONENT: "bg-purple-100 text-purple-800 border-purple-200",
  DELETE_USER: "bg-rose-100 text-rose-800 border-rose-200",
};

export default function AuditLogs({ currentUser }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedAction, setSelectedAction] = useState("ALL");

  // RBAC 2-role: audit log admin-only (backend menegakkan dengan require_admin).
  const isAdmin = currentUser === "admin" || getRole() === "admin";

  const loadLogs = async () => {
    if (!isAdmin) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAuditLogs();
      setLogs(data);
    } catch (e) {
      setError(e.message || "Failed to load audit logs.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, [isAdmin]);

  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  const filteredLogs = logs.filter((l) => {
    const matchesUser = l.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (l.detail && l.detail.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesAction = selectedAction === "ALL" || l.action === selectedAction;
    return matchesUser && matchesAction;
  });

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-white rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant/30 p-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-2xl">shield</span>
            Security & Operations Audit Logs
          </h2>
          <p className="text-body-md text-on-surface-variant mt-1">
            Track user logins, scheduled node bookings, component restarts, and account security changes.
          </p>
        </div>
        <button
          className="px-4 py-2 border border-outline-variant text-on-surface text-label-lg font-bold rounded-lg hover:bg-surface-container transition-all flex items-center gap-2"
          onClick={loadLogs}
          disabled={loading}
        >
          <span className={`material-symbols-outlined text-base ${loading ? "animate-spin" : ""}`}>
            refresh
          </span>
          Refresh Logs
        </button>
      </div>

      {/* Filter Toolbar */}
      <div className="bg-white p-4 rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant/30 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2 w-full sm:w-auto flex-1 max-w-md">
          <span className="material-symbols-outlined text-on-surface-variant">search</span>
          <input
            type="text"
            placeholder="Search by username or detail..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <label className="text-xs font-semibold text-on-surface-variant whitespace-nowrap">Filter Action:</label>
          <select
            value={selectedAction}
            onChange={(e) => setSelectedAction(e.target.value)}
            className="bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-primary/40"
          >
            <option value="ALL">All Actions</option>
            <option value="LOGIN">LOGIN</option>
            <option value="REGISTER">REGISTER</option>
            <option value="CREATE_RESERVATION">CREATE_RESERVATION</option>
            <option value="CANCEL_RESERVATION">CANCEL_RESERVATION</option>
            <option value="RESTART_COMPONENT">RESTART_COMPONENT</option>
            <option value="DELETE_USER">DELETE_USER</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant/30 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-container-low text-[11px] uppercase tracking-wider font-bold text-on-surface-variant whitespace-nowrap">
                <th className="px-6 py-3.5">Timestamp</th>
                <th className="px-6 py-3.5">User</th>
                <th className="px-6 py-3.5">Action</th>
                <th className="px-6 py-3.5">Target (Domain / Comp)</th>
                <th className="px-6 py-3.5">IP Address</th>
                <th className="px-6 py-3.5">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant text-sm whitespace-nowrap">
              {loading && logs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-on-surface-variant italic">
                    Loading audit records...
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-error italic">
                    {error}
                  </td>
                </tr>
              ) : filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-on-surface-variant italic">
                    No audit logs recorded yet.
                  </td>
                </tr>
              ) : (
                filteredLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-surface-container-low/50 transition-colors">
                    <td className="px-6 py-3.5 text-xs text-on-surface-variant font-mono">
                      {formatTimestamp(log.timestamp)}
                    </td>
                    <td className="px-6 py-3.5 font-bold text-on-surface">
                      @{log.username}
                    </td>
                    <td className="px-6 py-3.5">
                      <span className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-md border ${
                        ACTION_BADGES[log.action] || "bg-slate-100 text-slate-700 border-slate-200"
                      }`}>
                        {log.action}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-xs text-on-surface font-medium">
                      {log.domain ? `${log.domain.toUpperCase()} / ${log.component_id || "-"}` : "-"}
                    </td>
                    <td className="px-6 py-3.5 font-mono text-xs text-on-surface-variant">
                      {log.ip_address || "127.0.0.1"}
                    </td>
                    <td className="px-6 py-3.5 text-xs text-on-surface-variant max-w-xs truncate" title={log.detail}>
                      {log.detail || "-"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
