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

export default function ReservationPage({ currentUser }) {
  const role = getRole();
  const isAdmin = currentUser === "admin" || role === "admin";

  // time-only booking form
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");

  const [myBookings, setMyBookings] = useState([]);
  const [allBookings, setAllBookings] = useState([]);
  const [activeBooking, setActiveBooking] = useState(null);
  const [err, setErr] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [adminFilter, setAdminFilter] = useState("active");

  const load = async () => {
    try {
      const mine = await fetchMyBookings();
      setMyBookings(mine);
      const act = mine.find((b) => b.is_active) || null;
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
    } catch {
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

  // #8 admin filter tabs derived counts + filtered list
  const adminCounts = useMemo(() => {
    const c = { active: 0, upcoming: 0, done: 0 };
    allBookings.forEach((b) => {
      if (b.status === "active") c.active += 1;
      else if (b.status === "pending") c.upcoming += 1;
      else if (["done", "cancelled", "rejected"].includes(b.status)) c.done += 1;
    });
    return c;
  }, [allBookings]);

  const filteredAllBookings = useMemo(() => {
    if (adminFilter === "active") return allBookings.filter((b) => b.status === "active");
    if (adminFilter === "upcoming") return allBookings.filter((b) => b.status === "pending");
    if (adminFilter === "done") return allBookings.filter((b) => ["done", "cancelled", "rejected"].includes(b.status));
    return allBookings;
  }, [allBookings, adminFilter]);

  const handleBook = async (e) => {
    e.preventDefault();
    setErr("");
    setOkMsg("");
    if (!startAt || !endAt) { setErr("Fill start and end time"); return; }
    const startTs = new Date(startAt).getTime() / 1000;
    const endTs = new Date(endAt).getTime() / 1000;
    if (isNaN(startTs) || isNaN(endTs) || startTs >= endTs) { setErr("Invalid time range"); return; }
    if ((endTs - startTs) > 3600) { setErr("Max 1 hour per booking (3600s) exceeded"); return; }
    setLoading(true);
    try {
      await bookReservation(startTs, endTs);
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

  return (
    <div className="max-w-[1600px] mx-auto space-y-6">
      <div>
        <h2 className="font-headline-md text-headline-md text-on-surface">Reservation Booking</h2>
      </div>

      {/* Active Session — time & status only, no provider pick */}
      {activeBooking ? (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-emerald-800">Active Session</p>
            <p className="text-sm text-emerald-700">{formatTime(activeBooking.start_at)} → {formatTime(activeBooking.end_at)}</p>
            <p className="text-xs text-emerald-600">Status: {activeBooking.status} • remaining {formatCountdown(Math.floor(activeRemaining))}</p>
            <p className="mt-1 text-xs text-emerald-700">Provider choice: go to <a href="#/core" className="underline font-bold">Core → Core↔RAN bar</a> to connect.</p>
          </div>
          <div className="text-right">
            <p className="text-2xl font-mono font-bold text-emerald-800">{formatCountdown(Math.floor(activeRemaining))}</p>
            <p className="text-xs text-emerald-600">time remaining</p>
          </div>
        </div>
      ) : (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <p className="text-sm text-amber-800">No active reservation — book a slot and wait for admin approval. {isAdmin && "Admin can connect via Core page without booking."}</p>
          <p className="text-xs text-amber-700 mt-1">Provider (Core/RAN) is chosen on the <a href="#/core" className="underline font-bold">Core page</a> after your session is active.</p>
        </div>
      )}

      {/* Book Session form — time only, no provider dropdowns */}
      <div className="bg-white rounded-xl border border-outline-variant shadow-sm p-6">
        <h3 className="font-title-md text-title-md mb-4">Book Session</h3>
        <form onSubmit={handleBook} className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
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
        <p className="mt-2 text-xs text-on-surface-variant">Session-only: booking reserves time on the single B210 testbed. Overlap with any pending/active booking → 409 Slot taken. Provider (Core/RAN) chosen on Core page at connect time.</p>
      </div>

      {/* My Bookings — time only */}
      <div className="bg-white rounded-xl border border-outline-variant shadow-sm p-6">
        <h3 className="font-title-md text-title-md mb-4">My Bookings</h3>
        {myBookings.length === 0 ? (
          <p className="text-sm text-on-surface-variant py-4 text-center">No bookings yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-container-low text-[11px] uppercase tracking-wider font-bold text-on-surface-variant">
                <tr><th className="px-4 py-2">ID</th><th className="px-4 py-2">Start</th><th className="px-4 py-2">End</th><th className="px-4 py-2">Status</th><th className="px-4 py-2">Remaining</th><th className="px-4 py-2 text-right">Action</th></tr>
              </thead>
              <tbody className="divide-y divide-outline-variant">
                {myBookings.map((b) => (
                  <tr key={b.id} className={b.is_active ? "bg-emerald-50" : ""}>
                    <td className="px-4 py-2 font-mono text-xs">{b.id}</td>
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

      {/* Admin view — user + time only, filter tabs active/upcoming/done, 1-click Approve/Reject */}
      {isAdmin && (
        <div className="bg-white rounded-xl border border-outline-variant shadow-sm p-6">
          <h3 className="font-title-md text-title-md mb-4">All Bookings (Admin)</h3>
          <div className="flex gap-1 border-b border-outline-variant mb-4">
            {[
              { key: "active", label: "Active" },
              { key: "upcoming", label: "Upcoming" },
              { key: "done", label: "Done" },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => setAdminFilter(tab.key)}
                className={`px-4 py-2 text-sm font-bold border-b-2 -mb-px transition-colors ${adminFilter === tab.key ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}
              >
                {tab.label} ({adminCounts[tab.key]})
              </button>
            ))}
          </div>
          {allBookings.length === 0 ? (
            <p className="text-sm text-on-surface-variant py-4 text-center">No bookings.</p>
          ) : filteredAllBookings.length === 0 ? (
            <p className="text-sm text-on-surface-variant py-4 text-center">No {adminFilter} bookings.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-surface-container-low text-[11px] uppercase tracking-wider font-bold text-on-surface-variant">
                  <tr><th className="px-4 py-2">User</th><th className="px-4 py-2">Start → End</th><th className="px-4 py-2">Status</th><th className="px-4 py-2 text-right">Actions</th></tr>
                </thead>
                <tbody className="divide-y divide-outline-variant">
                  {filteredAllBookings.map((b) => (
                    <tr key={b.id}>
                      <td className="px-4 py-2 font-bold">{b.user}</td>
                      <td className="px-4 py-2 text-xs">{formatTime(b.start_at)} → {formatTime(b.end_at)}</td>
                      <td className="px-4 py-2"><span className={`px-2 py-0.5 rounded-full text-xs border font-bold ${statusBadge(b.status)}`}>{b.status}</span></td>
                      <td className="px-4 py-2 text-right space-x-2">
                        {b.status === "pending" && <>
                          <button onClick={() => handleApprove(b.id)} className="px-3 py-1 bg-emerald-600 text-white rounded-lg text-xs font-bold hover:bg-emerald-700">Approve</button>
                          <button onClick={() => handleReject(b.id)} className="px-3 py-1 bg-red-600 text-white rounded-lg text-xs font-bold hover:bg-red-700">Reject</button>
                        </>}
                        {(b.status === "pending" || b.status === "active") && <button onClick={() => handleCancel(b.id)} className="px-3 py-1 border rounded-lg text-xs font-bold hover:bg-surface-container">Cancel</button>}
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
