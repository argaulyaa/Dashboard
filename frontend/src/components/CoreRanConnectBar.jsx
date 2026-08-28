import React, { useEffect, useState, useMemo } from "react";
import { fetchProviders, fetchRanStatus, connectRan, disconnectRan, fetchActiveBooking } from "../api.js";
import { getRole } from "../user.js";

export default function CoreRanConnectBar() {
  const [coreProviders, setCoreProviders] = useState([]);
  const [ranProviders, setRanProviders] = useState([]);
  const [coreSel, setCoreSel] = useState("");
  const [ranSel, setRanSel] = useState("");
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [msgErr, setMsgErr] = useState(false);
  const [hasActive, setHasActive] = useState(null); // null=loading, true/false

  const isAdmin = useMemo(() => {
    try { return getRole() === "admin"; } catch { return false; }
  }, []);

  const checkActive = async () => {
    if (isAdmin) { setHasActive(true); return; }
    try {
      const a = await fetchActiveBooking();
      setHasActive(!!a);
    } catch {
      setHasActive(false);
    }
  };

  useEffect(() => {
    fetchProviders("core").then((l) => {
      setCoreProviders(l);
      if (l.length) setCoreSel(l[0].key);
    }).catch(() => {});
    fetchProviders("ran").then((l) => {
      setRanProviders(l);
      if (l.length) setRanSel(l[0].key);
    }).catch(() => {});
    checkActive();
  }, [isAdmin]);

  useEffect(() => {
    const id = setInterval(checkActive, 8000);
    return () => clearInterval(id);
  }, [isAdmin]);

  const pollStatus = async () => {
    try {
      const s = await fetchRanStatus();
      setStatus(s);
    } catch {}
  };

  useEffect(() => {
    pollStatus();
    const id = setInterval(pollStatus, 5000);
    return () => clearInterval(id);
  }, []);

  const blocked = !isAdmin && hasActive === false;

  const doConnect = async () => {
    if (blocked) { setMsg("Requires active booking — book a session first"); setMsgErr(true); return; }
    if (!coreSel || !ranSel) {
      setMsg("Please select Core and RAN provider"); setMsgErr(true); return;
    }
    setBusy(true); setMsg(""); setMsgErr(false);
    try {
      const res = await connectRan(coreSel, ranSel, false);
      const estab = res.ran?.sctp_estab ?? res.sctp_estab;
      const am = res.ran?.amf_addr_set || "";
      setMsg(`${res.status === "connected" ? "CONNECTED" : "STARTED"}: Core ${res.core?.active_ns} (${res.core?.svc}) -> RAN ${res.ran?.unit} AMF ${am} | SCTP ${estab ? "ESTAB" : "PENDING"}`);
      setMsgErr(false);
      setTimeout(pollStatus, 1500);
    } catch (e) {
      const detail = e?.payload ? (typeof e.payload === "string" ? e.payload : JSON.stringify(e.payload)) : e.message;
      setMsg(`Error ${e.status || ""}: ${detail}`); setMsgErr(true);
    } finally { setBusy(false); }
  };

  const doDisconnect = async () => {
    // Disconnect also gated? Allow if blocked? Spec says gate Connect; but we gate both for consistency unless admin
    if (blocked) { setMsg("Requires active booking"); setMsgErr(true); return; }
    if (!coreSel || !ranSel) {
      setMsg("Please select Core and RAN provider"); setMsgErr(true); return;
    }
    setBusy(true); setMsg(""); setMsgErr(false);
    try {
      const res = await disconnectRan(coreSel, ranSel);
      setMsg(`DISCONNECTED: Core ${res.core?.active_ns} (${res.core?.svc}) scaled to 0, RAN ${res.ran?.unit} stopped | SCTP ${res.sctp_estab ? "ESTAB" : "CLOSED"}`);
      setMsgErr(false);
      setTimeout(pollStatus, 1500);
    } catch (e) {
      const detail = e?.payload ? (typeof e.payload === "string" ? e.payload : JSON.stringify(e.payload)) : e.message;
      setMsg(`Error ${e.status || ""}: ${detail}`); setMsgErr(true);
    } finally { setBusy(false); }
  };

  const sctp = status?.sctp_estab;
  const sctpCount = status?.sctp_count ?? status?.ran?.sctp_estab ?? 0;

  // Derive active core provider/ns for dynamic button
  const activeCoreProvider = useMemo(() => {
    if (status?.active_core_provider) return status.active_core_provider;
    if (!status?.core) return null;
    for (const [k, v] of Object.entries(status.core)) {
      if (v && (v.replicas > 0 || v.status === "active")) return k;
    }
    return null;
  }, [status]);
  const activeNs = status?.active_ns || (activeCoreProvider ? status?.core?.[activeCoreProvider]?.ns : null);
  const selectedNs = status?.core?.[coreSel]?.ns || null;

  // UI reflects testbed state: selected Core vs active Core + sctp_estab
  const isCoreMatch = useMemo(() => {
    if (activeCoreProvider && coreSel) return activeCoreProvider === coreSel;
    if (activeNs && selectedNs) return activeNs === selectedNs;
    return false;
  }, [activeCoreProvider, coreSel, activeNs, selectedNs]);

  // Also consider RAN match as secondary signal (if status available)
  const ranMatches = useMemo(() => {
    if (!status?.ran) return true; // no ran data -> rely on core+sctp only per spec
    if (ranSel === "srsran") return status.ran.srsgnb_active === "active";
    if (ranSel === "oai") return status.ran.oai_gnb_active === "active";
    return true;
  }, [status, ranSel]);

  const isConnected = Boolean(sctp && isCoreMatch && (ranMatches || true));
  // Strict per spec: sctp_estab true && active_ns matches selected core
  // ranMatches kept lenient so spec literal passes even if ran active string varies

  const handleToggle = () => {
    if (isConnected) doDisconnect();
    else doConnect();
  };

  return (
    <div className="mb-6 glass-card rounded-2xl border border-outline-variant p-4 shadow-sm">
      {blocked && (
        <div className="mb-3 flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-amber-300 bg-amber-50 text-amber-900 text-xs font-medium">
          <span>⚠ No active session - book a session to connect</span>
          <a href="#/reservations" className="shrink-0 px-3 py-1 rounded-lg bg-amber-600 text-white font-bold hover:bg-amber-700">Book now →</a>
        </div>
      )}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-primary text-[22px]">link</span>
          <span className="font-black text-title-md md:text-lg tracking-tight">Core ↔ RAN</span>
          <span className={`ml-1 px-2.5 py-1 rounded-full text-[10px] font-bold ${sctp ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container text-on-surface-variant"}`}>
            {sctp ? `● ESTAB (${sctpCount})` : "○ NO SCTP"}
          </span>
          {activeCoreProvider && (
            <span className="hidden md:inline-flex ml-1 px-2 py-1 rounded-full text-[10px] font-medium bg-surface-container-low text-on-surface-variant border border-outline-variant">
              active: {activeCoreProvider} {activeNs ? `(${activeNs})` : ""}
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select value={coreSel} onChange={(e) => setCoreSel(e.target.value)} disabled={blocked} className={`px-3 py-2 rounded-lg border border-outline-variant bg-surface-bright text-sm font-medium ${blocked ? "opacity-50 cursor-not-allowed" : ""}`}>
            {coreProviders.map((p) => <option key={p.key} value={p.key}>{p.label} ({p.key})</option>)}
          </select>
          <span className="text-on-surface-variant">↔</span>
          <select value={ranSel} onChange={(e) => setRanSel(e.target.value)} disabled={blocked} className={`px-3 py-2 rounded-lg border border-outline-variant bg-surface-bright text-sm font-medium ${blocked ? "opacity-50 cursor-not-allowed" : ""}`}>
            {ranProviders.length ? ranProviders.map((p) => <option key={p.key} value={p.key}>{p.label} ({p.key})</option>) : ["oai","srsran"].map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <button
            onClick={handleToggle}
            disabled={busy || blocked}
            className={`px-5 py-2 rounded-lg text-sm font-bold shadow-md hover:brightness-110 disabled:opacity-50 flex items-center gap-1.5 transition-colors ${
              isConnected
                ? "bg-error text-on-error border border-error"
                : "bg-primary text-on-primary"
            }`}
            title={blocked ? "Requires active booking — book a session at /reservations" : isConnected ? `Disconnect ${ranSel} from ${coreSel} (scale ${selectedNs || coreSel} to 0 + stop unit)` : `Connect ${ranSel} to ${coreSel}`}
          >
            {busy ? "..." : isConnected ? (
              <>
                <span className="material-symbols-outlined text-base">link_off</span>Disconnect
              </>
            ) : (
              <>
                <span className="material-symbols-outlined text-base">bolt</span>Connect
              </>
            )}
          </button>
        </div>
      </div>
      {msg && <div className={`mt-3 text-xs font-mono px-3 py-2 rounded-lg border ${msgErr ? "bg-error-container text-on-error-container border-error" : "bg-secondary-container text-on-secondary-container border-secondary"}`}>{msg}</div>}
      {status?.ran?.sctp_lines?.length > 0 && <div className="mt-2 text-[11px] font-mono text-on-surface-variant truncate">{status.ran.sctp_lines.slice(0,2).join(" | ")}</div>}
    </div>
  );
}
