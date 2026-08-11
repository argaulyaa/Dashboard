import React from "react";
import ComponentCard from "../components/ComponentCard.jsx";

export default function DomainPage({ title, subtitle, components, onSelect }) {
  return (
    <div>
      <h1 className="text-xl mt-0 mb-1">{title}</h1>
      <p className="text-dim text-[13px] mb-5">{subtitle}</p>

      <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(240px,1fr))]">
        {components.length === 0 && (
          <div className="text-dim text-[13px] font-mono py-3">No component data available.</div>
        )}
        {components.map((c) => (
          <ComponentCard key={c.id} component={c} onSelect={onSelect} isSelected={false} />
        ))}
      </div>
    </div>
  );
}
