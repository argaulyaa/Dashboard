import React from "react";

const STATUS_LABEL = {
  healthy: "Healthy",
  degraded: "Degraded",
  down: "Down",
  restarting: "Restarting...",
};

const STATUS_BORDER = {
  healthy: "border-l-healthy",
  degraded: "border-l-degraded",
  down: "border-l-down",
  restarting: "border-l-restarting",
};

const STATUS_PILL = {
  healthy: "bg-healthy/10 text-healthy",
  degraded: "bg-degraded/10 text-degraded",
  down: "bg-down/10 text-down",
  restarting: "bg-restarting/10 text-restarting",
};

export default function ComponentCard({ component, onSelect, isSelected }) {
  return (
    <button
      className={`block w-full text-left bg-slate-100 border border-panel-border border-l-[3px] rounded-lg px-3 py-2.5 text-ink cursor-pointer transition-colors font-sans hover:bg-slate-200 ${
        STATUS_BORDER[component.status] ?? "border-l-dim"
      } ${isSelected ? "border-restarting bg-blue-50" : ""}`}
      onClick={() => onSelect(component)}
    >
      <div className="flex justify-between items-center mb-1">
        <span className="font-semibold text-[13px]">
          {component.name}
          {component.reservation && (
            <span
              className="ml-1.5 text-[11px]"
              title={`Reserved by ${component.reservation.user}`}
            >
              🔒
            </span>
          )}
        </span>
        <span
          className={`font-mono text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wide ${
            STATUS_PILL[component.status] ?? "bg-dim/10 text-dim"
          }`}
        >
          {STATUS_LABEL[component.status] ?? component.status}
        </span>
      </div>
      <div className="text-[11px] text-dim font-mono">{component.kind}</div>
      <div className="text-xs text-dim mt-1">{component.detail}</div>
    </button>
  );
}
