import React, { useMemo, useState, useEffect } from "react";
import { fetchProviders, fetchComponents, getActiveProvider, activateProvider, deactivateProvider, providerLabel, fetchActiveBooking } from "../api.js";
import { getRole } from "../user.js";
import LogsModal from "../components/LogsModal.jsx";
import CoreRanConnectBar from "../components/CoreRanConnectBar.jsx";
import { usePageHeader } from "../components/PageHeaderContext.jsx";

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

// Strip raw ss ESTAB IP:port noise from Core detail (e.g. "ESTAB 0 0 10.91.2.152:37713 ..." / "%enp1s0")
function cleanCoreDetail(detail) {
  if (!detail || typeof detail !== "string") return detail || "-";
  if (!detail.includes("ESTAB") && !detail.includes("%enp")) return detail;
  const parts = detail.split(" • ").filter((seg) => !seg.includes("ESTAB") && !seg.includes("%enp"));
  let cleaned = parts.join(" • ");
  cleaned = cleaned.replace(/ESTAB[^•|]*/g, "").replace(/\|\s*/g, " • ").replace(/•\s*•/g, "•").trim();
  cleaned = cleaned.replace(/^\s*•\s*|\s*•\s*$/g, "").trim();
  return cleaned || detail.split(" • ").filter((seg) => !seg.includes("ESTAB")).join(" • ").trim() || "-";
}

