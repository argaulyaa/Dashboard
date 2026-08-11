import React from "react";

const domainHealth = (components) => {
  if (!components?.length) return "healthy";
  if (components.some((c) => c.status === "down")) return "down";
  if (components.some((c) => c.status === "degraded")) return "degraded";
  return "healthy";
};

const DOT_COLOR = {
  healthy: "bg-healthy shadow-[0_0_8px_theme(colors.healthy)]",
  degraded: "bg-degraded shadow-[0_0_8px_theme(colors.degraded)]",
  down: "bg-down shadow-[0_0_8px_theme(colors.down)]",
};

const TRACK_PULSE = {
  healthy: "bg-healthy shadow-[0_0_6px_theme(colors.healthy)]",
  degraded: "bg-degraded shadow-[0_0_6px_theme(colors.degraded)]",
  down: "bg-down shadow-[0_0_6px_theme(colors.down)]",
};

export default function TopologyBar({ core, ran, ric }) {
  const coreHealth = domainHealth(core);
  const ranHealth = domainHealth(ran);
  const ricHealth = domainHealth(ric);

  return (
    <div className="flex items-center gap-0 px-4 py-5 bg-panel border border-panel-border rounded-xl mb-7 max-[860px]:flex-col">
      <TopoNode label="CORE" health={coreHealth} />
      <TopoLink iface="N2 / N11" flowHealth={coreHealth} />
      <TopoNode label="RAN" health={ranHealth} />
      <TopoLink iface="E2" flowHealth={ranHealth} />
      <TopoNode label="RIC" health={ricHealth} />
    </div>
  );
}

function TopoNode({ label, health }) {
  return (
    <div className="flex items-center gap-2 font-mono text-[13px] font-semibold tracking-wider px-4 py-2 rounded-lg border border-panel-border whitespace-nowrap">
      <span className={`w-2 h-2 rounded-full ${DOT_COLOR[health]}`} />
      {label}
    </div>
  );
}

function TopoLink({ iface, flowHealth }) {
  return (
    <div className="flex-1 flex flex-col items-center gap-1.5 px-3 min-w-[60px] max-[860px]:w-full max-[860px]:py-2">
      <div className="relative w-full h-0.5 bg-panel-border overflow-hidden rounded-full">
        <span
          className={`absolute top-0 left-[-20%] w-1/5 h-full animate-travel ${TRACK_PULSE[flowHealth]}`}
        />
      </div>
      <span className="font-mono text-[11px] text-dim">{iface}</span>
    </div>
  );
}
