import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import NetworkTopologyMap from "../components/NetworkTopologyMap.jsx";
import { fetchMe } from "../auth.js";


const DOMAIN_META = {
  core: { title: "Core", subtitle: "5G Core network functions", icon: "memory" },
  ran: { title: "RAN", subtitle: "gNB / CU / DU (OAI)", icon: "settings_input_antenna" },
  ric: { title: "RIC", subtitle: "near-RT & non-RT RIC", icon: "lan" },
};

const ACCENT_BORDER = { core: "border-primary", ran: "border-secondary", ric: "border-tertiary" };
const ACCENT_ICON = {
  core: "bg-primary-fixed text-primary",
  ran: "bg-secondary-fixed text-secondary",
  ric: "bg-tertiary-fixed text-tertiary",
};

const HEALTH_LABEL = { healthy: "Online", degraded: "Degraded", down: "Down" };
const HEALTH_PILL = {
  healthy: "bg-secondary-container text-on-secondary-fixed-variant",
  degraded: "bg-tertiary-fixed text-on-tertiary-fixed-variant",
  down: "bg-error-container text-on-error-container",
};

const ACTIVITY_BG = {
  primary: "bg-primary-fixed text-primary",
  secondary: "bg-secondary-container text-secondary",
  tertiary: "bg-tertiary-fixed text-tertiary",
  error: "bg-error-container text-error",
};

function domainUptimeSeconds(components, nowSeconds) {
  if (!components?.length) return null;
  const newestStart = Math.max(...components.map((c) => c.started_at || 0));
  return newestStart ? Math.max(0, nowSeconds - newestStart) : null;
}

function formatUptime(seconds) {
  if (seconds == null) return "-";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return d > 0 ? `${d}d ${h}h ${m}m` : `${h}h ${m}m`;
}

function domainHealth(components) {
  if (!components?.length) return "healthy";
  if (components.some((c) => c.status === "down")) return "down";
  if (components.some((c) => c.status === "degraded")) return "degraded";
  return "healthy";
}

