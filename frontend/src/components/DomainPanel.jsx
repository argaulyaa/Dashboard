import React from "react";
import ComponentCard from "./ComponentCard.jsx";

export default function DomainPanel({ title, subtitle, components, onSelect, selectedId }) {
  return (
    <section className="bg-panel border border-panel-border rounded-xl p-4 flex flex-col gap-3">
      <header>
        <h2 className="m-0 text-[15px] font-semibold">{title}</h2>
        <p className="mt-0.5 mb-0 text-dim text-xs">{subtitle}</p>
      </header>
      <div className="flex flex-col gap-2.5">
        {components.length === 0 && (
          <div className="text-dim text-[13px] font-mono py-3">No component data available.</div>
        )}
        {components.map((c) => (
          <ComponentCard
            key={c.id}
            component={c}
            onSelect={onSelect}
            isSelected={c.id === selectedId}
          />
        ))}
      </div>
    </section>
  );
}
