import React, { useMemo, useState, useEffect } from "react";
import { fetchProviders, fetchComponents } from "../api.js";
import { getRole } from "../user.js";
import LogsModal from "../components/LogsModal.jsx";

const STATUS_DOT = {
  healthy: "text-secondary",
  degraded: "text-tertiary",
  down: "text-error",
  restarting: "text-primary",
};

const STATUS_LABEL = {
  healthy: "Healthy",
  degraded: "Degraded",
  down: "Down",
  restarting: "Restarting...",
};

// Status agregat satu domain: kalau ada 1 komponen down -> domain dianggap
// down, kalau ada yang degraded -> degraded, selain itu healthy.
function domainHealth(components) {
  if (!components?.length) return "down";
  if (components.some((c) => c.status === "down")) return "down";
  if (components.some((c) => c.status === "degraded")) return "degraded";
  return "healthy";
}

const HEALTH_BADGE_LABEL = { healthy: "ONLINE", degraded: "DEGRADED", down: "OFFLINE" };
const HEALTH_BADGE_CLASS = {
  healthy: "bg-secondary-container text-on-secondary-container",
  degraded: "bg-tertiary-container text-on-tertiary-container",
  down: "bg-error-container text-on-error-container",
};

function formatUptime(seconds) {
  if (!seconds || seconds < 0) return "-";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${d}d ${String(h).padStart(2, "0")}h ${String(m).padStart(2, "0")}m`;
}

export default function CorePage({ components, currentUser, onSelect, onRestart }) {
  // Daftar provider datang dari backend (GET /api/core/providers), bukan
  // ditulis manual di sini. Kalau backend nambah provider baru, tab baru
  // otomatis muncul tanpa file ini disentuh lagi.
  const [providers, setProviders] = useState([]);
  const [activeProvider, setActiveProvider] = useState(null);
  const [providerComponents, setProviderComponents] = useState(null);
  const [restartingId, setRestartingId] = useState(null);
  const [logTarget, setLogTarget] = useState(null);

  useEffect(() => {
    fetchProviders("core")
      .then((list) => {
        setProviders(list);
        if (list.length) setActiveProvider(list[0].key);
      })
      .catch(() => setProviders([]));
  }, []);

  // Provider pertama (default) pakai data live dari WebSocket telemetry
  // (`components` prop, sudah dikirim App.jsx). Provider lain (kalau ada)
  // diambil sekali lewat REST saat tab-nya diklik.
  const isDefaultProvider = providers[0]?.key === activeProvider;

  useEffect(() => {
    if (!activeProvider || isDefaultProvider) {
      setProviderComponents(null);
      return;
    }
    fetchComponents("core", activeProvider)
      .then(setProviderComponents)
      .catch(() => setProviderComponents([]));
  }, [activeProvider, isDefaultProvider]);

  const activeMeta = providers.find((p) => p.key === activeProvider);
  const displayedComponents = isDefaultProvider ? components : (providerComponents || []);

  // "Hero" component = AMF, dipakai mewakili instance Core secara keseluruhan
  // (lihat komentar di backend/adapters.py: host di AMF = host instance Core).
  const hero = displayedComponents.find((c) => c.id === "amf") || displayedComponents[0];
  const health = domainHealth(displayedComponents);

  const heroView = {
    ip: hero?.host || "-",
    cpuPct: hero?.cpu_pct ?? 0,
    memGb: hero?.mem_gb ?? 0,
    memPct: hero?.mem_pct ?? 0,
    sshActive: !!hero?.host,
    operator: hero?.reservation?.user || "-",
  };

  const activeCount = displayedComponents.filter((c) => c.status !== "down").length;

  const handleRestartRow = async (id) => {
    setRestartingId(id);
    try {
      await onRestart("core", id);
    } finally {
      setRestartingId(null);
    }
  };

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Page Header */}
      <div className="mb-8">
        <h2 className="text-headline-md font-headline-md text-on-surface mb-2">Core Network Management</h2>
        <p className="text-on-surface-variant">
          Configure and monitor 5G Core Network functions across multiple providers.
        </p>
      </div>

      {/* Provider Selector Tabs -- dirender dari data backend, jumlah tab
          mengikuti berapa provider yang benar-benar terdaftar */}
      <div className="flex flex-wrap gap-4 mb-8">
        {providers.map((p) => {
          const active = p.key === activeProvider;
          return (
            <button
              key={p.key}
              onClick={() => setActiveProvider(p.key)}
              className={`flex items-center gap-3 px-6 py-4 rounded-xl border-2 transition-all duration-200 glass-card ${
                active
                  ? "border-primary text-primary shadow-md"
                  : "border-transparent text-on-surface-variant hover:bg-surface-container"
              }`}
            >
              <span className="material-symbols-outlined">{p.icon}</span>
              <div className="text-left">
                <p className="text-xs uppercase tracking-widest font-bold opacity-70">Provider</p>
                <p className="font-bold">{p.label}</p>
              </div>
            </button>
          );
        })}
      </div>

      {/* Bento Grid Dashboard */}
      <div className="grid grid-cols-12 gap-6">
        {/* Status Main Card */}
        <div className="col-span-12 lg:col-span-8 glass-card rounded-2xl p-6 shadow-sm border border-outline-variant relative overflow-hidden">
          <div className="absolute top-0 right-0 p-4">
            <span className={`px-3 py-1 text-xs font-bold rounded-full ${HEALTH_BADGE_CLASS[health]}`}>
              ● {HEALTH_BADGE_LABEL[health]}
            </span>
          </div>
          <div className="flex items-start gap-6 mb-8">
            <div className="p-4 bg-primary-container text-white rounded-2xl shadow-lg">
              <span className="material-symbols-outlined text-4xl">{activeMeta?.icon || "cloud_done"}</span>
            </div>
            <div>
              <h3 className="text-title-lg font-title-lg mb-1">{activeMeta?.label || "Core"}</h3>
              <p className="text-sm text-on-surface-variant">{activeMeta?.desc || ""}</p>
              <div className="flex gap-4 mt-4">
                <div className="bg-surface-container px-3 py-2 rounded-lg">
                  <p className="text-[10px] text-on-surface-variant font-bold uppercase">IPv4 Address</p>
                  <p className="font-mono text-sm">{heroView.ip}</p>
                </div>
                <div className="bg-surface-container px-3 py-2 rounded-lg">
                  <p className="text-[10px] text-on-surface-variant font-bold uppercase">Current Operator</p>
                  <p className="text-sm">{heroView.operator}</p>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-surface-bright rounded-xl p-4 border border-outline-variant">
              <div className="flex justify-between items-end mb-2">
                <p className="text-sm font-bold">CPU Usage</p>
                <p className="text-2xl font-bold text-primary">{heroView.cpuPct}%</p>
              </div>
              <div className="w-full bg-surface-container rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full transition-all duration-500"
                  style={{ width: `${heroView.cpuPct}%` }}
                />
              </div>
            </div>
            <div className="bg-surface-bright rounded-xl p-4 border border-outline-variant">
              <div className="flex justify-between items-end mb-2">
                <p className="text-sm font-bold">Memory (RAM)</p>
                <p className="text-2xl font-bold text-primary">{heroView.memGb} GB</p>
              </div>
              <div className="w-full bg-surface-container rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full transition-all duration-500"
                  style={{ width: `${heroView.memPct}%` }}
                />
              </div>
            </div>
          </div>

          <div className="mt-8 flex justify-end gap-3">
            <button
              className="px-6 py-2.5 border border-outline-variant text-on-surface font-bold rounded-lg hover:bg-surface-container-low transition-colors flex items-center gap-2"
              onClick={() => hero && setLogTarget({ domain: "core", compId: hero.id, compName: hero.name })}
            >
              <span className="material-symbols-outlined text-lg">subject</span>
              View Logs
            </button>
            {getRole() !== "viewer" && (
              heroView.sshActive ? (
                <button
                  className="px-6 py-2.5 bg-primary text-white font-bold rounded-lg shadow-md hover:brightness-110 active:scale-95 transition-all flex items-center gap-2"
                  onClick={() => hero && onSelect(hero)}
                >
                  <span className="material-symbols-outlined text-lg">terminal</span>
                  Console
                </button>
              ) : (
                <button
                  className="px-6 py-2.5 bg-outline-variant text-white font-bold rounded-lg opacity-50 cursor-not-allowed flex items-center gap-2"
                  disabled
                >
                  <span className="material-symbols-outlined text-lg">block</span>
                  Session Busy
                </button>
              )
            )}
          </div>
        </div>

        {logTarget && (
          <LogsModal
            domain={logTarget.domain}
            compId={logTarget.compId}
            compName={logTarget.compName}
            onClose={() => setLogTarget(null)}
          />
        )}

        {/* Right Sidebar: Connectivity Visualization */}
        <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
          <div className="glass-card rounded-2xl p-6 shadow-sm border border-outline-variant flex-1 flex flex-col items-center justify-center text-center">
            <h4 className="text-sm font-bold mb-4 self-start">Topology Overview</h4>
            <div className="relative w-48 h-48 mb-4">
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-16 h-16 rounded-full bg-primary-container border-4 border-white shadow-lg z-10 flex items-center justify-center">
                  <span className="material-symbols-outlined text-white">hub</span>
                </div>
              </div>
              <div className="absolute top-0 left-1/2 -translate-x-1/2 flex flex-col items-center">
                <div className="w-8 h-8 rounded-full bg-secondary border-2 border-white shadow-sm flex items-center justify-center">
                  <span className="material-symbols-outlined text-white text-xs">cell_tower</span>
                </div>
                <p className="text-[10px] font-bold mt-1">UE-01</p>
              </div>
              <div className="absolute bottom-4 left-4 flex flex-col items-center">
                <div className="w-8 h-8 rounded-full bg-secondary border-2 border-white shadow-sm flex items-center justify-center">
                  <span className="material-symbols-outlined text-white text-xs">smartphone</span>
                </div>
                <p className="text-[10px] font-bold mt-1">SIM-04</p>
              </div>
              <div className="absolute bottom-4 right-4 flex flex-col items-center">
                <div className="w-8 h-8 rounded-full bg-secondary border-2 border-white shadow-sm flex items-center justify-center">
                  <span className="material-symbols-outlined text-white text-xs">router</span>
                </div>
                <p className="text-[10px] font-bold mt-1">GNB-3</p>
              </div>
              <svg className="absolute inset-0 w-full h-full -z-10" viewBox="0 0 100 100">
                <line stroke="#0c56d0" strokeDasharray="2 2" strokeWidth="1" x1="50" x2="50" y1="50" y2="20" />
                <line stroke="#0c56d0" strokeDasharray="2 2" strokeWidth="1" x1="50" x2="25" y1="50" y2="75" />
                <line stroke="#0c56d0" strokeDasharray="2 2" strokeWidth="1" x1="50" x2="75" y1="50" y2="75" />
              </svg>
            </div>
            <p className="text-xs text-on-surface-variant">{activeCount} Active Network Nodes connected to this core instance.</p>
          </div>

          <div className="glass-card rounded-2xl p-6 shadow-sm border border-outline-variant">
            <h4 className="text-sm font-bold mb-4">Instance Health</h4>
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-xs">Uptime</span>
                <span className="text-xs font-mono font-bold">{formatUptime(hero?.uptime_seconds)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs">Latency (Backhaul)</span>
                <span className="text-xs font-mono font-bold text-secondary">
                  {hero?.latency_ms != null ? `${hero.latency_ms}ms` : "-"}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs">Active Sessions</span>
                <span className="text-xs font-mono font-bold">-</span>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Full-width Row: Service List */}
        <div className="col-span-12 glass-card rounded-2xl shadow-sm border border-outline-variant overflow-hidden">
          <div className="px-6 py-4 border-b border-outline-variant flex justify-between items-center">
            <h4 className="text-sm font-bold">Running Microservices</h4>
            <span className="text-xs bg-surface-container px-2 py-1 rounded">
              {activeCount} / {displayedComponents.length} Services Running
            </span>
          </div>
          <table className="w-full text-left">
            <thead>
              <tr className="bg-surface-container-low text-[11px] uppercase tracking-wider font-bold text-on-surface-variant">
                <th className="px-6 py-3">Service Name</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Throughput</th>
                <th className="px-6 py-3">Port</th>
                <th className="px-6 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="text-sm divide-y divide-outline-variant">
              {displayedComponents.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-6 text-center text-on-surface-variant text-xs font-mono">
                    No component data available.
                  </td>
                </tr>
              )}
              {displayedComponents.map((c) => (
                <tr key={c.id} className="hover:bg-surface-container-low">
                  <td className="px-6 py-4 font-medium cursor-pointer" onClick={() => onSelect(c)}>
                    {c.name} <span className="text-on-surface-variant font-normal">({c.kind})</span>
                    {c.reservation && (
                      <span className="ml-1.5 text-xs" title={`Reserved by ${c.reservation.user}`}>
                        🔒
                      </span>
                    )}
                  </td>
                  <td className={`px-6 py-4 text-xs font-bold ${STATUS_DOT[c.status] ?? "text-on-surface-variant"}`}>
                    ● {STATUS_LABEL[c.status] ?? c.status}
                  </td>
                  <td className="px-6 py-4 font-mono text-xs">{c.throughput_mbps} Mbps</td>
                  <td className="px-6 py-4 font-mono text-xs">{c.port || "-"}</td>
                  <td className="px-6 py-4 text-right">
                    <button
                      className="text-primary hover:underline font-bold text-xs disabled:opacity-50 disabled:no-underline disabled:cursor-not-allowed"
                      onClick={() => handleRestartRow(c.id)}
                      disabled={restartingId === c.id || c.status === "restarting" || getRole() === "viewer"}
                      title={getRole() === "viewer" ? "Viewers cannot restart components" : ""}
                    >
                      {restartingId === c.id || c.status === "restarting" ? "Restarting..." : "Restart"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}