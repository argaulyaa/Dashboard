import React, { useEffect, useState, useMemo } from "react";
import { fetchProviders, fetchRanStatus, connectRan, disconnectRan, fetchActiveBooking } from "../api.js";
import { getRole } from "../user.js";

// Friendly labels — user-friendly, no confusing raw chart/ns duplication
function friendlyCore(key, providers) {
  if (!key) return null;
  const found = providers?.find((p) => p.key === key);
  if (found?.label) {
    // Use label but clean duplication: e.g. "open5GS (open5gs-chart)" -> keep as is only if key != ns
    // For display pair we prefer short friendly
    const k = String(key).toLowerCase();
    if (k.includes("open5gs")) return "open5GS";
    if (k === "oai") return "OAI 5GC";
    return found.label.replace(/\s*\(.*\)\s*$/, "").trim() || key;
  }
  const k = String(key).toLowerCase();
  if (k.includes("open5gs")) return "open5GS";
  if (k === "oai") return "OAI 5GC";
  return key;
}
function friendlyRan(key) {
  if (!key) return null;
  const k = String(key).toLowerCase();
  if (k === "srsran") return "srsRAN";
  if (k === "oai") return "OAI gNB";
  return key;
}
function inferActiveRan(status) {
  if (!status?.ran) return null;
  const srs = String(status.ran.srsgnb_active || "").toLowerCase();
  const oai = String(status.ran.oai_gnb_active || "").toLowerCase();
  if (srs === "active") return "srsran";
  if (oai === "active") return "oai";
  const ps = String(status.ran.ps || "").toLowerCase();
  if (ps.includes("nr-softmodem")) return "oai";
  if (ps.includes("gnb")) return "srsran";
  return null;
}

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
  // sctp_count is now deduped (unique associations) from backend — keep for logic but not shown raw
  // const sctpCount = status?.sctp_count ?? status?.ran?.sctp_estab ?? 0;

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

  const isCoreMatch = useMemo(() => {
    if (activeCoreProvider && coreSel) return activeCoreProvider === coreSel;
    if (activeNs && selectedNs) return activeNs === selectedNs;
    return false;
  }, [activeCoreProvider, coreSel, activeNs, selectedNs]);

  const ranMatches = useMemo(() => {
    if (!status?.ran) return true;
    if (ranSel === "srsran") return status.ran.srsgnb_active === "active";
    if (ranSel === "oai") return status.ran.oai_gnb_active === "active";
    return true;
  }, [status, ranSel]);

  const isConnected = Boolean(sctp && isCoreMatch && (ranMatches || true));

  const handleToggle = () => {
    if (isConnected) doDisconnect();
    else doConnect();
  };

  // --- User-friendly display: single badge + clean pair text, no duplicate parentheses ---
  const inferredRan = inferActiveRan(status);
  // Prefer active pair when connected, otherwise selected pair
  const displayCoreKey = (isConnected && activeCoreProvider) ? activeCoreProvider : (activeCoreProvider || coreSel);
  const displayRanKey = (isConnected && inferredRan) ? inferredRan : (inferredRan || ranSel);
  const coreFriendly = friendlyCore(displayCoreKey, coreProviders) || "Core";
  const ranFriendly = friendlyRan(displayRanKey) || "RAN";
  // Avoid "open5gs-chart (open5gs-chart)" duplication: helpers already return short friendly; no extra ns badge
  const pairText = `${coreFriendly} ↔ ${ranFriendly}`;

  return (
    <div className="mb-6 glass-card rounded-2xl border border-outline-variant p-4 shadow-sm">
      {blocked && (
        <div className="mb-3 flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-amber-300 bg-amber-50 text-amber-900 text-xs font-medium">
          <span>⚠ No active session - book a session to connect</span>
          <a href="#/reservations" className="shrink-0 px-3 py-1 rounded-lg bg-amber-600 text-white font-bold hover:bg-amber-700">Book now →</a>
        </div>
      )}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="material-symbols-outlined text-primary text-[22px]">link</span>
          <span className="font-black text-title-md md:text-lg tracking-tight">Core ↔ RAN</span>
          {/* Single badge: green if ESTAB else grey if idle — no count, no duplication */}
          <span className={`ml-1 px-3 py-1 rounded-full text-[11px] font-bold border ${sctp ? "bg-green-100 text-green-800 border-green-200" : "bg-slate-100 text-slate-600 border-slate-200"}`}>
            {sctp ? "● Connected" : "○ Idle"}
          </span>
          {/* Clean pair text: e.g. "Connected: OAI 5GC ↔ srsRAN" — no duplicate parentheses */}
          <span className="hidden md:inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-semibold bg-slate-900 text-white">
            {pairText}
          </span>
          {/* Mobile fallback: show pair below badge on small screens */}
          <span className="md:hidden text-[11px] font-medium text-on-surface-variant">{pairText}</span>
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
      {/* SCTP raw line hidden per request — mengganggu di CORE page; info tetap ada di View Logs / ss di RAN. Badge Connected sudah cukup. */}
    </div>
  );
}
