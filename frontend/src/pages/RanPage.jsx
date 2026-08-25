import React, { useState, useEffect, useMemo } from "react";
import { fetchProviders, fetchComponents, getActiveProvider, activateProvider, deactivateProvider } from "../api.js";
import { getRole } from "../user.js";
import LogsModal from "../components/LogsModal.jsx";
import { usePageHeader } from "../components/PageHeaderContext.jsx";

const STATUS_META = {
  healthy: { label: "Active", dot: "bg-secondary", text: "text-secondary", pulse: true },
  degraded: { label: "Degraded", dot: "bg-tertiary", text: "text-tertiary", pulse: false },
  down: { label: "Critical", dot: "bg-error", text: "text-error", pulse: false },
  restarting: { label: "Restarting", dot: "bg-primary", text: "text-primary", pulse: true },
};

// Label & kelas badge health — dipakai kotak Current Operator (pola CorePage).
const HEALTH_BADGE_LABEL = { healthy: "ONLINE", degraded: "DEGRADED", down: "OFFLINE" };
const HEALTH_BADGE_CLASS = {
  healthy: "bg-secondary-container text-on-secondary-container",
  degraded: "bg-tertiary-container text-on-tertiary-container",
  down: "bg-error-container text-on-error-container",
};

// Status agregat satu domain RAN — logika sama dengan CorePage.jsx:
// satu komponen down -> domain down, ada yang degraded -> degraded,
// selain itu healthy.
function domainHealth(components) {
  if (!components?.length) return "down";
  if (components.some((c) => c.status === "down")) return "down";
  if (components.some((c) => c.status === "degraded")) return "degraded";
  return "healthy";
}

