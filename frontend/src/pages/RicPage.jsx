import React, { useMemo, useState, useEffect } from "react";
import { fetchProviders, fetchComponents, fetchActiveBooking } from "../api.js";
import { getRole } from "../user.js";
import LogsModal from "../components/LogsModal.jsx";
import ConsoleTerminal from "../components/ConsoleTerminal.jsx";
import { usePageHeader } from "../components/PageHeaderContext.jsx";

// Data referensi Service Model E2 -- ini spesifikasi standar O-RAN, bukan
// telemetry per-instance, jadi wajar tetap statis sampai ada endpoint nyata
// (misalnya /api/ric/service-models kalau nanti disambungkan ke FlexRIC SDK).
const SERVICE_MODELS = [
  { id: "E2SM-KPM", version: "v2.03", nodes: "2 Nodes", active: true },
  { id: "E2SM-RC", version: "v1.01", nodes: "2 Nodes", active: true },
  { id: "E2SM-MAC", version: "v1.00", nodes: "1 Node", active: true },
  { id: "E2SM-RLC", version: "v1.00", nodes: "1 Node", active: true },
  { id: "E2SM-GTP", version: "v2.00", nodes: "0 Nodes", active: false },
];

const STATUS_LABEL = {
  healthy: "Healthy",
  degraded: "Degraded",
  down: "Down",
  restarting: "Restarting...",
};

const STATUS_PILL = {
  healthy: "bg-secondary-container text-on-secondary-container",
  degraded: "bg-tertiary-container text-on-tertiary-container",
  down: "bg-error-container text-on-error-container",
  restarting: "bg-primary-container text-white",
};

const RAN_NODE_TEXT = {
  healthy: "text-secondary",
  degraded: "text-tertiary",
  down: "text-on-surface-variant",
  restarting: "text-primary",
};

function formatClock(ts) {
  if (!ts) return "--:--:--";
  return new Date(ts * 1000).toLocaleTimeString("id-ID", { hour12: false });
}

