import React from "react";
import { useParams, Link } from "react-router-dom";
import SshTerminal from "../components/ConsoleTerminal.jsx";

export default function SshPage({ data, currentUser }) {
  // RBAC 2-role: 'user' & 'admin' sama-sama boleh akses Console SSH.

  const { domain, componentId } = useParams();
  const component = (data[domain] || []).find((c) => c.id === componentId);

  if (!component) {
    return (
      <div>
        <h1 className="text-xl mt-0 mb-1">Console</h1>
        <p className="text-dim text-[13px] mb-5">Component not found.</p>
        <Link
          className="inline-block font-sans text-xs font-semibold px-3 py-1.5 rounded-lg border border-panel-border bg-transparent text-ink"
          to="/reservations"
        >
          Back to Reservations
        </Link>
      </div>
    );
  }

  const activeRes = component.reservation?.active;
  const heldByMe = activeRes && activeRes.user === currentUser;

  return (
    <div>
      <h1 className="text-xl mt-0 mb-1">Console — {component.name}</h1>
      <p className="text-dim text-[13px] mb-5">{component.host}</p>

      {!heldByMe && (
        <div className="text-down text-xs">
          You don't have an active reservation for this component. Reserve it first via the{" "}
          <Link className="underline" to="/reservations">Reservations</Link> page before opening Console.
        </div>
      )}

      {heldByMe && (
        <SshTerminal
          domain={domain}
          componentId={componentId}
          host={component.host}
          currentUser={currentUser}
        />
      )}
    </div>
  );
}