export default function CorePage({ components, currentUser, onSelect, onRestart, telemetryMeta }) {
  // Daftar provider datang dari backend (GET /api/core/providers), bukan
  // ditulis manual di sini. Kalau backend nambah provider baru, tab baru
  // otomatis muncul tanpa file ini disentuh lagi.
  const [providers, setProviders] = useState([]);
  const [activeProvider, setActiveProvider] = useState(null);
  const [providerComponents, setProviderComponents] = useState(null);
  const [restartingId, setRestartingId] = useState(null);
  const [logTarget, setLogTarget] = useState(null);

  // Provider core yang di-set AKTIF lewat backend (tabel active_providers).
  // Eksklusif: cuma ada satu row global, jadi nilainya satu provider atau null.
  // Shape: {provider, username, activated_at} | null
  const [activeActivation, setActiveActivation] = useState(null);
  const [activationBusy, setActivationBusy] = useState(false);

  // Health semua non-default provider — di-fetch sekali saat providers pertama kali load.
  // Default provider sudah punya data live dari WebSocket (`components` prop).
  const [providerHealthMap, setProviderHealthMap] = useState({});

  // Reservation gate for Activate (power_settings_new): requires active booking
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

  useEffect(() => {
    fetchProviders("core")
      .then((list) => {
        setProviders(list);
        if (list.length) setActiveProvider(list[0].key);

        // Fetch health semua provider non-default di background
        list.slice(1).forEach(async (p) => {
          try {
            const comps = await fetchComponents("core", p.key);
            setProviderHealthMap((prev) => ({ ...prev, [p.key]: domainHealth(comps) }));
          } catch {
            setProviderHealthMap((prev) => ({ ...prev, [p.key]: "down" }));
          }
        });
      })
      .catch(() => setProviders([]));

    // Status aktivasi provider (siapa yang sedang AKTIF secara eksplisit).
    // Gagal diam-diam: fitur ini opsional bagi sisa halaman.
    getActiveProvider("core").then(setActiveActivation).catch(() => {});
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

  // ---- F2: status aktivasi real-time dari meta WS (payload v2) ----
  // meta.active.core = provider yang di-set aktif (bookkeeping DB backend).
  // Sumber kebenaran utama = WS; REST getActiveProvider cuma fallback awal.
  const wsActiveCore = telemetryMeta?.active?.core ?? undefined; // undefined = belum ada data WS
  useEffect(() => {
    if (wsActiveCore === undefined) return; // WS belum hidup -> biarkan hasil REST
    setActiveActivation(
      wsActiveCore ? { provider: wsActiveCore } : null
    );
  }, [wsActiveCore]);

  // Alur eksklusif terpandu: klik Activate saat provider lain aktif ->
  // dialog konfirmasi "matikan X dulu, lalu nyalakan Y?" (deactivate lalu
  // activate berurutan). Kalau kalah race antar-user -> 409 dari server,
  // refetch status + tampilkan pesan dari payload error.
  const [switchPrompt, setSwitchPrompt] = useState(null); // {fromLabel, toKey}

  const handleToggleActivation = async () => {
    if (isViewer || !activeProvider) return;
    if (blockedByBooking) { alert("Requires active booking — book a session at /reservations"); return; }
    if (activatedKey != null && !isActiveTab) {
      // Provider lain sedang aktif -> minta konfirmasi switch (server akan
      // menolak langsung dengan 409 kalau kita paksa, jadi alurnya terpandu).
      setSwitchPrompt({
        fromLabel: activatedLabel || activatedKey,
        toKey: activeProvider,
      });
      return;
    }
    setActivationBusy(true);
    try {
      if (isActiveTab) {
        await deactivateProvider("core");
        setActiveActivation(null);
      } else {
        const res = await activateProvider("core", activeProvider);
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
        // Race antar user: state lokal basi -> sinkron ulang dari server
        getActiveProvider("core").then(setActiveActivation).catch(() => {});
      }
      if (reason) alert(reason);
    } finally {
      setActivationBusy(false);
    }
  };

  const confirmSwitchProvider = async () => {
    if (!switchPrompt) return;
    const toKey = switchPrompt.toKey;
    setSwitchPrompt(null);
    setActivationBusy(true);
    try {
      await deactivateProvider("core");
      await activateProvider("core", toKey);
      setActiveActivation({ provider: toKey });
    } catch (e) {
      console.error("Provider switch failed", e);
      const reason = e?.payload?.message || e?.message;
      if (e?.payload?.reason === "provider_active") {
        getActiveProvider("core").then(setActiveActivation).catch(() => {});
      }
      if (reason) alert(reason);
    } finally {
      setActivationBusy(false);
    }
  };

  const activeMeta = providers.find((p) => p.key === activeProvider);
  const _rawComponents = isDefaultProvider ? components : (providerComponents || []);
  // Sanitize Core detail: strip raw ss ESTAB IP:port noise (keep host/cpu/mem untouched)
  const displayedComponents = useMemo(() => _rawComponents.map((c) => ({ ...c, detail: cleanCoreDetail(c.detail) })), [_rawComponents]);

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

  // ---- Provider activation state ----
  // RBAC 2-role: user & admin sama-sama operator penuh.
  const isViewer = false;
  // Provider yang sedang aktif secara eksplisit (atau null).
  const activatedKey = activeActivation?.provider || null;
  const activatedLabel = providers.find((p) => p.key === activatedKey)?.label || activatedKey;
  // SYNC FIX: tombol Activate/Deactivate sinkron dengan status ONLINE/OFFLINE (health), bukan cuma active_providers
  // online = healthy/degraded dari pod K8s; kalau belum ada yang di-activate (null), ikut health biar ONLINE→Deactivate
  const _healthForButton = (()=>{ try{return domainHealth(displayedComponents);}catch{return "down"} })();
  const _isOnlineForButton = _healthForButton !== "down";
  const isActiveTab = activatedKey != null ? (activatedKey === activeProvider) : _isOnlineForButton;
  const isBusy = activationBusy;

  // Current Operator — F2: sumber kebenaran = status AKTIVASI eksplisit
  // (siapa yang SEHARUSNYA jalan), bukan inferensi health yang bisa salah
  // kalau dua provider sehat bersamaan. Health tampil sebagai baris kedua
  // ("LIVE") — health di sini milik provider yang sedang aktif saja.
  const currentOperator = useMemo(() => {
    if (!providers.length) return null;
    if (!activatedKey) return null;
    const meta = providers.find((p) => p.key === activatedKey);
    if (!meta) return { key: activatedKey, label: activatedKey, icon: "cloud", health: "down" };
    return { ...meta, health: domainHealth(displayedComponents) };
  }, [providers, activatedKey, displayedComponents]);

  const activeCount = displayedComponents.filter((c) => c.status !== "down").length;

  const handleRestartRow = async (id) => {
    setRestartingId(id);
    try {
      await onRestart("core", id);
    } finally {
      setRestartingId(null);
    }
  };

  // Judul + subtitle halaman dirender sticky TopBar lewat PageHeaderContext
  // (revisi owner t_6c29abe5) — body tidak merender judul lokal lagi.
  // Slot right sengaja null: Current Operator ada di body sejajar tabs.
  usePageHeader({
    title: "Core Network Management",
    subtitle: "Configure and monitor 5G Core Network functions across multiple providers.",
    right: null,
  });

  return (
    <div className="max-w-[1400px] mx-auto">
      <CoreRanConnectBar />
      {/* Baris atas: provider tabs (kiri) + kotak Current Operator (kanan).
          Revisi owner t_6c29abe5: judul halaman pindah ke sticky TopBar
          (via usePageHeader), kotak operator pindah ke sini sejajar tabs. */}
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-8">
        {/* Provider Selector Tabs -- dirender dari data backend, jumlah tab
            mengikuti berapa provider yang benar-benar terdaftar */}
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
            {/* 1) Console — dipindah ke kiri */}
            {/* RBAC 2-role: user & admin sama-sama operator */}
            {(getRole() === "user" || getRole() === "admin") && (
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

            {/* 2) View Logs */}
            <button
              className="px-6 py-2.5 border border-outline-variant text-on-surface font-bold rounded-lg hover:bg-surface-container-low transition-colors flex items-center gap-2"
              onClick={() => hero && setLogTarget({ domain: "core", compId: hero.id, compName: hero.name, provider: activeProvider })}
            >
              <span className="material-symbols-outlined text-lg">subject</span>
              View Logs
            </button>

            {/* 3) Activate / Deactivate provider tab yang sedang dibuka.
                Eksklusif: kalau provider LAIN sedang aktif, tombol disabled.
                Viewer: lihat status tapi tombol disabled. */}
            <button
              onClick={handleToggleActivation}
              disabled={isBusy || isViewer || (activatedKey != null && !isActiveTab) || blockedByBooking}
              title={
                blockedByBooking
                  ? "Requires active booking — book a session at /reservations"
                  : isViewer
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

        {logTarget && (
          <LogsModal
            domain={logTarget.domain}
            compId={logTarget.compId}
            compName={logTarget.compName}
            provider={logTarget.provider}
            onClose={() => setLogTarget(null)}
          />
        )}

        {/* Dialog konfirmasi switch eksklusif (F2): matikan provider aktif
            dulu, baru nyalakan yang diminta. Server-side 409 (B1) tetap
            jadi pengaman kalau ada race antar user. */}
        {switchPrompt && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="glass-card border border-outline-variant rounded-2xl p-6 max-w-md w-[92%] shadow-xl">
              <h4 className="font-bold text-title-md mb-2">Ganti Core Provider?</h4>
              <p className="text-sm text-on-surface-variant mb-6">
                «{switchPrompt.fromLabel}» sedang aktif. Matikan dulu, lalu
                nyalakan «{providerLabel(switchPrompt.toKey)}»?
              </p>
              <div className="flex justify-end gap-3">
                <button
                  className="px-4 py-2 rounded-lg border border-outline-variant font-bold text-sm hover:bg-surface-container-low"
                  onClick={() => setSwitchPrompt(null)}
                >
                  Batal
                </button>
                <button
                  className="px-4 py-2 rounded-lg bg-error text-on-error font-bold text-sm shadow-md hover:brightness-110 disabled:opacity-50"
                  onClick={confirmSwitchProvider}
                  disabled={activationBusy}
                >
                  {activationBusy ? "Memproses..." : `Matikan ${switchPrompt.fromLabel} & nyalakan ${providerLabel(switchPrompt.toKey)}`}
                </button>
              </div>
            </div>
          </div>
        )}
        {/* Right Sidebar: Instance Health */}
        <div className="col-span-12 lg:col-span-4 glass-card rounded-2xl p-6 shadow-sm border border-outline-variant">
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
                      disabled={restartingId === c.id || c.status === "restarting"}
                      title=""
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