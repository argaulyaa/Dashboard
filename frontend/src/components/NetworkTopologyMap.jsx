import React, { useState, useEffect, useCallback } from "react";
import { fetchRanStatus, fetchProviders, fetchComponents } from "../api.js";

const domainHealth = (components) => {
  if (!components?.length) return "unknown";
  if (components.some((c) => c.status === "down")) return "down";
  if (components.some((c) => c.status === "degraded")) return "degraded";
  return "healthy";
};

const HEALTH_FILL = {
  healthy: { bg: "#10b981", stroke: "#6ee7b7", glow: "rgba(16,185,129,0.5)", label: "Healthy" },
  degraded: { bg: "#f59e0b", stroke: "#fcd34d", glow: "rgba(245,158,11,0.45)", label: "Degraded" },
  down: { bg: "#ef4444", stroke: "#fca5a5", glow: "rgba(239,68,68,0.5)", label: "Down" },
  unknown: { bg: "#6b7280", stroke: "#9ca3af", glow: "rgba(107,114,128,0.35)", label: "Unknown" },
};

// Normalize active_core_provider -> "oai" or "open5gs"
function normCore(provider) {
  if (!provider) return null;
  const p = String(provider).toLowerCase();
  if (p.includes("open5gs")) return "open5gs";
  if (p.includes("oai")) return "oai";
  if (p === "magma") return "magma";
  return p;
}
function normRanFromStatus(ran) {
  if (!ran) return null;
  const srs = String(ran.srsgnb_active || "").toLowerCase();
  const oai = String(ran.oai_gnb_active || "").toLowerCase();
  const ps = String(ran.ps || "").toLowerCase();
  // prefer systemctl active
  if (srs === "active") return "srsran";
  if (oai === "active") return "oai";
  // fallback: ps contains binary name
  if (ps.includes("gnb") && !ps.includes("nr-softmodem")) return "srsran";
  if (ps.includes("nr-softmodem")) return "oai";
  // if both inactive, fallback null
  return null;
}

