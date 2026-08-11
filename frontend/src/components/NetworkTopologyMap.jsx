import React from "react";

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

  return (
    <div className="bg-white rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.06)] overflow-hidden">
      <div className="p-6 border-b border-outline-variant flex justify-between items-center flex-wrap gap-2">
        <div>
          <h4 className="font-title-lg text-title-lg">Network Topology</h4>
          <p className="text-body-md text-on-surface-variant">Live visual of gNB and UPF connections</p>
        </div>
        <div className="flex gap-2">
          <button className="px-3 py-1 bg-surface-container text-on-surface rounded-lg font-label-lg hover:bg-surface-container-high transition-colors">
            Expand
          </button>
          <button className="px-3 py-1 bg-surface-container text-on-surface rounded-lg font-label-lg hover:bg-surface-container-high transition-colors">
            Refresh
          </button>
        </div>
      </div>
      <div className="relative h-[300px] bg-[#051a3e] p-8 overflow-hidden">
        <svg className="w-full h-full" viewBox="0 0 800 300">
          <path className="topology-line animate-dash" d="M180,150 L390,150" fill="none" strokeWidth="2" />
          <path className="topology-line animate-dash" d="M410,150 L620,150" fill="none" strokeWidth="2" />
          <text x="285" y="135" fill="#c3c6d6" fontFamily="Inter" fontSize="9" textAnchor="middle">N2 / N11</text>
          <text x="515" y="135" fill="#c3c6d6" fontFamily="Inter" fontSize="9" textAnchor="middle">E2</text>

          <Node x={150} y={150} w={38} shape="circle" label="CORE" sub={`${core?.length || 0} NF`} colors={CORE_COLOR[coreHealth]} />
          <Node x={400} y={150} w={32} shape="circle" label="RAN" sub={`${ran?.length || 0} units`} colors={NODE_COLOR[ranHealth]} />
          <Node x={650} y={150} shape="rect" label="RIC" sub={`${ric?.length || 0} xApp`} colors={NODE_COLOR[ricHealth]} />
        </svg>
      </div>
    </div>
  );
}