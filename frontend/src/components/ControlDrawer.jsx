import React, { useState } from "react";
import { Link } from "react-router-dom";
import { getRole } from "../user.js";

function formatRemaining(seconds) {
  if (!seconds || seconds <= 0) return "0m 0s";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

function formatTimeRange(startTs, endTs) {
  if (!startTs || !endTs) return "";
  const startStr = new Date(startTs * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const endStr = new Date(endTs * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${startStr} - ${endStr}`;
}

const STATUS_PILL = {
  healthy: "bg-healthy/10 text-healthy",
  degraded: "bg-degraded/10 text-degraded",
  down: "bg-down/10 text-down",
  restarting: "bg-restarting/10 text-restarting",
};

export default function ControlDrawer({ domain, component, currentUser, onClose, onRestart }) {
  const [busyRestart, setBusyRestart] = useState(false);

  if (!component) return null;

  const resStatus = component.reservation || {};
  const activeRes = resStatus.active;
  const upcomingRes = resStatus.upcoming || [];

  const heldByMe = activeRes && activeRes.user === currentUser;
  const heldByOther = activeRes && activeRes.user !== currentUser;

  const handleRestart = async () => {
    setBusyRestart(true);
    try {
      await onRestart(domain, component.id);
    } finally {
      setBusyRestart(false);
    }
  };

  return (
    <aside className="fixed top-0 right-0 h-full w-[340px] bg-panel border-l border-panel-border p-6 shadow-[-12px_0_24px_rgba(0,0,0,0.4)] flex flex-col gap-5 overflow-y-auto z-[60]">
      <div className="flex justify-between items-start">
        <div>
          <div className="font-mono text-[11px] text-dim tracking-wider">{domain.toUpperCase()}</div>
          <h2 className="mt-1 mb-0 text-lg">{component.name}</h2>
        </div>
        <button
          className="bg-transparent border-none text-dim text-2xl cursor-pointer leading-none"
          onClick={onClose}
          aria-label="Close"
        >
          ×
        </button>
      </div>

      <dl className="flex flex-col gap-3 m-0">
        <div>
          <dt className="text-[11px] text-dim font-mono mb-0.5">Type</dt>
          <dd className="m-0 text-[13px]">{component.kind}</dd>
        </div>
        <div>
          <dt className="text-[11px] text-dim font-mono mb-0.5">Status</dt>
          <dd
            className={`m-0 inline-block font-mono text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wide ${
              STATUS_PILL[component.status] ?? "bg-dim/10 text-dim"
            }`}
          >
            {component.status}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] text-dim font-mono mb-0.5">Details</dt>
          <dd className="m-0 text-[13px]">{component.detail || "-"}</dd>
        </div>
        {component.host && (
          <div>
            <dt className="text-[11px] text-dim font-mono mb-0.5">Host</dt>
            <dd className="m-0 text-[13px] font-mono">{component.host}</dd>
          </div>
        )}
      </dl>

      <div>
        <button
          className="font-sans text-[13px] font-semibold px-4 py-2.5 rounded-lg border border-down/40 bg-transparent text-down cursor-pointer w-full hover:bg-down/[0.08] disabled:opacity-50 disabled:cursor-not-allowed"
          onClick={handleRestart}
          disabled={busyRestart || component.status === "restarting"}
          title=""
        >
          {busyRestart || component.status === "restarting" ? "Restarting..." : "Restart Component"}
        </button>
      </div>

      {component.host && (
        <div className="border-t border-panel-border pt-4 flex flex-col gap-2.5">
          <h3 className="text-[13px] m-0 text-dim font-mono uppercase tracking-wide">
            Console Access
          </h3>

          {heldByMe && (
            <>
              <p className="text-xs leading-relaxed m-0 text-healthy">
                Reserved by you — {formatRemaining(activeRes.remaining_seconds)} remaining ({formatTimeRange(activeRes.start_at, activeRes.end_at)})
              </p>
              <code className="block bg-slate-100 border border-panel-border rounded-md px-2.5 py-2 font-mono text-xs text-restarting">
                ssh user@{component.host}
              </code>
              <Link
                className="font-sans text-[13px] font-semibold px-4 py-2.5 rounded-lg border border-restarting/40 bg-primary text-white cursor-pointer w-full text-center hover:bg-primary-container block"
                to={`/ssh/${domain}/${component.id}`}
              >
                Open Console
              </Link>
            </>
          )}

          {heldByOther && (
            <p className="text-xs leading-relaxed m-0 text-degraded">
              Currently occupied by <strong>{activeRes.user}</strong> —{" "}
              {formatRemaining(activeRes.remaining_seconds)} remaining.
            </p>
          )}

          {!activeRes && (
            <p className="text-xs text-dim leading-relaxed">
              No active session right now.
            </p>
          )}

          {upcomingRes.length > 0 && (
            <div className="bg-surface-container-low p-3 rounded-lg border border-outline-variant/40 mt-1">
              <p className="text-[11px] font-bold text-on-surface-variant uppercase tracking-wider mb-1">
                Upcoming Bookings ({upcomingRes.length})
              </p>
              <div className="space-y-1">
                {upcomingRes.slice(0, 2).map((u) => (
                  <p key={u.id} className="text-xs text-on-surface-variant">
                    • <strong>{u.user}</strong> ({formatTimeRange(u.start_at, u.end_at)})
                  </p>
                ))}
              </div>
            </div>
          )}

          <Link
            className="font-sans text-[13px] font-semibold px-4 py-2 rounded-lg border border-outline-variant bg-transparent text-primary cursor-pointer w-full text-center hover:bg-surface-container block mt-2"
            to="/reservations"
          >
            Manage / Schedule Slots
          </Link>
        </div>
      )}

      <p className="text-xs text-dim leading-relaxed">
        Additional control actions (scale, reconfigure, toggle policy) can be added here as features evolve.
      </p>
    </aside>
  );
}