export default function NetworkTopologyMap({ core, ran, ric }) {
  // real-time fetched state
  const [ranStatus, setRanStatus] = useState(null);
  const [healthMap, setHealthMap] = useState({
    "core-oai": domainHealth(core),
    "core-open5gs": "unknown",
    "ran-oai": "unknown",
    "ran-srsran": "unknown",
    "ric": domainHealth(ric),
  });
  const [tooltip, setTooltip] = useState(null); // {x,y,text}

  // derived active pair
  const activeCore = normCore(ranStatus?.active_core_provider || ranStatus?.active_ns && (ranStatus.active_ns.includes("open5gs") ? "open5gs" : ranStatus.active_ns.includes("5g-core") ? "oai" : null));
  // also try core.active_ns map fallback: if active_ns is "5g-core" -> oai, "open5gs-chart"/"open5gs-v2"/"open5gs" -> open5gs
  const activeCoreResolved = (() => {
    const a = normCore(ranStatus?.active_core_provider);
    if (a) return a;
    const ns = String(ranStatus?.active_ns || "").toLowerCase();
    if (ns.includes("open5gs")) return "open5gs";
    if (ns.includes("5g-core")) return "oai";
    // fallback: check core snapshot replicas>0
    if (ranStatus?.core) {
      for (const [k, v] of Object.entries(ranStatus.core)) {
        if (v?.status === "active" || v?.replicas > 0) return normCore(k);
      }
    }
    return null;
  })();
  const activeRan = normRanFromStatus(ranStatus?.ran);
  const sctpEstab = ranStatus?.sctp_estab === true || (ranStatus?.ran?.sctp_estab > 0);
  const sctpCount = ranStatus?.sctp_count ?? ranStatus?.ran?.sctp_estab ?? 0;

  const loadAll = useCallback(async () => {
    // 1) ran/status
    let rs = null;
    try {
      rs = await fetchRanStatus();
      setRanStatus(rs);
    } catch {
      // keep previous
    }
    // 2) per-provider health via components (real) — parallel, best-effort
    const tryFetch = async (domain, provider) => {
      try {
        const comps = await fetchComponents(domain, provider);
        return domainHealth(comps);
      } catch {
        return "unknown";
      }
    };
    try {
      // providers listing (verify existence, but health from components)
      const [coreProvs, ranProvs, ricProvs] = await Promise.allSettled([
        fetchProviders("core"),
        fetchProviders("ran"),
        fetchProviders("ric"),
      ]);
      // determine which providers exist to avoid 404 noise? still try components
      const hasCoreOai = coreProvs.status === "fulfilled" && coreProvs.value.some(p=>p.key==="oai");
      const hasCoreOpen5gs = coreProvs.status === "fulfilled" && coreProvs.value.some(p=>p.key==="open5gs"||p.key==="open5gs-chart");
      const hasRanOai = ranProvs.status === "fulfilled" && ranProvs.value.some(p=>p.key==="oai");
      const hasRanSrs = ranProvs.status === "fulfilled" && ranProvs.value.some(p=>p.key==="srsran");
      const hasRic = ricProvs.status === "fulfilled";

      const [hCoreOai, hCoreOpen, hRanOai, hRanSrs, hRic] = await Promise.all([
        hasCoreOai || true ? tryFetch("core","oai") : Promise.resolve("unknown"),
        hasCoreOpen5gs || true ? tryFetch("core","open5gs") : tryFetch("core","open5gs-chart"),
        hasRanOai || true ? tryFetch("ran","oai") : Promise.resolve("unknown"),
        hasRanSrs || true ? tryFetch("ran","srsran") : Promise.resolve("unknown"),
        hasRic ? tryFetch("ric","oai") : Promise.resolve(domainHealth(ric)),
      ]);
      // fallback to props if unknown and props available (telemetry for active provider)
      const fallbackCore = domainHealth(core);
      const fallbackRan = domainHealth(ran);
      const fallbackRic = domainHealth(ric);
      setHealthMap({
        "core-oai": hCoreOai !== "unknown" ? hCoreOai : fallbackCore,
        "core-open5gs": hCoreOpen !== "unknown" ? hCoreOpen : "unknown",
        "ran-oai": hRanOai !== "unknown" ? hRanOai : (activeRan==="oai" ? fallbackRan : hRanOai),
        "ran-srsran": hRanSrs !== "unknown" ? hRanSrs : (activeRan==="srsran" ? fallbackRan : hRanSrs),
        "ric": hRic !== "unknown" ? hRic : fallbackRic,
      });
    } catch {
      // fallback to prop health
      setHealthMap({
        "core-oai": domainHealth(core) || "unknown",
        "core-open5gs": "unknown",
        "ran-oai": "unknown",
        "ran-srsran": domainHealth(ran) || "unknown",
        "ric": domainHealth(ric) || "unknown",
      });
    }
  }, [core, ran, ric, activeRan]);

  useEffect(() => {
    loadAll();
    const id = setInterval(loadAll, 15000);
    return () => clearInterval(id);
  }, [loadAll]);

  // Keep healthMap in sync when props change (telemetry push) even if fetch pending
  useEffect(() => {
    setHealthMap((prev) => ({
      ...prev,
      "core-oai": prev["core-oai"] === "unknown" ? domainHealth(core) : prev["core-oai"],
      "ric": prev["ric"] === "unknown" ? domainHealth(ric) : prev["ric"],
    }));
  }, [core, ric]);

  const isActivePair = (coreKey, ranKey) => activeCoreResolved === coreKey && activeRan === ranKey && sctpEstab;

  // positions
  const POS = {
    "core-oai": { x: 180, y: 72 },
    "core-open5gs": { x: 620, y: 72 },
    "ric": { x: 400, y: 188 },
    "ran-oai": { x: 180, y: 360 },
    "ran-srsran": { x: 620, y: 360 },
  };

  function NodeCard({ id, label, sub, icon }) {
    const h = healthMap[id] || "unknown";
    const c = HEALTH_FILL[h];
    const p = POS[id];
    const isCore = id.startsWith("core");
    const isRic = id === "ric";
    return (
      <g
        transform={`translate(${p.x},${p.y})`}
        style={{ cursor: "pointer" }}
        onMouseEnter={() => setTooltip({ x: p.x, y: p.y - 62, text: `${label} • ${c.label} (${h})` })}
        onMouseLeave={() => setTooltip(null)}
      >
        {/* glow */}
        <ellipse cx="0" cy="0" rx={isRic ? 72 : 68} ry={isRic ? 46 : 42} fill={c.bg} opacity="0.12" />
        {/* card bg */}
        <rect x={isRic ? -68 : -64} y="-36" width={isRic ? 136 : 128} height="72" rx="14" fill="#0f1e3a" stroke={c.stroke} strokeWidth={isActivePairForNode(id) ? 2.2 : 1.4} opacity="0.98" style={{ filter: `drop-shadow(0 0 10px ${c.glow})` }} />
        {/* top health dot */}
        <circle cx={isRic ? 56 : 52} cy="-24" r="7" fill={c.bg} stroke="#0f1e3a" strokeWidth="2" />
        <circle cx={isRic ? 56 : 52} cy="-24" r="7" fill={c.bg} opacity="0.45" className="animate-ping" style={{ animationDuration: "2.2s" }} />
        {/* icon */}
        <foreignObject x="-14" y="-26" width="28" height="28">
          <div style={{ width: 28, height: 28, borderRadius: 8, background: `${c.bg}22`, display: "flex", alignItems: "center", justifyContent: "center", border: `1px solid ${c.stroke}55` }}>
            <span className="material-symbols-outlined" style={{ fontSize: 16, color: c.bg }}>{icon}</span>
          </div>
        </foreignObject>
        {/* labels */}
        <text y="8" textAnchor="middle" fill="white" fontFamily="Inter" fontSize="11" fontWeight="800" letterSpacing="0.3">{label}</text>
        <text y="22" textAnchor="middle" fill="#cbd5e1" fontFamily="Inter" fontSize="8.5" fontWeight="500" opacity="0.95">{sub}</text>
        {/* type badge */}
        <g transform={`translate(${- (isRic? 68:64) + 10},-28)`}>
          <rect width={isCore ? 36 : isRic ? 30 : 34} height="14" rx="7" fill={isCore ? "#1e3a8a" : isRic ? "#134e4a" : "#312e81"} opacity="0.95" />
          <text x={isCore ? 18 : isRic ? 15 : 17} y="10" textAnchor="middle" fill="#e2e8f0" fontSize="7" fontWeight="800" letterSpacing="0.6">{isCore ? "CORE" : isRic ? "RIC" : "gNB"}</text>
        </g>
      </g>
    );
  }

  function isActivePairForNode(nodeId) {
    // highlight node if part of active pair
    if (nodeId === "core-oai" && activeCoreResolved === "oai" && sctpEstab) return true;
    if (nodeId === "core-open5gs" && activeCoreResolved === "open5gs" && sctpEstab) return true;
    if (nodeId === "ran-oai" && activeRan === "oai" && sctpEstab) return true;
    if (nodeId === "ran-srsran" && activeRan === "srsran" && sctpEstab) return true;
    if (nodeId === "ric" && healthMap["ric"] === "healthy") return true;
    return false;
  }

  function Link({ from, to, active, label, kind }) {
    const a = POS[from];
    const b = POS[to];
    // curved path
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    // add slight curve for diagonal links
    const dx = b.x - a.x;
    const isVertical = Math.abs(dx) < 10;
    let d;
    if (isVertical) {
      d = `M ${a.x} ${a.y + 36} C ${a.x} ${a.y + 90}, ${b.x} ${b.y - 90}, ${b.x} ${b.y - 36}`;
    } else {
      // diagonal with gentle S
      const c1x = a.x + (b.x > a.x ? 80 : -80);
      const c1y = a.y + 70;
      const c2x = b.x + (b.x > a.x ? -80 : 80);
      const c2y = b.y - 70;
      d = `M ${a.x} ${a.y + 36} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${b.x} ${b.y - 36}`;
    }
    const stroke = active
      ? (kind === "e2" ? "#22d3ee" : "#22c55e")
      : "#475569";
    const width = active ? 2.6 : 1.5;
    const dash = active ? null : "6 7";
    const opacity = active ? 1 : 0.55;
    const glow = active ? (kind === "e2" ? "rgba(34,211,238,0.55)" : "rgba(34,197,94,0.6)") : "rgba(71,85,105,0.35)";
    return (
      <g>
        {/* glow under */}
        <path d={d} fill="none" stroke={glow} strokeWidth={width + 5} opacity={active ? 0.28 : 0.15} strokeLinecap="round" />
        <path d={d} fill="none" stroke={stroke} strokeWidth={width} opacity={opacity} strokeLinecap="round" strokeDasharray={dash} className={active ? "" : "topology-line"} />
        {/* animated dot for active */}
        {active && (
          <circle r="5" fill={kind === "e2" ? "#22d3ee" : "#22c55e"} stroke="white" strokeWidth="1.2" opacity="0.95">
            <animateMotion dur={kind === "e2" ? "2.2s" : "1.8s"} repeatCount="indefinite" rotate="auto">
              <mpath href={`#path-${from}-${to}`} />
            </animateMotion>
          </circle>
        )}
        {/* invisible path for motion */}
        <path id={`path-${from}-${to}`} d={d} fill="none" stroke="none" />
        {/* label */}
        <g transform={`translate(${mx},${my - (isVertical ? 10 : 6)})`}>
          <rect x="-22" y="-9" width="44" height="14" rx="7" fill={active ? (kind === "e2" ? "#0e7490" : "#14532d") : "#1e293b"} opacity={active ? 0.98 : 0.85} stroke={active ? stroke : "#334155"} strokeWidth="0.9" />
          <text textAnchor="middle" y="2" fill={active ? "white" : "#94a3b8"} fontFamily="Inter" fontSize="7.5" fontWeight="800" letterSpacing="0.5">{label}</text>
        </g>
      </g>
    );
  }

  const sctpLabel = sctpEstab ? `SCTP ESTAB${sctpCount ? ` · ${sctpCount}` : ""}` : "SCTP idle";
  const activePairText = activeCoreResolved && activeRan ? `${activeCoreResolved === "oai" ? "OAI 5GC" : "open5gs"} ↔ ${activeRan === "oai" ? "OAI gNB" : "srsRAN"}` : "no active N2";
  const ricHealthy = healthMap["ric"] === "healthy";

  return (
    <div className="bg-white rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] overflow-hidden border border-slate-100">
      <div className="px-5 py-4 border-b border-slate-100 flex justify-between items-start gap-3 flex-wrap">
        <div className="min-w-0">
          <h4 className="font-title-lg text-title-lg flex items-center gap-2 flex-wrap">
            Network Topology
            <span className="inline-flex items-center gap-1.5 bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-0.5 rounded-full text-[11px] font-extrabold tracking-wide">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              Live
            </span>
            <span className={`inline-flex items-center gap-1 border px-2.5 py-0.5 rounded-full text-[11px] font-bold ${sctpEstab ? "bg-green-100 text-green-800 border-green-200" : "bg-slate-100 text-slate-600 border-slate-200"}`}>
              ● {sctpLabel}
            </span>
            {activeCoreResolved && (
              <span className="inline-flex items-center bg-slate-900 text-white px-2.5 py-0.5 rounded-full text-[11px] font-bold">
                {activePairText}
              </span>
            )}
          </h4>
          <p className="text-body-md text-on-surface-variant mt-1">
            2 Core · 2 gNB · 1 RIC — <span style={{ color: sctpEstab ? "#16a34a" : "#64748b", fontWeight: 700 }}>{sctpEstab ? "green solid = active N2" : "grey dashed = idle"}</span> · E2 <span style={{ color: ricHealthy ? "#0891b2" : "#64748b", fontWeight: 700 }}>{ricHealthy ? "cyan = FlexRIC healthy" : "grey = RIC down"}</span> — health colors are real
          </p>
        </div>
        <button onClick={loadAll} className="shrink-0 px-3.5 py-1.5 bg-slate-900 text-white rounded-full font-label-lg hover:bg-slate-800 transition-colors text-[13px] flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[16px]">refresh</span> Refresh
        </button>
      </div>

      <div className="relative bg-[#06102a] overflow-hidden" style={{ height: 460 }}>
        {/* subtle grid + vignette */}
        <div className="absolute inset-0 opacity-[0.07]" style={{ backgroundImage: "linear-gradient(rgba(148,163,184,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.5) 1px, transparent 1px)", backgroundSize: "32px 32px" }} />
        <div className="absolute inset-0" style={{ background: "radial-gradient(900px 420px at 50% 0%, rgba(56,189,248,0.16), transparent 62%), radial-gradient(700px 380px at 12% 95%, rgba(34,197,94,0.12), transparent 60%), radial-gradient(700px 380px at 88% 95%, rgba(168,85,247,0.12), transparent 60%)" }} />

        <svg className="absolute inset-0 w-full h-full" viewBox="0 0 800 440" preserveAspectRatio="xMidYMid meet">
          <defs>
            <filter id="glow-green" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3.5" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          {/* N2 links: 4 pairs */}
          <Link from="core-oai" to="ran-oai" active={isActivePair("core-oai","ran-oai")} label="N2" kind="n2" />
          <Link from="core-oai" to="ran-srsran" active={isActivePair("core-oai","ran-srsran")} label="N2" kind="n2" />
          <Link from="core-open5gs" to="ran-oai" active={isActivePair("core-open5gs","ran-oai")} label="N2" kind="n2" />
          <Link from="core-open5gs" to="ran-srsran" active={isActivePair("core-open5gs","ran-srsran")} label="N2" kind="n2" />

          {/* E2 links: RIC -> both gNBs */}
          <Link from="ric" to="ran-oai" active={ricHealthy} label="E2" kind="e2" />
          <Link from="ric" to="ran-srsran" active={ricHealthy} label="E2" kind="e2" />

          {/* Nodes */}
          <NodeCard id="core-oai" label="OAI 5GC" sub="5g-core · N2 38412" icon="cloud" />
          <NodeCard id="core-open5gs" label="open5gs" sub="open5gs-chart · N2 32112" icon="dns" />
          <NodeCard id="ric" label="FlexRIC" sub="nearRT-RIC · E2 36421" icon="hub" />
          <NodeCard id="ran-oai" label="OAI gNB" sub="nr-softmodem" icon="cell_tower" />
          <NodeCard id="ran-srsran" label="srsRAN" sub="srsGNB · gnb" icon="settings_input_antenna" />
        </svg>

        {/* tooltip */}
        {tooltip && (
          <div className="absolute pointer-events-none px-2.5 py-1 rounded-full bg-slate-900 text-white text-[11px] font-bold shadow-lg border border-white/10" style={{ left: `${(tooltip.x / 800) * 100}%`, top: tooltip.y, transform: "translateX(-50%)" }}>
            {tooltip.text}
          </div>
        )}

        {/* legend */}
        <div className="absolute bottom-3 left-3 right-3 flex flex-wrap gap-2 items-center justify-between">
          <div className="flex flex-wrap gap-1.5 items-center bg-slate-900/85 backdrop-blur px-3 py-2 rounded-full border border-white/10 shadow">
            <span className="flex items-center gap-1.5 text-[10px] font-bold text-white"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.7)]" /> Healthy</span>
            <span className="w-px h-3 bg-white/15" />
            <span className="flex items-center gap-1.5 text-[10px] font-bold text-white"><span className="w-2.5 h-2.5 rounded-full bg-amber-500" /> Degraded</span>
            <span className="w-px h-3 bg-white/15" />
            <span className="flex items-center gap-1.5 text-[10px] font-bold text-white"><span className="w-2.5 h-2.5 rounded-full bg-red-500" /> Down</span>
            <span className="w-px h-3 bg-white/15" />
            <span className="flex items-center gap-1.5 text-[10px] font-bold text-white"><span className="w-2.5 h-2.5 rounded-full bg-slate-500" /> Unknown</span>
            <span className="w-px h-3 bg-white/15 hidden sm:inline" />
            <span className="hidden sm:flex items-center gap-1.5 text-[10px] font-bold text-emerald-300"><span className="w-6 h-[2.5px] bg-emerald-500 rounded-full" /> N2 active</span>
            <span className="hidden sm:flex items-center gap-1.5 text-[10px] font-bold text-slate-300"><span className="w-6 h-[2px] border-t-[2px] border-dashed border-slate-400" /> idle</span>
            <span className="hidden sm:flex items-center gap-1.5 text-[10px] font-bold text-cyan-300"><span className="w-6 h-[2.5px] bg-cyan-400 rounded-full" /> E2</span>
          </div>
          <div className="hidden md:flex items-center gap-1.5 bg-white/95 px-3 py-1.5 rounded-full text-[10px] font-bold text-slate-700 shadow border border-slate-200">
            <span className="material-symbols-outlined text-[14px] text-slate-500">info</span> Hover node for provider · dashed = inactive, solid + dot = SCTP ESTAB
          </div>
        </div>
      </div>
    </div>
  );
}
