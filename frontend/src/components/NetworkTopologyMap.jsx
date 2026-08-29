import React, { useState, useEffect, useCallback } from "react";
import { fetchRanStatus } from "../api.js";

const domainHealth = (components) => {
  if (!components?.length) return "healthy";
  if (components.some((c) => c.status === "down")) return "down";
  if (components.some((c) => c.status === "degraded")) return "degraded";
  return "healthy";
};

const NODE_COLOR = {
  healthy: { fill: "#00734c", stroke: "#82f9be" },
  degraded: { fill: "#7d5200", stroke: "#ffb950" },
  down: { fill: "#93000a", stroke: "#ffdad6" },
};

const CORE_COLOR = {
  healthy: { fill: "#0052cc", stroke: "#b2c5ff" },
  degraded: { fill: "#7d5200", stroke: "#ffb950" },
  down: { fill: "#93000a", stroke: "#ffdad6" },
};

function Node({ x, y, w, shape, label, sub, colors }) {
  return (
    <g transform={`translate(${x},${y})`}>
      {shape === "rect" ? (
        <rect x={-32} y={-24} width="64" height="48" rx="8" fill={colors.fill} stroke={colors.stroke} strokeWidth="2" />
      ) : (
        <>
          <circle r={w} fill="none" stroke={colors.fill} strokeWidth="1" opacity="0.35" className="animate-ping" />
          <circle r={w} fill={colors.fill} stroke={colors.stroke} strokeWidth="2" />
        </>
      )}
      <text dy="-2" fill="white" fontFamily="Inter" fontSize="11" fontWeight="700" textAnchor="middle">{label}</text>
      <text dy="11" fill="white" fontFamily="Inter" fontSize="8" opacity="0.8" textAnchor="middle">{sub}</text>
    </g>
  );
}

export default function NetworkTopologyMap({ core, ran, ric }) {
  const coreHealth = domainHealth(core);
  const ranHealth = domainHealth(ran);
  const ricHealth = domainHealth(ric);

  // #7 real SCTP health for CORE-RAN link
  const [sctpEstab, setSctpEstab] = useState(null); // true=ESTAB green, false=down red, null=unknown grey
  const [sctpCount, setSctpCount] = useState(0);
  const [activeNs, setActiveNs] = useState(null);

  const loadSctp = useCallback(async () => {
    try {
      const res = await fetchRanStatus();
      const estab = typeof res.sctp_estab === "boolean" ? res.sctp_estab : (res?.ran?.sctp_estab > 0 ? true : (res.sctp_estab === true ? true : (res.sctp_estab === false ? false : null)));
      // normalize: backend returns sctp_estab boolean + sctp_count numeric
      let normalized = null;
      if (typeof res.sctp_estab === "boolean") normalized = res.sctp_estab;
      else if (typeof res.sctp_estab === "number") normalized = res.sctp_estab > 0;
      else if (res?.ran && typeof res.ran.sctp_estab === "number") normalized = res.ran.sctp_estab > 0;
      setSctpEstab(normalized);
      setSctpCount(res.sctp_count ?? res?.ran?.sctp_estab ?? 0);
      setActiveNs(res.active_ns || res?.core?.active_ns || null);
    } catch {
      setSctpEstab(null);
    }
  }, []);

  useEffect(() => {
    loadSctp();
    const id = setInterval(loadSctp, 15000);
    return () => clearInterval(id);
  }, [loadSctp]);

  // line color based on real sctp_estab
  const CORE_RAN_COLOR = sctpEstab === true ? "#22c55e" : sctpEstab === false ? "#ef4444" : "#6b7280";
  const CORE_RAN_DASH = sctpEstab === true ? "animate-dash" : sctpEstab === false ? "" : "animate-dash opacity-60";
  const SCTP_BADGE_CLASS = sctpEstab === true
    ? "bg-green-100 text-green-800 border-green-200"
    : sctpEstab === false
    ? "bg-red-100 text-red-800 border-red-200"
    : "bg-gray-100 text-gray-600 border-gray-200";
  const SCTP_LABEL = sctpEstab === true
    ? `● SCTP ESTAB${sctpCount ? ` (${sctpCount})` : ""}${activeNs ? ` · ${activeNs}` : ""}`
    : sctpEstab === false
    ? "● SCTP DOWN"
    : "● SCTP unknown";

  return (
    <div className="bg-white rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] overflow-hidden">
      <div className="p-6 border-b border-outline-variant flex justify-between items-center flex-wrap gap-2">
        <div>
          <h4 className="font-title-lg text-title-lg">Network Topology <span className="ml-2 text-label-sm font-normal text-on-surface-variant border border-outline-variant px-1.5 py-0.5 rounded align-middle">Mock topology — illustrative</span><span className={`ml-2 text-[11px] font-bold border px-2 py-0.5 rounded-full align-middle ${SCTP_BADGE_CLASS}`}>{SCTP_LABEL}</span></h4>
          <p className="text-body-md text-on-surface-variant">Schematic CORE–RAN–RIC links (not to scale; health colors are real) — CORE–RAN line <span style={{color: CORE_RAN_COLOR, fontWeight: 700}}>{sctpEstab===true?"green ESTAB":sctpEstab===false?"red DOWN":"grey unknown"}</span> reflects real SCTP</p>
        </div>
        <div className="flex gap-2">
          <button className="px-3 py-1 bg-surface-container text-on-surface rounded-lg font-label-lg hover:bg-surface-container-high transition-colors">
            Expand
          </button>
          <button onClick={loadSctp} className="px-3 py-1 bg-surface-container text-on-surface rounded-lg font-label-lg hover:bg-surface-container-high transition-colors">
            Refresh
          </button>
        </div>
      </div>
      <div className="relative h-[300px] bg-[#051a3e] p-8 overflow-hidden">
        <svg className="w-full h-full" viewBox="0 0 800 300">
          {/* CORE-RAN real SCTP health color */}
          <path className={`topology-line ${CORE_RAN_DASH}`} d="M180,150 L390,150" fill="none" stroke={CORE_RAN_COLOR} strokeWidth="2.5" />
          {/* RAN-RIC illustrative (no real SCTP yet) */}
          <path className="topology-line animate-dash" d="M410,150 L620,150" fill="none" stroke="#4b5563" strokeWidth="2" />
          <text x="285" y="135" fill={CORE_RAN_COLOR} fontFamily="Inter" fontSize="9" fontWeight="700" textAnchor="middle">N2 / N11</text>
          <text x="515" y="135" fill="#9ca3af" fontFamily="Inter" fontSize="9" textAnchor="middle">E2</text>

          <Node x={150} y={150} w={38} shape="circle" label="CORE" sub={`${core?.length || 0} NF`} colors={CORE_COLOR[coreHealth]} />
          <Node x={400} y={150} w={32} shape="circle" label="RAN" sub={`${ran?.length || 0} units`} colors={NODE_COLOR[ranHealth]} />
          <Node x={650} y={150} shape="rect" label="RIC" sub={`${ric?.length || 0} xApp`} colors={NODE_COLOR[ricHealth]} />
        </svg>
      </div>
    </div>
  );
}
