import React, { useState, useEffect, useMemo } from "react";
import { getRole } from "../user.js";
import {
  bookReservation,
  fetchMyBookings,
  fetchAllBookings,
  fetchActiveBooking,
  approveBooking,
  rejectBooking,
  cancelBooking,
  connectRan,
  disconnectRan,
  fetchProviders,
} from "../api.js";

function formatTime(ts) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
function formatCountdown(sec) {
  if (sec <= 0) return "00:00:00";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
function statusBadge(s) {
  const map = {
    pending: "bg-amber-100 text-amber-800 border-amber-200",
    active: "bg-emerald-100 text-emerald-800 border-emerald-200",
    done: "bg-gray-100 text-gray-600 border-gray-200",
    cancelled: "bg-red-100 text-red-700 border-red-200",
    rejected: "bg-red-100 text-red-700 border-red-200",
  };
  return map[s] || "bg-gray-100 text-gray-600";
}

export default function ReservationPage({ data, currentUser }) {
  const role = getRole();
  const isAdmin = currentUser === "admin" || role === "admin";

  // providers for dropdowns
  const [coreProviders, setCoreProviders] = useState([]);
  const [ranProviders, setRanProviders] = useState([]);
  useEffect(() => {
    fetchProviders("core").then(setCoreProviders).catch(() => setCoreProviders([{ key: "oai", label: "OAI" }]));
    fetchProviders("ran").then(setRanProviders).catch(() => setRanProviders([{ key: "oai", label: "OAI" }]));
  }, []);

  // form
  const [coreProv, setCoreProv] = useState("");
  const [ranProv, setRanProv] = useState("");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  useEffect(() => {
    if (coreProviders.length && !coreProv) setCoreProv(coreProviders[0].key);
  }, [coreProviders]);
  useEffect(() => {
    if (ranProviders.length && !ranProv) setRanProv(ranProviders[0].key);
  }, [ranProviders]);

  const [myBookings, setMyBookings] = useState([]);
  const [allBookings, setAllBookings] = useState([]);
  const [activeBooking, setActiveBooking] = useState(null);
  const [err, setErr] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [connectBusy, setConnectBusy] = useState(false);

  const load = async () => {
    try {
      const mine = await fetchMyBookings();
      setMyBookings(mine);
      const act = mine.find((b) => b.is_active) || null;
      // also try /active endpoint for authoritative
      try {
        const a = await fetchActiveBooking();
        if (a) setActiveBooking(a);
        else setActiveBooking(act);
      } catch {
        setActiveBooking(act);
      }
      if (isAdmin) {
        const all = await fetchAllBookings();
        setAllBookings(all);
      }
    } catch (e) {
      // ignore
    }
  };
  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [isAdmin]);

  // countdown tick
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const activeRemaining = useMemo(() => {
    if (!activeBooking) return 0;
    return Math.max(0, Math.floor(activeBooking.end_at * 1000 - now) / 1000);
  }, [activeBooking, now]);

  const handleBook = async (e) => {
    e.preventDefault();
    setErr(""); setOkMsg("");
    if (!coreProv || !ranProv || !startAt || !endAt) { setErr("Fill core, ran, start and end"); return; }
    const startTs = new Date(startAt).getTime() / 1000;
    const endTs = new Date(endAt).getTime() / 1000;
    if (isNaN(startTs) || isNaN(endTs) || startTs >= endTs) { setErr("Invalid time range"); return; }
    setLoading(true);
    try {
      await bookReservation(coreProv, ranProv, startTs, endTs);
      setOkMsg("Booking created (pending approval)");
      setStartAt(""); setEndAt("");
      await load();
    } catch (ex) {
      const msg = ex.payload?.message || ex.message || "Book failed";
      if (ex.status === 409) setErr(`Slot taken: ${msg}`);
      else setErr(msg);
    } finally { setLoading(false); }
  };

  const handleCancel = async (id) => {
    try { await cancelBooking(id); await load(); } catch (ex) { alert(ex.payload?.message || ex.message); }
  };
  const handleApprove = async (id) => {
    try { await approveBooking(id); await load(); } catch (ex) { alert(ex.payload?.message || ex.message); }
  };
  const handleReject = async (id) => {
    try { await rejectBooking(id); await load(); } catch (ex) { alert(ex.payload?.message || ex.message); }
  };
  const handleConnect = async (disco = false) => {
    if (!activeBooking && !isAdmin) { alert("No active reservation"); return; }
    const cp = activeBooking ? activeBooking.core_provider : coreProv;
    const rp = activeBooking ? activeBooking.ran_provider : ranProv;
    setConnectBusy(true);
    try {
      const res = disco ? await disconnectRan(cp, rp) : await connectRan(cp, rp, false);
      alert(`${disco ? "Disconnect" : "Connect"}: ${res.status || "ok"} ${res.sctp_estab ? "(SCTP ESTAB)" : ""}`);
    } catch (ex) {
      const m = ex.payload?.message || ex.message;
      alert(`Failed: ${m}`);
    } finally { setConnectBusy(false); }
  };

  return (
    <div className="max-w-[1600px] mx-auto space-y-6">
      <div>
        <h2 className="font-headline-md text-headline-md text-on-surface">Reservation Booking</h2>
        <p className="text-on-surface-variant opacity-70">Book exclusive Core↔RAN session to prevent concurrent gNB/Core chaos.</p>
      </div>

      {/* Active countdown */}
      {activeBooking ? (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-emerald-800">Active Session</p>
            <p className="text-sm text-emerald-700">{activeBooking.core_provider} / {activeBooking.ran_provider} • {formatTime(activeBooking.start_at)} → {formatTime(activeBooking.end_at)}</p>
            <p className="text-xs text-emerald-600">Status: {activeBooking.status} • remaining {formatCountdown(Math.floor(activeRemaining))}</p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => handleConnect(false)} disabled={connectBusy || (!isAdmin && !activeBooking?.is_active)} className="px-5 py-2 bg-emerald-600 text-white rounded-lg font-bold disabled:opacity-40 hover:bg-emerald-700">
              {connectBusy ? "..." : "Connect now"}
            </button>
            <button onClick={() => handleConnect(true)} disabled={connectBusy} className="px-4 py-2 border border-emerald-600 text-emerald-700 rounded-lg font-bold disabled:opacity-40">Disconnect</button>
          </div>
        </div>
      ) : (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-center justify-between gap-4">
          <p className="text-sm text-amber-800">No active reservation — book a slot and wait for admin approval. {isAdmin && "Admin can connect without booking."}</p>
          <button onClick={() => handleConnect(false)} disabled={!isAdmin || connectBusy} className={`px-4 py-2 rounded-lg font-bold ${isAdmin ? "bg-primary text-white" : "bg-gray-200 text-gray-400 cursor-not-allowed"}`} title={isAdmin ? "Admin bypass" : "Only active session can connect"}>
            Connect {isAdmin ? "(admin bypass)" : "(need active)"}
          </button>
        </div>
      )}

      {/* Book Session form */}
      <div className="bg-white rounded-xl border border-outline-variant shadow-sm p-6">
        <h3 className="font-title-md text-title-md mb-4">Book Session</h3>
        <form onSubmit={handleBook} className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Core Provider</label>
            <select value={coreProv} onChange={(e) => setCoreProv(e.target.value)} className="w-full mt-1 px-3 py-2 border border-outline-variant rounded-lg bg-white">
              {coreProviders.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">RAN Provider</label>
            <select value={ranProv} onChange={(e) => setRanProv(e.target.value)} className="w-full mt-1 px-3 py-2 border border-outline-variant rounded-lg bg-white">
              {ranProviders.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Start</label>
            <input type="datetime-local" value={startAt} onChange={(e) => setStartAt(e.target.value)} className="w-full mt-1 px-3 py-2 border border-outline-variant rounded-lg" />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">End</label>
            <input type="datetime-local" value={endAt} onChange={(e) => setEndAt(e.target.value)} className="w-full mt-1 px-3 py-2 border border-outline-variant rounded-lg" />
          </div>
          <button type="submit" disabled={loading} className="px-6 py-2 bg-primary text-white rounded-lg font-bold disabled:opacity-50 hover:bg-primary/90">
            {loading ? "Booking..." : "Book"}
          </button>
        </form>
        {err && <p className="mt-3 text-sm text-red-600 font-mono">{err}</p>}
        {okMsg && <p className="mt-3 text-sm text-emerald-600">{okMsg}</p>}
        <p className="mt-2 text-xs text-on-surface-variant">Overlap with any pending/active booking → 409 Slot taken.</p>
      </div>

      {/* My Bookings */}
      <div className="bg-white rounded-xl border border-outline-variant shadow-sm p-6">
        <h3 className="font-title-md text-title-md mb-4">My Bookings</h3>
        {myBookings.length === 0 ? (
          <p className="text-sm text-on-surface-variant py-4 text-center">No bookings yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-container-low text-[11px] uppercase tracking-wider font-bold text-on-surface-variant">
                <tr><th className="px-4 py-2">ID</th><th className="px-4 py-2">Core</th><th className="px-4 py-2">RAN</th><th className="px-4 py-2">Start</th><th className="px-4 py-2">End</th><th className="px-4 py-2">Status</th><th className="px-4 py-2">Remaining</th><th className="px-4 py-2 text-right">Action</th></tr>
              </thead>
              <tbody className="divide-y divide-outline-variant">
                {myBookings.map((b) => (
                  <tr key={b.id} className={b.is_active ? "bg-emerald-50" : ""}>
                    <td className="px-4 py-2 font-mono text-xs">{b.id}</td>
                    <td className="px-4 py-2">{b.core_provider}</td>
                    <td className="px-4 py-2">{b.ran_provider}</td>
                    <td className="px-4 py-2">{formatTime(b.start_at)}</td>
                    <td className="px-4 py-2">{formatTime(b.end_at)}</td>
                    <td className="px-4 py-2"><span className={`px-2 py-0.5 rounded-full text-xs border font-bold ${statusBadge(b.status)}`}>{b.status}</span>{b.is_active && <span className="ml-2 text-xs font-bold text-emerald-600 animate-pulse">● ACTIVE {formatCountdown(b.remaining_seconds)}</span>}</td>
                    <td className="px-4 py-2 font-mono text-xs">{b.is_active ? formatCountdown(b.remaining_seconds) : "-"}</td>
                    <td className="px-4 py-2 text-right">
                      {(b.status === "pending" || b.status === "active") && <button onClick={() => handleCancel(b.id)} className="px-3 py-1 border border-outline-variant rounded-lg text-xs font-bold hover:bg-surface-container">Cancel</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Admin view */}
      {isAdmin && (
        <div className="bg-white rounded-xl border border-outline-variant shadow-sm p-6">
          <h3 className="font-title-md text-title-md mb-4">All Bookings (Admin)</h3>
          {allBookings.length === 0 ? (
            <p className="text-sm text-on-surface-variant py-4 text-center">No bookings.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-surface-container-low text-[11px] uppercase tracking-wider font-bold text-on-surface-variant">
                  <tr><th className="px-4 py-2">User</th><th className="px-4 py-2">Core/RAN</th><th className="px-4 py-2">Start → End</th><th className="px-4 py-2">Status</th><th className="px-4 py-2 text-right">Actions</th></tr>
                </thead>
                <tbody className="divide-y divide-outline-variant">
                  {allBookings.map((b) => (
                    <tr key={b.id}>
                      <td className="px-4 py-2 font-bold">{b.user}</td>
                      <td className="px-4 py-2">{b.core_provider}/{b.ran_provider}</td>
                      <td className="px-4 py-2 text-xs">{formatTime(b.start_at)} → {formatTime(b.end_at)}</td>
                      <td className="px-4 py-2"><span className={`px-2 py-0.5 rounded-full text-xs border font-bold ${statusBadge(b.status)}`}>{b.status}</span></td>
                      <td className="px-4 py-2 text-right space-x-2">
                        {b.status === "pending" && <>
                          <button onClick={() => handleApprove(b.id)} className="px-3 py-1 bg-emerald-600 text-white rounded-lg text-xs font-bold">Approve</button>
                          <button onClick={() => handleReject(b.id)} className="px-3 py-1 bg-red-600 text-white rounded-lg text-xs font-bold">Reject</button>
                        </>}
                        {(b.status === "pending" || b.status === "active") && <button onClick={() => handleCancel(b.id)} className="px-3 py-1 border rounded-lg text-xs font-bold">Cancel</button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
