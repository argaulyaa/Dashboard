import React, { useState, useEffect, useMemo } from "react";
import { fetchProviders, fetchComponents, getActiveProvider, activateProvider, deactivateProvider, providerLabel, fetchActiveBooking } from "../api.js";
import { getRole } from "../user.js";
import ConsoleTerminal from "../components/ConsoleTerminal.jsx";
import LogsModal from "../components/LogsModal.jsx";
import { usePageHeader } from "../components/PageHeaderContext.jsx";

const STATUS_META = {
  healthy: { label: "Active", dot: "bg-secondary", text: "text-secondary", pulse: true },
  degraded: { label: "Degraded", dot: "bg-tertiary", text: "text-tertiary", pulse: false },
  down: { label: "Inactive", dot: "bg-error", text: "text-error", pulse: false },
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

// Ilustrasi "Coverage Map" -- ILLUSTRATIVE ONLY, not from testbed.
// Hidden for ALL providers (only real metrics shown). SVG statis, murni dekoratif, tidak terikat data asli.
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

export default function RanPage({ components, currentUser, onSelect, onRestart, telemetryMeta }) {
  const [providers, setProviders] = useState([]);
  const [activeProvider, setActiveProvider] = useState(null);
  const [providerComponents, setProviderComponents] = useState(null);
  const [restartingId, setRestartingId] = useState(null);
  const [logTarget, setLogTarget] = useState(null);
  const [consoleTarget, setConsoleTarget] = useState(null);

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

  // WebSocket telemetry (prop `components`) men-stream provider yang AKTIF
  // di DB (meta.active.ran dari backend — tabel active_providers), BUKAN
  // selalu provider pertama di registry. Fallback ke providers[0] kalau
  // belum ada provider yang diaktifkan — ini meniru persis logika backend
  // (main.py::telemetry_ws: entry = active_map.get(domain) atau
  // next(iter(providers.values()))). Tanpa fallback ke meta.active ini,
  // tab OAI bisa salah menampilkan data srsRAN (atau sebaliknya) kalau
  // provider aktif di DB bukan providers[0] — komponen tidak pernah
  // ter-"bind" ke tab yang benar-benar diklik.
  const streamedProviderKey = telemetryMeta?.active?.ran || providers[0]?.key;
  const isDefaultProvider = streamedProviderKey === activeProvider;

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

  // ---- F3: status aktivasi real-time dari meta WS (payload v2) ----
  // meta.active.ran = provider RAN yang di-set aktif; meta.active.core =
  // core yang sedang aktif (dipakai gate Activate + label "Core aktif").
  const wsActiveRan = telemetryMeta?.active?.ran ?? undefined;
  useEffect(() => {
    if (wsActiveRan === undefined) return;
    setActiveActivation(wsActiveRan ? { provider: wsActiveRan } : null);
  }, [wsActiveRan]);

  // ---- Health REAL per provider (independen dari bookkeeping DB) ----
  // Bug yang diperbaiki (3 Nov 2026): badge ACTIVE/Current Operator/tombol
  // Activate-Deactivate sebelumnya 100% ikut tabel active_providers di DB —
  // yang CUMA berubah lewat tombol dashboard. Kalau radio di-switch manual
  // via SSH (operator langsung di server, di luar dashboard), DB jadi basi
  // dan UI menampilkan provider yang SALAH sebagai aktif.
  // Fix: poll health SEMUA provider RAN tiap 5s (independen dari tab yang
  // sedang dibuka), lalu badge/tombol/Current Operator pakai HEALTH NYATA
  // sebagai sumber kebenaran utama — DB cuma dipakai sebagai fallback kalau
  // tidak ada satupun provider yang sehat (mis. keduanya mati).
  const [providerHealthMap, setProviderHealthMap] = useState({});
  useEffect(() => {
    if (!providers.length) return;
    let cancelled = false;
    const pollAll = async () => {
      const entries = await Promise.all(
        providers.map(async (p) => {
          // Provider yang sedang di-stream WS pakai `components` langsung
          // (live, tanpa REST tambahan) — provider lain di-fetch REST.
          if (p.key === streamedProviderKey) {
            return [p.key, domainHealth(components)];
          }
          try {
            const comps = await fetchComponents("ran", p.key);
            return [p.key, domainHealth(comps)];
          } catch {
            return [p.key, "down"];
          }
        })
      );
      if (!cancelled) setProviderHealthMap(Object.fromEntries(entries));
    };
    pollAll();
    const id = setInterval(pollAll, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, [providers, streamedProviderKey, components]);

  // Provider yang REAL-TIME sehat (gNB benar-benar jalan) — null kalau tidak
  // ada satupun yang healthy/degraded (semua down).
  const realActiveProviderKey = useMemo(() => {
    const healthyKey = providers.find((p) => {
      const h = providerHealthMap[p.key];
      return h === "healthy" || h === "degraded";
    })?.key;
    return healthyKey ?? null;
  }, [providers, providerHealthMap]);

  const activeCoreKey = telemetryMeta?.active?.core ?? null; // null = belum ada data WS
  const hasCoreData = telemetryMeta?.active != null;

  // Reservation gate for Activate: requires active booking (admin bypass)
  const [hasBooking, setHasBooking] = useState(null);
  const isAdminRole = useMemo(() => { try { return getRole() === "admin"; } catch { return false; } }, []);
  useEffect(() => {
    const check = async () => {
      if (isAdminRole) { setHasBooking(true); return; }
      try { const a = await fetchActiveBooking(); setHasBooking(!!a); } catch { setHasBooking(false); }
    };
    check();
    const id = setInterval(check, 8000);
    return () => clearInterval(id);
  }, [isAdminRole]);
  const blockedByBooking = !isAdminRole && hasBooking === false;

  // ---- Provider activation state ----
  // RBAC 2-role: user & admin sama-sama operator penuh.
  const isViewer = false;
  // Provider yang "aktif": prioritas HEALTH NYATA (realActiveProviderKey) —
  // fallback ke status DB (activeActivation) HANYA kalau tidak ada provider
  // yang benar-benar hidup (mis. keduanya down, atau baru switch manual
  // lewat SSH belum sempat ke-detect poll pertama).
  const activatedKey = realActiveProviderKey ?? activeActivation?.provider ?? null;
  const activatedLabel = providers.find((p) => p.key === activatedKey)?.label || activatedKey;
  // Fallback kayak Core: Active/Critical (gNB ada) => Deactivate, Offline (no gNB) => Activate
  const isActiveTab = activatedKey != null ? activatedKey === activeProvider : displayedComponents.length > 0;
  const isBusy = activationBusy;

  // Current Operator RAN — F3: sumber kebenaran = status AKTIVASI eksplisit
  // (selaras CorePage), health sebagai sekunder.
  const currentOperator = useMemo(() => {
    if (!providers.length) return null;
    if (!activatedKey) return null;
    const meta = providers.find((p) => p.key === activatedKey);
    if (!meta) return { key: activatedKey, label: activatedKey, icon: "settings_input_antenna", health: "down" };
    return { ...meta, health: domainHealth(displayedComponents) };
  }, [providers, activatedKey, displayedComponents]);

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

  // Toggle Activate/Deactivate untuk provider RAN pada tab yang sedang
  // dibuka. `activeProvider` = key tab (match DOMAIN_PROVIDERS["ran"]:
  // "oai" / "srsran"), sama seperti pola CorePage.
  // F3 gate: tanpa core aktif, Activate RAN ditolak di UI (server B1/Fase-3
  // akan jadi pengaman kedua saat akting RAN direalisasikan).
  const handleToggleActivation = async () => {
    if (isViewer || !activeProvider) return;
    if (blockedByBooking) { alert("Requires active booking — book a session at /reservations"); return; }
    if (!isActiveTab && !activatedKey && hasCoreData && !activeCoreKey) {
      alert("Aktifkan Core dulu di halaman Core sebelum mengaktifkan RAN.");
      return;
    }
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
      const reason = e?.payload?.message || e?.message;
      if (e?.payload?.reason === "provider_active") {
        getActiveProvider("ran").then(setActiveActivation).catch(() => {});
      }
      if (reason) alert(reason);
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

        {/* Current Operator — minimal: label + provider name only (no health/dot/badge) */}
        <div className="shrink-0 glass-card border border-outline-variant rounded-2xl px-5 py-3 shadow-sm flex items-center gap-3 self-start">
          <span className="material-symbols-outlined text-primary text-xl">
            {currentOperator?.icon || "cloud"}
          </span>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Current Operator</p>
            <p className="font-bold text-sm text-on-surface">
              {currentOperator?.label ?? "None"}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6">
          {/* Main Status Card (Featured) — full-width for all providers, only real testbed data (srsran cleanup same as oai 38145cc) */}
          <div className={`col-span-12 bg-white rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant overflow-hidden flex flex-col`}>
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

            {/* Hero metrics: ONLY real testbed data for ALL providers (38145cc extended to srsran) — Architecture CU/DU, Interface F1-C/U, Throughput mock removed */}
            <div className="p-6 grid grid-cols-1 sm:grid-cols-3 gap-x-4 gap-y-6">
                <div className="space-y-6">
                  <div className="h-12 flex flex-col justify-center gap-2">
                    <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Implementation</p>
                    <p className="text-on-surface text-body-md font-bold">{hero?.kind || activeMeta?.label || "gNB"}</p>
                  </div>
                  <div className="h-12 flex flex-col justify-center gap-2">
                    <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Latency</p>
                    <p className="text-secondary text-body-md font-bold">{hero?.latency_ms ? `${hero.latency_ms}ms` : "0ms (no data)"}</p>
                  </div>
                  <div className="h-12 flex flex-col justify-center gap-2">
                    <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Uptime</p>
                    <p className="text-on-surface text-body-md font-bold">{formatUptime(hero?.uptime_seconds)}</p>
                  </div>
                </div>
                <div className="space-y-6">
                  <div className="h-12 flex flex-col justify-center gap-2">
                    <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Active UEs</p>
                    <p className="text-on-surface text-body-md font-bold">{hero?.active_ues ?? 0}</p>
                  </div>
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
                </div>
                <div className="space-y-6">
                  <div className="h-12 flex flex-col justify-center gap-2">
                    <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Status detail</p>
                    <p className="text-on-surface text-body-md font-bold">{hero?.detail || "-"}</p>
                  </div>
                  <div className="h-12 flex flex-col justify-center gap-2">
                    <p className="text-on-surface-variant text-xs font-bold uppercase tracking-wider">Host/IP</p>
                    <p className="text-on-surface text-body-md font-bold font-mono text-sm">{hero?.host || "-"}</p>
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
                    className={`px-6 py-2.5 font-bold rounded-lg shadow-md transition-all flex items-center gap-2 ${blockedByBooking || !hero?.host ? "bg-surface-variant text-on-surface-variant opacity-50 cursor-not-allowed" : "bg-primary text-white hover:brightness-110 active:scale-95"}`}
                    onClick={() => { if(blockedByBooking){ alert("Requires active booking — book a session at /reservations"); return; } if(hero) setConsoleTarget({domain:"ran", compId: hero.id || hero.name || "gnb", provider: activeProvider, compName: hero.name}); }}
                    disabled={blockedByBooking || !hero?.host}
                    title={blockedByBooking ? "Requires active booking — book a session at /reservations" : ""}
                  >
                    <span className="material-symbols-outlined text-lg">terminal</span>
                    Console
                  </button>
                )}

                {/* 2) View Logs */}
                <button
                  className="px-6 py-2.5 border border-outline-variant text-on-surface font-bold text-label-lg rounded-lg hover:bg-surface-container-highest transition-colors flex items-center gap-2"
                  onClick={() => hero && setLogTarget({ domain: "ran", compId: hero.id || hero.name || "gnb", compName: hero.name, provider: activeProvider })}
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
                  disabled={isBusy || isViewer || (activatedKey != null && !isActiveTab) || (!activatedKey && hasCoreData && !activeCoreKey) || blockedByBooking}
                  title={
                    blockedByBooking
                      ? "Requires active booking — book a session at /reservations"
                      : isViewer
                      ? "Viewers cannot activate providers"
                      : activatedKey != null && !isActiveTab
                        ? `Provider ${activatedLabel} sedang aktif — nonaktifkan dulu`
                        : !activatedKey && hasCoreData && !activeCoreKey
                          ? "Aktifkan Core dulu di halaman Core"
                          : ""
                  }
                  className={
                    isActiveTab
                      ? `px-6 py-2.5 font-bold rounded-lg shadow-md transition-all flex items-center gap-2 ${isViewer || isBusy || blockedByBooking ? "bg-surface-variant text-on-surface-variant opacity-50 cursor-not-allowed" : "bg-error text-on-error hover:brightness-110 active:scale-95"}`
                      : `px-6 py-2.5 border border-outline-variant font-bold rounded-lg transition-all flex items-center gap-2 ${
                          isViewer || isBusy || blockedByBooking || activatedKey != null
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

          {consoleTarget && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/70 backdrop-blur-sm" onClick={()=>setConsoleTarget(null)}>
              <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-6xl max-h-[85vh] flex flex-col overflow-hidden" onClick={e=>e.stopPropagation()}>
                <div className="px-4 py-3 border-b border-slate-800 flex justify-between items-center bg-slate-950">
                  <h3 className="font-bold text-white flex items-center gap-2"><span className="material-symbols-outlined text-primary">terminal</span> Console • {consoleTarget.compName || "nr-softmodem"} <span className="text-[11px] bg-slate-800 px-2 py-0.5 rounded text-slate-400">{consoleTarget.provider}</span></h3>
                  <button onClick={()=>setConsoleTarget(null)} className="p-2 hover:bg-slate-800 rounded-lg"><span className="material-symbols-outlined text-slate-400">close</span></button>
                </div>
                <div className="flex-1 p-2 bg-black min-h-[480px]">
                  <ConsoleTerminal domain={consoleTarget.domain} compId={consoleTarget.compId} provider={consoleTarget.provider} currentUser={currentUser} host="10.91.2.152" onClose={()=>setConsoleTarget(null)} />
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

          {/* Coverage Map — ILLUSTRATIVE ONLY, hidden for all providers (only real metrics shown in hero/table). Keep component for future illustrative use. */}
          {false && activeProvider !== "oai" && (
            <div className="col-span-12 lg:col-span-4 bg-white rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-outline-variant p-6 flex flex-col">
              <h3 className="text-title-md font-bold mb-4">Coverage Map <span className="text-[10px] font-normal text-outline">(illustrative)</span></h3>
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
          )}

          {/* Deployment Inventory removed per request — RAN page shows only hero + provider tabs; do not re-add table */}
        </div>
    </div>
  );
}