export default function RicPage({ components, ranComponents = [], currentUser, onSelect, onRestart }) {
  void ranComponents; // topology removed — param retained for compatibility
  const [providers, setProviders] = useState([]);
  const [activeProvider, setActiveProvider] = useState(null);
  const [providerComponents, setProviderComponents] = useState(null);
  const [restartingId, setRestartingId] = useState(null);
  const [logTarget, setLogTarget] = useState(null);
  const [consoleTarget, setConsoleTarget] = useState(null);
  const [hasBooking, setHasBooking] = useState(null);
  const isAdminRole = (()=>{ try{ return getRole()==="admin"; }catch{ return false; } })();
  const blockedByBooking = !isAdminRole && hasBooking===false;
  // poll booking like CorePage

  // Fetch daftar provider dari backend (data-driven, sama pola CorePage & RanPage)
  useEffect(() => {
    const check=async()=>{ if(isAdminRole){ setHasBooking(true); return; } try{ const a=await fetchActiveBooking(); setHasBooking(!!a); }catch{ setHasBooking(false); } };
    check(); const id=setInterval(check,8000); return()=>clearInterval(id);
  }, [isAdminRole]);
  useEffect(() => {
    fetchProviders("ric")
      .then((list) => {
        setProviders(list);
        if (list.length) setActiveProvider(list[0].key);
      })
      .catch(() => setProviders([]));
  }, []);

  // Provider pertama = live dari WebSocket (prop `components`).
  // Jika activeProvider null/belum di-load, anggap default provider (true).
  const isDefaultProvider = !activeProvider || !providers.length || providers[0]?.key === activeProvider;

  useEffect(() => {
    if (!activeProvider || isDefaultProvider) {
      setProviderComponents(null);
      return;
    }
    fetchComponents("ric", activeProvider)
      .then(setProviderComponents)
      .catch(() => setProviderComponents([]));
  }, [activeProvider, isDefaultProvider]);

  const activeMeta = providers.find((p) => p.key === activeProvider) || providers[0] || { label: "FlexRIC", icon: "memory", desc: "FlexRIC near-RT RIC & xApps" };
  const displayedComponents = isDefaultProvider ? components : (providerComponents || []);

  // "non-RT RIC" mewakili controller secara keseluruhan di kartu utama
  const hero = displayedComponents.find((c) => c.id === "nonrt-ric") || displayedComponents[0];

  const heroStatus = hero?.status || "healthy";
  const heroView = {
    cpuPct: hero?.cpu_pct ?? 0,
    memGb: hero?.mem_gb ?? 0,
    memPct: hero?.mem_pct ?? 0,
    latencyMs: hero?.latency_ms ?? 0,
  };

  // Log semu dibangun dari data komponen ASLI (status + detail + last_updated),
  // bukan endpoint log sungguhan -- backend belum punya stream log/event.
  const logLines = useMemo(() => {
    return [...displayedComponents]
      .sort((a, b) => (b.last_updated || 0) - (a.last_updated || 0))
      .slice(0, 8)
      .map((c, i) => ({
        key: `${c.id}-${i}`,
        time: formatClock(c.last_updated),
        level: c.status === "down" ? "ERROR" : c.status === "degraded" ? "WARN" : "INFO",
        text: `${c.name}: ${c.detail || "no detail"}`,
      }));
  }, [displayedComponents]);

  const handleRestartRow = async (id) => {
    setRestartingId(id);
    try {
      await onRestart("ric", id);
    } finally {
      setRestartingId(null);
    }
  };

  // Judul "RIC Management" + subtitle dirender sticky TopBar lewat
  // PageHeaderContext (revisi owner t_6c29abe5). Body tidak merender judul
  // duplikat; RIC sengaja TANPA kotak Current Operator.
  usePageHeader({
    title: "RIC Management",
    subtitle: "RAN Intelligent Controller configuration",
    right: null,
  });

  return (
    <div className="max-w-[1600px] mx-auto">
      {/* Judul "RIC Management" + subtitle kini dirender sticky TopBar lewat
          usePageHeader() (dipanggil sebelum return di atas) — body tidak
          merender judul duplikat lagi (revisi owner t_6c29abe5).
          Switcher provider dipertahankan agar fungsi ganti provider tidak
          hilang, tapi hanya tampil bila provider > 1; kondisi sekarang
          (satu provider FlexRIC) body bersih tanpa header lokal.
          RIC sengaja TANPA kotak Current Operator. */}
      {providers.length > 1 && (
        <div className="mb-8 flex justify-end">
          <div className="flex p-1 bg-surface-container-high rounded-xl w-fit">
            {providers.map((p) => (
              <button
                key={p.key}
                onClick={() => setActiveProvider(p.key)}
                className={`px-6 py-2 rounded-lg font-bold text-sm transition-colors ${
                  p.key === (activeProvider || providers[0]?.key)
                    ? "bg-surface text-primary shadow-sm"
                    : "text-on-surface-variant hover:text-primary"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Content: placeholder if not default, bento grid if default */}
      {activeProvider && !isDefaultProvider ? (
        <div className="bg-white rounded-xl border border-outline-variant p-10 text-center text-on-surface-variant">
          <span className="material-symbols-outlined text-4xl mb-2 block">construction</span>
          <p className="font-bold mb-1">{activeMeta?.label}</p>
          <p className="text-sm">
            Adapter <code>{activeProvider}</code> is not connected to backend yet.
          </p>
        </div>
      ) : (
      <div className="grid grid-cols-12 gap-6">
        {/* Main Status Card */}
        <div className="col-span-12 bg-surface-container-lowest border border-outline-variant rounded-xl p-6 shadow-[0_4px_12px_rgba(0,0,0,0.06)]">
          <div className="flex justify-between items-start mb-6">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 bg-primary rounded-xl flex items-center justify-center">
                <span
                  className="material-symbols-outlined text-white"
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  {activeMeta?.icon || "memory"}
                </span>
              </div>
              <div>
                <h3 className="text-title-lg font-title-lg">{activeMeta?.label || "RIC"}</h3>
                <div className="flex items-center gap-2 mt-1">
                  <span
                    className={`flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full ${
                      STATUS_PILL[heroStatus] ?? "bg-surface-container text-on-surface-variant"
                    }`}
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-current" />
                    {STATUS_LABEL[heroStatus] ?? heroStatus}
                  </span>
                  <span className="text-xs text-on-surface-variant">{activeMeta?.desc || ""}</span>
                </div>
              </div>
            </div>

          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8">
            <MetricTile label="CPU Utilization" value={`${heroView.cpuPct}%`} pct={heroView.cpuPct} />
            <MetricTile
              label="Memory Usage"
              value={`${heroView.memGb} GB`}
              pct={heroView.memPct}
            />
            <MetricTile
              label="Latency (E2)"
              value={`${heroView.latencyMs}ms`}
              pct={Math.min(100, heroView.latencyMs * 10)}
            />
          </div>

          <div className="mt-6 flex justify-end items-center gap-3">
            <button
              className="flex items-center gap-2 px-6 py-2.5 border border-outline-variant text-on-surface rounded-lg hover:bg-surface-container transition-colors font-bold text-sm"
              onClick={() => hero && setLogTarget({ domain: "ric", compId: hero.id, compName: hero.name, provider: activeProvider || "oai" })}
            >
              <span className="material-symbols-outlined text-lg">subject</span>
              View Logs
            </button>
            {/* RBAC 2-role: user & admin sama-sama boleh operasi */}
            {(getRole() === "user" || getRole() === "admin") && (
              hero?.host ? (
                <button
                  className={`flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold text-sm shadow-md transition-all ${blockedByBooking ? "bg-outline-variant text-white opacity-50 cursor-not-allowed" : "bg-primary text-white hover:bg-primary-container active:scale-95"}`}
                  onClick={() => { if(blockedByBooking){ alert("Requires active booking — book a session at /reservations"); return; } if(hero) setConsoleTarget({domain:"ric", compId: hero.id, provider: activeProvider || "oai", compName: hero.name}); }}
                  disabled={blockedByBooking}
                  title={blockedByBooking ? "Requires active booking — book a session at /reservations" : "Open terminal"}
                >
                  <span className="material-symbols-outlined text-lg">terminal</span>
                  Console
                </button>
              ) : (
                <span
                  className="text-xs text-on-surface-variant italic px-2 py-1"
                  title="This component has no host configured for console access"
                >
                  No Console Access
                </span>
              )
            )}
          </div>
        </div>

        {consoleTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-slate-900/70 backdrop-blur-sm" onClick={()=>setConsoleTarget(null)}>
            <div className="bg-slate-900 border border-slate-700/60 text-slate-100 rounded-2xl shadow-2xl w-full max-w-5xl max-h-[88vh] flex flex-col overflow-hidden" onClick={(e)=>e.stopPropagation()}>
              <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 bg-slate-950 shrink-0">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center text-primary border border-primary/30">
                    <span className="material-symbols-outlined">terminal</span>
                  </div>
                  <h3 className="font-bold text-sm sm:text-base text-white">Console • FlexRIC RIC</h3>
                  <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">ric/{consoleTarget.provider}</span>
                </div>
                <button onClick={()=>setConsoleTarget(null)} className="w-8 h-8 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center">×</button>
              </div>
              <div className="flex-1 p-3 bg-[#0e1420] overflow-hidden">
                <ConsoleTerminal domain={consoleTarget.domain} componentId={consoleTarget.compId} provider={consoleTarget.provider} host={hero?.host || "ric"} currentUser={currentUser} />
              </div>
            </div>
          </div>
        )}
        {logTarget && (
          <LogsModal
            domain={logTarget.domain}
            compId={logTarget.compId}
            compName={logTarget.compName}
            provider={logTarget.provider}
            onClose={() => setLogTarget(null)}
          />
        )}

        {/* Live Telemetry Event Stream */}
        <div className="col-span-12 bg-surface-container-lowest border border-outline-variant rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)]">
          <div className="p-4 border-b border-outline-variant flex justify-between items-center">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-primary">sensors</span>
              <h3 className="text-title-md font-title-md">Live Telemetry Event Stream</h3>
            </div>
            <div className="text-[10px] font-mono text-on-surface-variant bg-surface-container-low px-2 py-0.5 rounded">
              WEBSOCKET STREAM (/ws/telemetry)
            </div>
          </div>
          <div className="p-4 font-mono text-code-md h-64 overflow-y-auto bg-inverse-surface text-surface-container-low rounded-b-xl">
            <div className="space-y-1">
              {logLines.length === 0 && <p className="opacity-60">No data available.</p>}
              {logLines.map((l) => (
                <p
                  key={l.key}
                  className={
                    l.level === "WARN"
                      ? "text-tertiary-fixed"
                      : l.level === "ERROR"
                      ? "text-error-container"
                      : "opacity-80"
                  }
                >
                  <span className="text-secondary-fixed-dim">[{l.time}]</span> {l.level}: {l.text}
                </p>
              ))}
            </div>
          </div>
        </div>

        {/* All RIC Components — LEFT (col-span-7) */}
        <div className="col-span-12 lg:col-span-7 bg-surface-container-lowest border border-outline-variant rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] overflow-hidden flex flex-col">
          <div className="px-6 py-4 border-b border-outline-variant flex justify-between items-center">
            <h4 className="text-sm font-bold">All RIC Components</h4>
            <span className="text-xs bg-surface-container px-2 py-1 rounded">
              {components.filter((c) => c.status !== "down").length} / {components.length} healthy
            </span>
          </div>
          <div className="overflow-x-auto flex-1">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-surface-container-low text-[11px] uppercase tracking-wider font-bold text-on-surface-variant">
                  <th className="px-6 py-3">Component Name</th>
                  <th className="px-6 py-3">Status</th>
                  <th className="px-6 py-3">Details</th>
                  <th className="px-6 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="text-sm divide-y divide-outline-variant">
                {components.map((c) => (
                  <tr key={c.id} className="hover:bg-surface-container-low">
                    <td className="px-6 py-4 font-medium cursor-pointer" onClick={() => onSelect(c)}>
                      {c.name} <span className="text-on-surface-variant font-normal">({c.kind})</span>
                      {c.reservation && (
                        <span className="ml-1.5 text-xs" title={`Reserved by ${c.reservation.user}`}>
                          🔒
                        </span>
                      )}
                    </td>
                    <td className={`px-6 py-4 text-xs font-bold ${RAN_NODE_TEXT[c.status] ?? "text-on-surface-variant"}`}>
                      ● {STATUS_LABEL[c.status] ?? c.status}
                    </td>
                    <td className="px-6 py-4 text-xs text-on-surface-variant">{c.detail || "-"}</td>
                    <td className="px-6 py-4 text-right">
                      <button
                        className="text-primary hover:underline font-bold text-xs disabled:opacity-50 disabled:no-underline disabled:cursor-not-allowed"
                        onClick={() => handleRestartRow(c.id)}
                        disabled={restartingId === c.id || c.status === "restarting"}
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

        {/* Registered Service Models — RIGHT (col-span-5) */}
        <div className="col-span-12 lg:col-span-5 bg-surface-container-lowest border border-outline-variant rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] flex flex-col">
          <div className="p-4 border-b border-outline-variant">
            <h3 className="text-title-md font-title-md">Registered Service Models</h3>
          </div>
          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-left">
              <thead className="bg-surface-container-low sticky top-0">
                <tr>
                  <th className="px-4 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">Model ID</th>
                  <th className="px-4 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">Version</th>
                  <th className="px-4 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">Nodes</th>
                  <th className="px-4 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30">
                {SERVICE_MODELS.map((m) => (
                  <tr key={m.id}>
                    <td className="px-4 py-4 text-sm font-medium">{m.id}</td>
                    <td className="px-4 py-4 text-xs font-mono">{m.version}</td>
                    <td className="px-4 py-4 text-xs">{m.nodes}</td>
                    <td className="px-4 py-4 text-xs">
                      <span className={m.active ? "text-secondary font-bold" : "text-on-surface-variant"}>
                        {m.active ? "READY" : "INACTIVE"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

      </div>
      )}
    </div>
  );
}

function MetricTile({ label, value, pct }) {
  return (
    <div className="p-4 bg-surface-container-low rounded-xl border border-outline-variant/30">
      <p className="text-xs text-on-surface-variant font-medium mb-1">
        {label.toUpperCase()}
      </p>
      <div className="flex items-end gap-2">
        <span className="text-2xl font-bold">{value}</span>
      </div>
      <div className="w-full bg-outline-variant/30 h-1.5 rounded-full mt-3 overflow-hidden">
        <div className="bg-primary h-full" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
      </div>
    </div>
  );
}
