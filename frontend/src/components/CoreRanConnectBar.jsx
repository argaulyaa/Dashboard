import React, { useEffect, useState } from "react";
import { fetchProviders, fetchRanStatus, connectRan } from "../api.js";

export default function CoreRanConnectBar() {
  const [coreProviders, setCoreProviders] = useState([]);
  const [ranProviders, setRanProviders] = useState([]);
  const [coreSel, setCoreSel] = useState("");
  const [ranSel, setRanSel] = useState("");
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [msgErr, setMsgErr] = useState(false);

  useEffect(() => {
    fetchProviders("core").then((l) => {
      setCoreProviders(l);
      if (l.length) setCoreSel(l[0].key);
    }).catch(() => {});
    fetchProviders("ran").then((l) => {
      setRanProviders(l);
      if (l.length) setRanSel(l[0].key);
    }).catch(() => {});
  }, []);

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

  const doConnect = async () => {
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

  const sctp = status?.sctp_estab;
  const sctpCount = status?.sctp_count ?? status?.ran?.sctp_estab ?? 0;

  return (
    <div className="mb-6 glass-card rounded-2xl border border-outline-variant p-4 shadow-sm">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary">link</span>
          <span className="font-bold text-sm">Core↔RAN</span>
          <span className={`ml-2 px-2.5 py-1 rounded-full text-[10px] font-bold ${sctp ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container text-on-surface-variant"}`}>
            {sctp ? `● ESTAB (${sctpCount})` : "○ NO SCTP"}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select value={coreSel} onChange={(e) => setCoreSel(e.target.value)} className="px-3 py-2 rounded-lg border border-outline-variant bg-surface-bright text-sm font-medium">
            {coreProviders.map((p) => <option key={p.key} value={p.key}>{p.label} ({p.key})</option>)}
          </select>
          <span className="text-on-surface-variant">↔</span>
          <select value={ranSel} onChange={(e) => setRanSel(e.target.value)} className="px-3 py-2 rounded-lg border border-outline-variant bg-surface-bright text-sm font-medium">
            {ranProviders.length ? ranProviders.map((p) => <option key={p.key} value={p.key}>{p.label} ({p.key})</option>) : ["oai","srsran"].map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <button onClick={() => doConnect()} disabled={busy} className="px-5 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold shadow-md hover:brightness-110 disabled:opacity-50 flex items-center gap-1">
            {busy ? "..." : <><span className="material-symbols-outlined text-base">bolt</span>Connect</>}
          </button>
        </div>
      </div>
      {msg && <div className={`mt-3 text-xs font-mono px-3 py-2 rounded-lg border ${msgErr ? "bg-error-container text-on-error-container border-error" : "bg-secondary-container text-on-secondary-container border-secondary"}`}>{msg}</div>}
      {status?.ran?.sctp_lines?.length > 0 && <div className="mt-2 text-[11px] font-mono text-on-surface-variant truncate">{status.ran.sctp_lines.slice(0,2).join(" | ")}</div>}
    </div>
  );
}