function formatRemaining(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

function buildActivity(components) {
  const items = [];
  components.forEach((c) => {
    if (c.status === "restarting") {
      items.push({ id: `${c.domain}-${c.id}-restart`, icon: "autorenew", color: "primary", text: `${c.name} is restarting.` });
    } else if (c.status === "down") {
      items.push({ id: `${c.domain}-${c.id}-down`, icon: "error", color: "error", text: `${c.name} is down.` });
    } else if (c.status === "degraded") {
      items.push({ id: `${c.domain}-${c.id}-degraded`, icon: "warning", color: "tertiary", text: `${c.name} performance degraded.` });
    }
    if (c.reservation) {
      items.push({
        id: `${c.domain}-${c.id}-res`,
        icon: "lock",
        color: "secondary",
        text: `${c.name} reserved by ${c.reservation.user}.`,
      });
    }
  });
  if (items.length === 0) {
    items.push({ id: "all-clear", icon: "check_circle", color: "secondary", text: "All components running normally." });
  }
  return items.slice(0, 5);
}

function MetricCard({ label, value, icon, color }) {
  return (
    <div className="bg-white p-6 rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] flex items-center justify-between">
      <div>
        <p className="text-on-surface-variant font-label-lg mb-1">{label}</p>
        <h3 className={`font-display-lg text-headline-lg ${color}`}>{value}</h3>
      </div>
      <span className={`material-symbols-outlined text-display-lg opacity-20 ${color}`}>{icon}</span>
    </div>
  );
}

function DomainCard({ domainKey, components, onSelect, nowSeconds }) {
  const meta = DOMAIN_META[domainKey];
  const health = domainHealth(components);
  const problem = components.find((c) => c.status !== "healthy");
  const uptime = domainUptimeSeconds(components, nowSeconds);
  // RIC is now live K8s (KubectlRicAdapter ns ric) — no mock domain remains.
  // Keep isMock only if provider is truly a mock adapter (e.g. desc contains "mock").
  const isMock = false;

  return (
    <div className={`bg-white p-6 rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] border-t-4 ${ACCENT_BORDER[domainKey]}`}>
      <div className="flex justify-between items-start mb-4">
        <span className={`material-symbols-outlined p-2 rounded-lg ${ACCENT_ICON[domainKey]}`}>{meta.icon}</span>
        <span className={`px-2 py-0.5 rounded text-label-sm font-bold uppercase tracking-wider ${HEALTH_PILL[health]}`}>
          {HEALTH_LABEL[health]}
        </span>
      </div>
      <h4 className="font-title-lg text-title-lg mb-1">{meta.title} {isMock && <span className="text-label-sm font-normal text-on-surface-variant border border-outline-variant px-1.5 py-0.5 rounded ml-1 align-middle">mock</span>}</h4>
      <p className="text-body-md text-on-surface-variant mb-1">Uptime: {formatUptime(uptime)}</p>
      <p className="text-body-md text-on-surface-variant mb-4">
        {meta.subtitle} &middot; {components.length} components
      </p>
      <div className="flex flex-col gap-2">
        <Link className="text-primary hover:underline font-label-lg flex items-center gap-1" to={`/${domainKey}`}>
          View all components <span className="material-symbols-outlined text-[16px]">chevron_right</span>
        </Link>
        {problem && (
          <button
            className="text-left bg-transparent text-primary hover:underline font-label-lg flex items-center gap-1"
            onClick={() => onSelect(domainKey, problem)}
          >
            Check {problem.name} <span className="material-symbols-outlined text-[16px]">chevron_right</span>
          </button>
        )}
      </div>
    </div>
  );
}

export default function Overview({ data, currentUser, onSelect, onReservationChange }) {
  // displayName uses Full Name from /api/auth/me (full_name), fallback to username if empty, never email/Network ID
  const [displayName, setDisplayName] = useState(currentUser || "Admin");
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await fetchMe();
        if (cancelled) return;
        const fn = (me?.full_name || "").trim();
        if (fn) setDisplayName(fn);
        else setDisplayName(currentUser || "Admin");
      } catch {
        if (!cancelled) setDisplayName(currentUser || "Admin");
      }
    })();
    return () => { cancelled = true; };
  }, [currentUser]);
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60000);
    return () => clearInterval(t);
  }, []);

  const allComponents = [
    ...(data.core || []).map((c) => ({ ...c, domain: "core" })),
    ...(data.ran || []).map((c) => ({ ...c, domain: "ran" })),
    ...(data.ric || []).map((c) => ({ ...c, domain: "ric" })),
  ];

  const total = allComponents.length;
  const healthyCount = allComponents.filter((c) => c.status === "healthy").length;
  const overallHealth = allComponents.some((c) => c.status === "down")
    ? "down"
    : allComponents.some((c) => c.status === "degraded")
    ? "degraded"
    : "healthy";
  const reservedComponents = allComponents.filter((c) => c.reservation?.active);
  const activity = buildActivity(allComponents);
  const systemUptime = domainUptimeSeconds(allComponents, now.getTime() / 1000);

  const dateLabel = now.toLocaleDateString("en-US", {
    weekday: "long",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  const timeLabel = now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });

  const healthDot =
    overallHealth === "healthy" ? "bg-secondary" : overallHealth === "degraded" ? "bg-tertiary" : "bg-error";
  const healthText =
    overallHealth === "healthy" ? "text-secondary" : overallHealth === "degraded" ? "text-tertiary" : "text-error";
  const healthLabel =
    overallHealth === "healthy" ? "System Normal" : overallHealth === "degraded" ? "Partially Degraded" : "System Issue";

  return (
    <div>
      {/* Header & status kesehatan */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-8">
        <div>
          <h2 className="font-headline-lg text-headline-lg text-on-surface mb-1">
            Welcome, {displayName}
          </h2>
          <p className="text-body-lg text-on-surface-variant">
            {dateLabel} &middot; {timeLabel}
          </p>
        </div>
        <div className="flex items-center gap-3 bg-white px-4 py-3 rounded-xl shadow-sm border border-secondary/20">
          <div className="relative flex h-3 w-3">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${healthDot}`} />
            <span className={`relative inline-flex rounded-full h-3 w-3 ${healthDot}`} />
          </div>
          <span className={`font-title-md ${healthText}`}>{healthLabel}</span>
          <span className="text-label-sm text-on-surface-variant ml-2">
            {healthyCount}/{total} healthy components
          </span>
          <span className="text-label-sm text-on-surface-variant ml-2">
            &middot; Uptime: {formatUptime(systemUptime)}
          </span>
        </div>
      </div>

      {/* Metrik ringkas — hanya data nyata, tanpa mock bandwidth/latency */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter mb-8">
        <MetricCard label="Nodes Online" value={`${healthyCount}/${total}`} icon="router" color="text-primary" />
        <MetricCard label="Active Reservations" value={reservedComponents.length} icon="lock" color="text-secondary" />
        <MetricCard label="System Health" value={healthLabel} icon="monitor_heart" color={healthText} />
      </div>

      {/* Grid utama */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter">
        <div className="lg:col-span-8 space-y-gutter">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter">
            {Object.keys(DOMAIN_META).map((key) => (
              <DomainCard
                key={key}
                domainKey={key}
                components={data[key] || []}
                onSelect={onSelect}
                nowSeconds={now.getTime() / 1000}
              />
            ))}
          </div>

          <NetworkTopologyMap core={data.core} ran={data.ran} ric={data.ric} />
        </div>

        <div className="lg:col-span-4 space-y-gutter">
          {/* Reservasi aktif */}
          <div className="bg-white rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)]">
            <div className="p-6 border-b border-outline-variant flex justify-between items-center">
              <h4 className="font-title-lg text-title-lg">Active Reservations</h4>
              <span className="material-symbols-outlined text-on-surface-variant">lock</span>
            </div>
            <div className="p-4 space-y-3">
              {reservedComponents.length === 0 && (
                <p className="text-label-sm text-on-surface-variant px-1">No components currently reserved.</p>
              )}
              {reservedComponents.slice(0, 4).map((c) => {
                const activeRes = c.reservation.active;
                return (
                  <div key={`${c.domain}-${c.id}`} className="p-3 bg-surface-container-low rounded-lg border border-outline-variant/30">
                    <div className="flex justify-between items-start mb-1">
                      <span className="font-title-md">{c.name}</span>
                      <span className="bg-primary text-white px-2 py-0.5 rounded text-[10px] font-bold uppercase">
                        Active
                      </span>
                    </div>
                    <p className="text-label-sm text-on-surface-variant mb-2">
                      Reserved by <span className="text-primary font-bold">{activeRes.user}</span>
                    </p>
                    <div className="flex justify-between items-center text-label-sm">
                      <span>Expires in {formatRemaining(activeRes.remaining_seconds)}</span>
                      {activeRes.user === currentUser && (
                        <Link
                          className="font-semibold text-primary hover:underline text-xs"
                          to={`/ssh/${c.domain}/${c.id}`}
                        >
                          Console
                        </Link>
                      )}
                    </div>
                  </div>
                );
              })}
              {/* RBAC 2-role: semua role boleh kelola reservasi */}
              {true && (
                <Link
                  to="/reservations"
                  className="block text-center w-full py-3 bg-primary-container text-white rounded-xl font-label-lg hover:brightness-110 transition-all mt-3"
                >
                  Manage Reservations
                </Link>
              )}
            </div>
          </div>

          {/* Aktivitas terbaru */}
          <div className="bg-white rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] overflow-hidden">
            <div className="p-6 border-b border-outline-variant">
              <h4 className="font-title-lg text-title-lg">Recent Activity</h4>
            </div>
            <div className="divide-y divide-outline-variant/30">
              {activity.map((a) => (
                <div key={a.id} className="p-4 flex gap-3">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${ACTIVITY_BG[a.color]}`}>
                    <span className="material-symbols-outlined text-[20px]">{a.icon}</span>
                  </div>
                  <div>
                    <p className="text-body-md text-on-surface">{a.text}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}