function formatUptime(seconds) {
  if (!seconds || seconds < 0) return "-";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${d}d ${String(h).padStart(2, "0")}h ${String(m).padStart(2, "0")}m`;
}

// Ilustrasi "Coverage Map" -- pengganti foto AI-generated di mockup (yang di-hotlink
// dari URL luar). Ini SVG statis, murni dekoratif, tidak terikat data asli.
function CoverageMapArt() {
  return (
    <svg className="absolute inset-0 w-full h-full" viewBox="0 0 300 200" preserveAspectRatio="xMidYMid slice">
      <rect width="300" height="200" fill="#e9edff" />
      {Array.from({ length: 10 }).map((_, row) =>
        Array.from({ length: 15 }).map((_, col) => (
          <circle key={`${row}-${col}`} cx={col * 20 + 10} cy={row * 20 + 10} r="1.2" fill="#c3c6d6" />
        ))
      )}
      <circle cx="90" cy="70" r="26" fill="#82f9be" opacity="0.35" />
      <circle cx="90" cy="70" r="7" fill="#006c47" />
      <circle cx="190" cy="120" r="34" fill="#b2c5ff" opacity="0.35" />
      <circle cx="190" cy="120" r="7" fill="#003d9b" />
      <circle cx="230" cy="50" r="18" fill="#82f9be" opacity="0.3" />
      <circle cx="230" cy="50" r="5" fill="#006c47" />
      <line x1="90" y1="70" x2="190" y2="120" stroke="#0c56d0" strokeDasharray="3 3" strokeWidth="1" />
      <line x1="190" y1="120" x2="230" y2="50" stroke="#0c56d0" strokeDasharray="3 3" strokeWidth="1" />
    </svg>
  );
}

export default function RanPage({ components, currentUser, onSelect, onRestart }) {
  const [providers, setProviders] = useState([]);
  const [activeProvider, setActiveProvider] = useState(null);
  const [providerComponents, setProviderComponents] = useState(null);
  const [restartingId, setRestartingId] = useState(null);
  const [logTarget, setLogTarget] = useState(null);

  // Provider RAN yang di-set AKTIF lewat backend (tabel active_providers,
  // domain "ran"). Eksklusif per-domain: cuma satu provider atau null.
  // Shape: {provider, username, activated_at} | null
  const [activeActivation, setActiveActivation] = useState(null);
  const [activationBusy, setActivationBusy] = useState(false);

  // Fetch daftar provider dari backend (data-driven, sama pola CorePage.jsx)
  useEffect(() => {
    fetchProviders("ran")
      .then((list) => {
        setProviders(list);
        if (list.length) setActiveProvider(list[0].key);
      })
      .catch(() => setProviders([]));

    // Status aktivasi provider RAN (siapa yang sedang AKTIF secara eksplisit).
    // Backend menyimpan active provider PER-DOMAIN, jadi selalu query domain
    // "ran" — jangan pernah campur dengan status domain core.
    // Gagal diam-diam: fitur ini opsional bagi sisa halaman.
    getActiveProvider("ran").then(setActiveActivation).catch(() => {});
  }, []);

  // Provider pertama = data live dari WebSocket (prop `components`).
  // Provider lain = fetch sekali via REST saat tab diklik.
  const isDefaultProvider = providers[0]?.key === activeProvider;

  useEffect(() => {
    if (!activeProvider || isDefaultProvider) {
      setProviderComponents(null);
      return;
    }
    fetchComponents("ran", activeProvider)
      .then(setProviderComponents)
      .catch(() => setProviderComponents([]));
  }, [activeProvider, isDefaultProvider]);

  const activeMeta = providers.find((p) => p.key === activeProvider);
  const displayedComponents = isDefaultProvider ? components : (providerComponents || []);

  // Current Operator RAN — provider yang benar-benar sedang jalan
  // (healthy/degraded), pola sama dengan CorePage:
  //   • Default provider: health dari WebSocket `components` (real-time).
  //   • Provider lain: health dari providerHealthMap (fetch saat mount);
  //     RanPage tidak memelihara map itu, jadi cukup dari `components`.
  const currentOperator = useMemo(() => {
    if (!providers.length) return null;
    const defaultKey = providers[0].key;
    const allHealth = { [defaultKey]: domainHealth(components) };
    const running =
      providers.find((p) => allHealth[p.key] === "healthy") ||
      providers.find((p) => allHealth[p.key] === "degraded");
    if (!running) return null;
    return { ...running, health: allHealth[running.key] };
  }, [providers, components]);

  // Judul + subtitle halaman dirender sticky TopBar lewat PageHeaderContext
  // (revisi owner t_6c29abe5). Slot right null: operator box ada di body.
  usePageHeader({
    title: "Radio Access Network Monitoring and configure gNodeB instances across distributed sites",
    subtitle: "",
    right: null,
  });

  // "Hero" node = gNB-1, mewakili node gNB utama yang ditonjolkan di card.
  const hero = displayedComponents.find((c) => c.id === "gnb-1") || displayedComponents[0];

  const handleRestartRow = async (id) => {
    setRestartingId(id);
    try {
      await onRestart("ran", id);
    } finally {
      setRestartingId(null);
    }
  };

  // ---- Provider activation state ----
  // RBAC 2-role: user & admin sama-sama operator penuh.
  const isViewer = false;
  // Provider yang sedang aktif secara eksplisit (atau null).
  const activatedKey = activeActivation?.provider || null;
  const activatedLabel = providers.find((p) => p.key === activatedKey)?.label || activatedKey;
  const isActiveTab = activatedKey != null && activatedKey === activeProvider;
  const isBusy = activationBusy;

  // Toggle Activate/Deactivate untuk provider RAN pada tab yang sedang
  // dibuka. `activeProvider` = key tab (match DOMAIN_PROVIDERS["ran"]:
  // "oai" / "srsran"), sama seperti pola CorePage.
  const handleToggleActivation = async () => {
    if (isViewer || !activeProvider) return;
    setActivationBusy(true);
    try {
      if (isActiveTab) {
        await deactivateProvider("ran");
        setActiveActivation(null);
      } else {
        const res = await activateProvider("ran", activeProvider);
        setActiveActivation({
          provider: res.provider,
          username: res.username,
          activated_at: res.activated_at,
        });
      }
    } catch (e) {
      console.error("Provider activation failed", e);
    } finally {
      setActivationBusy(false);
    }
  };

  return (
    <div className="max-w-[1600px] mx-auto">
      {/* Baris atas: provider tabs (kiri) + kotak Current Operator (kanan).
          Judul halaman pindah ke sticky TopBar via usePageHeader (revisi
          owner t_6c29abe5) — body tidak merender judul lokal lagi. */}
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-8">
        {/* Provider Selector Tabs — same card-button style as CorePage */}
        <div className="flex flex-wrap gap-4">
          {providers.map((p) => {
            const active = p.key === activeProvider;
            // Tab yang provider-nya di-set AKTIF dapat badge + border khusus
            const isActiveProvider = p.key === activatedKey;
            return (
              <button
                key={p.key}
                onClick={() => setActiveProvider(p.key)}
                className={`relative flex items-center gap-3 px-6 py-4 rounded-xl border-2 transition-all duration-200 glass-card ${
                  isActiveProvider
                    ? "border-secondary shadow-md"
                    : active
                      ? "border-primary text-primary shadow-md"
                      : "border-transparent text-on-surface-variant hover:bg-surface-container"
                }`}
              >
                <span className="material-symbols-outlined">{p.icon}</span>
                <div className="text-left">
                  <p className="text-xs uppercase tracking-widest font-bold opacity-70">Provider</p>
                  <p className="font-bold flex items-center gap-2">
                    {p.label}
                    {isActiveProvider && (
                      <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-secondary-container text-on-secondary-container animate-pulse">
                        ● ACTIVE
                      </span>
                    )}
                  </p>
                </div>
              </button>
            );
          })}
        </div>

        {/* Current Operator — provider yang BENAR-BENAR sedang jalan
            (bukan sekadar tab yang diklik), bergaya serupa CorePage */}
        <div className="shrink-0 glass-card border border-outline-variant rounded-2xl px-5 py-3 shadow-sm flex items-center gap-3 self-start">
          <span className="material-symbols-outlined text-primary text-xl">
            {currentOperator?.icon || "cloud_off"}
          </span>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Current Operator</p>
            <p className="font-bold text-sm text-on-surface">
              {currentOperator?.label ?? "None"}
            </p>
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
              currentOperator
                ? HEALTH_BADGE_CLASS[currentOperator.health]
                : "bg-surface-container text-on-surface-variant"
            }`}>
              ● {currentOperator ? HEALTH_BADGE_LABEL[currentOperator.health] : "NO ACTIVE PROVIDER"}
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6">
          {/* Main Status Card (Featured) */}
          <div className="col-span-12 lg:col-span-8 bg-white rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant overflow-hidden flex flex-col">
            <div className="p-6 border-b border-outline-variant flex justify-between items-center">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-secondary-container/30 rounded-xl flex items-center justify-center text-secondary">
                  <span className="material-symbols-outlined text-[32px]">satellite_alt</span>
                </div>
                <div>
                  <h3 className="text-title-lg font-bold">{hero?.name || "-"}</h3>
                  <p className="text-xs text-on-surface-variant">
                    {hero?.kind} • Host: {hero?.host || "-"}
                  </p>
                </div>
              </div>
              <span
                className={`flex items-center gap-1.5 px-3 py-1 text-label-sm rounded-full ${
                  STATUS_META[hero?.status]?.text ?? "text-on-surface-variant"
                } bg-secondary-container/20`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${STATUS_META[hero?.status]?.dot ?? "bg-outline"}`} />
                {STATUS_META[hero?.status]?.label ?? hero?.status}
              </span>
            </div>

            <div className="p-6 grid grid-cols-1 sm:grid-cols-3 gap-x-4 gap-y-6">
              <div className="space-y-6">
                <div className="h-12 flex flex-col justify-center gap-2">
                  <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Implementation</p>
                  <p className="text-on-surface text-body-md font-bold">{hero?.kind || activeMeta?.label || "gNB"}</p>
                </div>
                <div className="h-12 flex flex-col justify-center gap-2">
                  <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Architecture</p>
                  <p className="text-on-surface text-body-md font-bold">CU/DU Split</p>
                </div>
                <div className="h-12 flex flex-col justify-center gap-2">
                  <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Interface</p>
                  <p className="text-primary text-body-md font-bold">F1-C / F1-U</p>
                </div>
              </div>
              <div className="space-y-6">
                <div className="h-12 flex flex-col justify-center gap-2">
                  <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Latency</p>
                  <p className="text-secondary text-body-md font-bold">{hero?.latency_ms ?? "-"}ms</p>
                </div>
                <div className="h-12 flex flex-col justify-center gap-2">
                  <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Uptime</p>
                  <p className="text-on-surface text-body-md font-bold">{formatUptime(hero?.uptime_seconds)}</p>
                </div>
                <div className="h-12 flex flex-col justify-center gap-2">
                  <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Active UEs</p>
                  <p className="text-on-surface text-body-md font-bold">{hero?.active_ues ?? 0}</p>
                </div>
              </div>
              <div className="space-y-6">
                <div className="h-12 flex flex-col justify-center gap-2">
                  <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">CPU</p>
                  <div className="flex items-center gap-3">
                    <div className="flex-1 h-1.5 bg-surface-container rounded-full overflow-hidden">
                      <div className="h-full bg-primary" style={{ width: `${hero?.cpu_pct ?? 0}%` }} />
                    </div>
                    <span className="text-on-surface text-body-md font-bold">{hero?.cpu_pct ?? 0}%</span>
                  </div>
                </div>
                <div className="h-12 flex flex-col justify-center gap-2">
                  <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Memory</p>
                  <div className="flex items-center gap-3">
                    <div className="flex-1 h-1.5 bg-surface-container rounded-full overflow-hidden">
                      <div className="h-full bg-tertiary" style={{ width: `${hero?.mem_pct ?? 0}%` }} />
                    </div>
                    <span className="text-on-surface text-body-md font-bold">{hero?.mem_gb ?? 0}GB</span>
                  </div>
                </div>
                <div className="h-12 flex flex-col justify-center gap-2">
                  <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Status detail</p>
                  <p className="text-on-surface text-body-md font-bold">{hero?.detail || "-"}</p>
                </div>
              </div>
            </div>

            <div className="mt-auto p-6 bg-surface-container-low flex justify-between items-center">
              <div className="flex -space-x-2">
                {["CU", "DU", "RU"].map((label) => (
                  <div
                    key={label}
                    className="w-8 h-8 rounded-full border-2 border-white bg-surface-dim flex items-center justify-center text-[10px] font-bold"
                    title={label === "RU" ? "RU not monitored by backend yet" : undefined}
                  >
                    {label}
                  </div>
                ))}
              </div>
              <div className="flex gap-3">
                {/* 1) Console — dipindah ke kiri */}
                {/* RBAC 2-role: user & admin sama-sama operator */}
                {(getRole() === "user" || getRole() === "admin") && (
                  <button
                    className="px-6 py-2.5 bg-primary text-white font-bold rounded-lg shadow-md hover:brightness-110 active:scale-95 transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    onClick={() => hero && onSelect(hero)}
                    disabled={!hero?.host}
                  >
                    <span className="material-symbols-outlined text-lg">terminal</span>
                    Console
                  </button>
                )}

                {/* 2) View Logs */}
                <button
                  className="px-6 py-2.5 border border-outline-variant text-on-surface font-bold text-label-lg rounded-lg hover:bg-surface-container-highest transition-colors flex items-center gap-2"
                  onClick={() => hero && setLogTarget({ domain: "ran", compId: hero.id, compName: hero.name })}
                >
                  <span className="material-symbols-outlined text-lg">subject</span>
                  View Logs
                </button>

                {/* 3) Activate / Deactivate provider tab yang sedang dibuka.
                    Eksklusif antar provider RAN (status per-domain dari
                    getActiveProvider("ran")): kalau provider LAIN sedang aktif,
                    tombol disabled. Viewer: lihat status tapi tombol disabled. */}
                <button
                  onClick={handleToggleActivation}
                  disabled={isBusy || isViewer || (activatedKey != null && !isActiveTab)}
                  title={
                    isViewer
                      ? "Viewers cannot activate providers"
                      : activatedKey != null && !isActiveTab
                        ? `Provider ${activatedLabel} sedang aktif — nonaktifkan dulu`
                        : ""
                  }
                  className={
                    isActiveTab
                      ? `px-6 py-2.5 bg-error text-on-error font-bold rounded-lg shadow-md transition-all flex items-center gap-2 ${isViewer || isBusy ? "opacity-50 cursor-not-allowed" : "hover:brightness-110 active:scale-95"}`
                      : `px-6 py-2.5 border border-outline-variant font-bold rounded-lg transition-all flex items-center gap-2 ${
                          isViewer || isBusy || activatedKey != null
                            ? "text-on-surface-variant opacity-50 cursor-not-allowed"
                            : "text-secondary hover:bg-surface-container-low hover:border-secondary active:scale-95"
                        }`
                  }
                >
                  <span className="material-symbols-outlined text-lg">
                    {isActiveTab ? "power_settings_new" : activatedKey != null && !isActiveTab ? "block" : "power_settings_new"}
                  </span>
                  {isBusy ? "..." : isActiveTab ? "Deactivate" : "Activate"}
                </button>
              </div>
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

          {/* Coverage Map Card */}
          <div className="col-span-12 lg:col-span-4 bg-white rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant p-6 flex flex-col">
            <h3 className="text-title-md font-bold mb-4">Coverage Map</h3>
            <div className="flex-1 rounded-lg bg-surface-container overflow-hidden relative min-h-[240px]">
              <CoverageMapArt />
              <div className="absolute bottom-3 left-3 bg-white/90 backdrop-blur p-2 rounded-lg text-[10px] font-bold shadow-sm">
                <p className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-secondary" />
                  Optimal Coverage
                </p>
              </div>
            </div>
            <div className="mt-6 space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-body-md text-on-surface-variant">FR1 (Sub-6GHz)</span>
                <span className="px-2 py-0.5 bg-secondary-container/30 text-secondary text-[10px] font-bold rounded">ENABLED</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-body-md text-on-surface-variant">FR2 (mmWave)</span>
                <span className="px-2 py-0.5 bg-surface-container text-outline text-[10px] font-bold rounded">DISABLED</span>
              </div>
            </div>
          </div>

          {/* Node List Table */}
          <div className="col-span-12 bg-white rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant overflow-hidden">
            <div className="p-6 border-b border-outline-variant flex justify-between items-center">
              <h3 className="text-title-md font-bold">Deployment Inventory</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead className="bg-surface-container-low">
                  <tr>
                    <th className="px-6 py-3 text-label-sm font-bold text-outline uppercase tracking-widest">Node Instance</th>
                    <th className="px-6 py-3 text-label-sm font-bold text-outline uppercase tracking-widest">Type</th>
                    <th className="px-6 py-3 text-label-sm font-bold text-outline uppercase tracking-widest">IP Address</th>
                    <th className="px-6 py-3 text-label-sm font-bold text-outline uppercase tracking-widest">Load</th>
                    <th className="px-6 py-3 text-label-sm font-bold text-outline uppercase tracking-widest">Status</th>
                    <th className="px-6 py-3 text-label-sm font-bold text-outline uppercase tracking-widest">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant">
                  {displayedComponents.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-6 py-6 text-center text-on-surface-variant text-xs font-mono">
                        No component data available.
                      </td>
                    </tr>
                  )}
                  {displayedComponents.map((c) => {
                    const meta = STATUS_META[c.status] ?? { label: c.status, dot: "bg-outline", text: "text-on-surface-variant" };
                    const isDown = c.status === "down";
                    return (
                      <tr key={c.id} className="hover:bg-surface-container-lowest transition-colors h-14">
                        <td className="px-6 py-4 cursor-pointer" onClick={() => onSelect(c)}>
                          <div className="flex items-center gap-3">
                            <div
                              className={`w-8 h-8 rounded flex items-center justify-center ${
                                isDown ? "bg-error-container/10 text-error" : "bg-primary-container/10 text-primary"
                              }`}
                            >
                              <span className="material-symbols-outlined text-[18px]">
                                {isDown ? "report_problem" : "router"}
                              </span>
                            </div>
                            <span className="font-bold text-body-md">{c.name}</span>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-body-md">{c.kind}</td>
                        <td className="px-6 py-4 font-mono text-xs">{c.host || "-"}</td>
                        <td className="px-6 py-4">
                          <div className="w-24 h-1 bg-surface-container rounded-full overflow-hidden">
                            <div
                              className={`h-full ${isDown ? "bg-error" : "bg-secondary"}`}
                              style={{ width: `${c.cpu_pct ?? 0}%` }}
                            />
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <span className={`flex items-center gap-1.5 text-label-sm font-bold ${meta.text}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${meta.dot} ${meta.pulse ? "animate-pulse" : ""}`} />
                            {meta.label}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <button
                            className="text-primary hover:underline font-bold text-label-sm disabled:opacity-50 disabled:no-underline disabled:cursor-not-allowed"
                            onClick={() => handleRestartRow(c.id)}
                            disabled={restartingId === c.id || c.status === "restarting"}
                          >
                            {restartingId === c.id || c.status === "restarting"
                              ? "..."
                              : isDown
                              ? "Recover"
                              : "Manage"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
    </div>
  );
}