import React, { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  createReservation,
  cancelReservation,
  fetchMyReservations,
  fetchAllReservations,
} from "../api.js";


const DOMAIN_ICON = {
  core: "memory",
  ran: "settings_input_antenna",
  ric: "lan",
};

function formatSlotTime(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const now = new Date();
  const isToday =
    d.getDate() === now.getDate() &&
    d.getMonth() === now.getMonth() &&
    d.getFullYear() === now.getFullYear();

  const timeStr = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  if (isToday) return `Today, ${timeStr}`;

  const monthStr = d.toLocaleDateString([], { month: "short", day: "numeric" });
  return `${monthStr}, ${timeStr}`;
}

function formatFullSlot(startTs, endTs) {
  if (!startTs || !endTs) return "-";
  const startObj = new Date(startTs * 1000);
  const endObj = new Date(endTs * 1000);
  const now = new Date();

  const isToday =
    startObj.getDate() === now.getDate() &&
    startObj.getMonth() === now.getMonth() &&
    startObj.getFullYear() === now.getFullYear();

  const startTime = startObj.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const endTime = endObj.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });

  const dateLabel = isToday ? "Today" : startObj.toLocaleDateString([], { month: "short", day: "numeric" });
  return `${dateLabel} | ${startTime} - ${endTime}`;
}

function computeDurationLabel(startTs, endTs) {
  if (!startTs || !endTs || endTs <= startTs) return "0m";
  const diffMinutes = Math.round((endTs - startTs) / 60);
  const h = Math.floor(diffMinutes / 60);
  const m = diffMinutes % 60;
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0) return `${h}h`;
  return `${m}m`;
}

function initials(name) {
  if (!name) return "?";
  const parts = name.trim().split(" ");
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export default function ReservationPage({ data, currentUser, onReservationChange }) {
  const [myReservations, setMyReservations] = useState([]);
  const [allReservations, setAllReservations] = useState([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState("schedule"); // "reserve" | "schedule" | "book"
  const [targetNode, setTargetNode] = useState(null); // { domain, id, name, host }

  // Modal form states
  const [formDate, setFormDate] = useState("");
  const [formStart, setFormStart] = useState("");
  const [formEnd, setFormEnd] = useState("");
  const [formNote, setFormNote] = useState("");
  const [modalError, setModalError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [cancellingId, setCancellingId] = useState(null);

  // Flatten all components across core, ran, ric
  const allNodes = useMemo(() => {
    const list = [];
    Object.entries(data || {}).forEach(([domain, comps]) => {
      (comps || []).forEach((c) => {
        if (c.id) {
          list.push({ ...c, domain, host: c.host || "127.0.0.1" });
        }
      });
    });
    return list;
  }, [data]);

  const loadReservations = async () => {
    try {
      const [mine, all] = await Promise.all([
        currentUser ? fetchMyReservations(currentUser) : Promise.resolve([]),
        fetchAllReservations(),
      ]);
      setMyReservations(mine);
      setAllReservations(all);
    } catch {
      // Ignore background fetch error
    }
  };

  useEffect(() => {
    loadReservations();
    const interval = setInterval(loadReservations, 5000);
    return () => clearInterval(interval);
  }, [currentUser]);

  // Compute stats
  const activeLocksCount = useMemo(() => {
    return allReservations.filter((r) => r.is_active).length;
  }, [allReservations]);

  const nextAvailableInfo = useMemo(() => {
    const now = Math.floor(Date.now() / 1000);
    if (allNodes.length === 0) return { name: "No nodes", label: "No infrastructure available" };

    // Find the node with the earliest free time
    let earliestNode = allNodes[0];
    let earliestTime = Infinity;

    allNodes.forEach((node) => {
      const nodeRes = allReservations
        .filter((r) => r.domain === node.domain && r.component_id === node.id)
        .sort((a, b) => a.start_at - b.start_at);

      let freeTime = now;
      for (const r of nodeRes) {
        if (freeTime < r.start_at) break;
        if (freeTime < r.end_at) freeTime = r.end_at;
      }
      if (freeTime < earliestTime) {
        earliestTime = freeTime;
        earliestNode = node;
      }
    });

    if (earliestTime <= now + 60) {
      return { name: earliestNode.name, label: "Available Now" };
    }
    return { name: earliestNode.name, label: formatSlotTime(earliestTime) };
  }, [allNodes, allReservations]);

  const openReserveModal = (node, prefillStartTs = null, mode = "schedule") => {
    setModalMode(mode);
    setTargetNode(node || allNodes[0] || null);
    setModalError(null);

    const baseDate = prefillStartTs ? new Date(prefillStartTs * 1000) : new Date();
    const YYYY = baseDate.getFullYear();
    const MM = String(baseDate.getMonth() + 1).padStart(2, "0");
    const DD = String(baseDate.getDate()).padStart(2, "0");
    setFormDate(`${YYYY}-${MM}-${DD}`);

    let startMinutes = baseDate.getHours() * 60 + baseDate.getMinutes();
    if (!prefillStartTs) {
      startMinutes = Math.ceil(startMinutes / 15) * 15; // round up to next 15m
    }
    const startH = String(Math.floor(startMinutes / 60) % 24).padStart(2, "0");
    const startM = String(startMinutes % 60).padStart(2, "0");
    setFormStart(`${startH}:${startM}`);

    const endMinutes = startMinutes + 60; // 1 hour default duration
    const endH = String(Math.floor(endMinutes / 60) % 24).padStart(2, "0");
    const endM = String(endMinutes % 60).padStart(2, "0");
    setFormEnd(`${endH}:${endM}`);

    setFormNote("");
    setModalOpen(true);
  };

  const handleConfirmReservation = async () => {
    if (!targetNode) return;
    if (!currentUser) {
      setModalError("Please log in or set username first.");
      return;
    }
    if (!formDate || !formStart || !formEnd) {
      setModalError("Please fill in date, start time, and end time.");
      return;
    }

    const startTs = new Date(`${formDate}T${formStart}:00`).getTime() / 1000;
    const endTs = new Date(`${formDate}T${formEnd}:00`).getTime() / 1000;

    if (isNaN(startTs) || isNaN(endTs)) {
      setModalError("Invalid date/time selection.");
      return;
    }
    if (startTs >= endTs) {
      setModalError("End time must be after start time.");
      return;
    }
    if (startTs < Date.now() / 1000 - 60) {
      setModalError("Cannot book a time slot in the past.");
      return;
    }

    setSubmitting(true);
    setModalError(null);
    try {
      const result = await createReservation(
        targetNode.domain,
        targetNode.id,
        currentUser,
        startTs,
        endTs,
        formNote
      );
      setModalOpen(false);
      onReservationChange?.(targetNode.domain, targetNode.id, result);
      await loadReservations();
    } catch (err) {
      if (err.payload?.reason === "already_reserved") {
        const c = err.payload.conflict;
        const conflictLabel = c ? formatFullSlot(c.start_at, c.end_at) : "another slot";
        setModalError(`Slot overlaps with existing booking by ${c?.user || "someone"} (${conflictLabel}).`);
      } else {
        setModalError(err.message || "Failed to create reservation.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancelReservation = async (domain, componentId, reservationId) => {
    setCancellingId(reservationId);
    try {
      await cancelReservation(domain, componentId, currentUser, reservationId);
      await loadReservations();
      onReservationChange?.(domain, componentId, null);
    } catch (err) {
      alert(err.message || "Failed to cancel reservation");
    } finally {
      setCancellingId(null);
    }
  };

  // Compute live modal duration
  const modalDurationText = useMemo(() => {
    if (!formDate || !formStart || !formEnd) return "0m";
    const startTs = new Date(`${formDate}T${formStart}:00`).getTime() / 1000;
    const endTs = new Date(`${formDate}T${formEnd}:00`).getTime() / 1000;
    return computeDurationLabel(startTs, endTs);
  }, [formDate, formStart, formEnd]);

  return (
    <div className="max-w-[1600px] mx-auto space-y-gutter">
      {/* Top Title & Header */}
      <div className="mb-4">
        <h2 className="font-headline-md text-headline-md text-on-surface">Node Reservations</h2>
        <p className="font-body-md text-body-md text-on-surface-variant opacity-70">
          Monitor and manage access to RAN infrastructure nodes.
        </p>
      </div>

      {/* Bento Grid Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-gutter">
        <div className="md:col-span-1 bg-surface-container-lowest p-6 rounded-xl border border-outline-variant shadow-sm">
          <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider mb-2">
            Total Nodes
          </p>
          <p className="font-display-lg text-display-lg text-primary">
            {String(allNodes.length).padStart(2, "0")}
          </p>
        </div>
        <div className="md:col-span-1 bg-surface-container-lowest p-6 rounded-xl border border-outline-variant shadow-sm">
          <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider mb-2">
            Active Locks
          </p>
          <p className="font-display-lg text-display-lg text-secondary">
            {String(activeLocksCount).padStart(2, "0")}
          </p>
        </div>
        <div className="md:col-span-2 bg-primary p-6 rounded-xl shadow-lg text-on-primary flex justify-between items-center overflow-hidden relative">
          <div className="relative z-10">
            <p className="font-label-sm text-label-sm text-primary-fixed uppercase tracking-wider mb-2">
              Next Available Slot
            </p>
            <p className="font-headline-md text-headline-md">{nextAvailableInfo.label}</p>
            <p className="font-body-md text-body-md opacity-80">{nextAvailableInfo.name}</p>
          </div>
          <span className="material-symbols-outlined text-[80px] opacity-20 absolute -right-4 -bottom-4">
            schedule
          </span>
        </div>
      </div>

      {/* My Reservations Widget */}
      <div className="bg-surface-container-lowest p-6 rounded-xl border border-outline-variant shadow-sm">
        <h3 className="font-title-md text-title-md text-on-surface mb-4">My Reservations</h3>
        <div className="space-y-3">
          {myReservations.length === 0 && (
            <p className="text-on-surface-variant text-body-md py-4 text-center font-mono">
              You have no active or scheduled reservations.
            </p>
          )}
          {myReservations.map((r) => {
            const comp = allNodes.find((n) => n.domain === r.domain && n.id === r.component_id);
            const compName = comp?.name || r.component_id;
            return (
              <div
                key={r.id}
                className={`flex items-center justify-between p-4 rounded-lg border flex-wrap gap-4 ${
                  r.is_active
                    ? "bg-primary-container/5 border-primary/20"
                    : "bg-surface-container-low border-outline-variant"
                }`}
              >
                <div className="flex items-center gap-4">
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center ${
                      r.is_active
                        ? "bg-primary/10 text-primary"
                        : "bg-surface-container-high text-on-surface-variant"
                    }`}
                  >
                    <span className="material-symbols-outlined">
                      {DOMAIN_ICON[r.domain] || "hub"}
                    </span>
                  </div>
                  <div>
                    <p className="font-title-md text-title-md text-on-surface">{compName}</p>
                    <p className="font-body-md text-body-md text-on-surface-variant">
                      {formatFullSlot(r.start_at, r.end_at)}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  {r.is_active ? (
                    <>
                      <span className="px-3 py-1 bg-secondary-container text-on-secondary-container text-xs font-bold rounded-full">
                        Active Now
                      </span>
                      <Link
                        className="px-4 py-2 bg-primary text-on-primary font-label-lg text-label-lg rounded-lg shadow-md hover:bg-primary-container transition-all"
                        to={`/ssh/${r.domain}/${r.component_id}`}
                      >
                        Console
                      </Link>
                    </>
                  ) : (
                    <>
                      <span className="px-3 py-1 bg-surface-container-highest text-on-surface-variant text-xs font-bold rounded-full">
                        Upcoming
                      </span>
                      <button
                        className="px-4 py-2 border border-outline-variant text-on-surface-variant font-label-lg text-label-lg rounded-lg hover:bg-surface-container transition-all disabled:opacity-50"
                        onClick={() => handleCancelReservation(r.domain, r.component_id, r.id)}
                        disabled={cancellingId === r.id}
                      >
                        {cancellingId === r.id ? "..." : "Cancel"}
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Available Infrastructure Table */}
      <div className="bg-surface-container-lowest rounded-xl border border-outline-variant shadow-[0_4px_12px_rgba(0,0,0,0.06)] overflow-hidden">
        <div className="px-6 py-4 border-b border-outline-variant bg-surface-bright flex items-center justify-between flex-wrap gap-3">
          <h3 className="font-title-md text-title-md text-on-surface">Available Infrastructure</h3>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-container-low text-[11px] uppercase tracking-wider font-bold text-on-surface-variant whitespace-nowrap">
                <th className="px-6 py-3">Node ID</th>
                <th className="px-6 py-3">Type</th>
                <th className="px-6 py-3">Current Owner</th>
                <th className="px-6 py-3">Scheduled Slot</th>
                <th className="px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant text-sm whitespace-nowrap">
              {allNodes.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-6 text-center text-on-surface-variant text-xs font-mono">
                    No components with console access available.
                  </td>
                </tr>
              )}
              {allNodes.map((node) => {
                const nodeRes = allReservations.filter(
                  (r) => r.domain === node.domain && r.component_id === node.id
                );
                const activeRes = nodeRes.find((r) => r.is_active);
                const upcomingRes = nodeRes.filter((r) => r.is_upcoming).sort((a, b) => a.start_at - b.start_at);

                const heldByMe = activeRes && activeRes.user === currentUser;
                const heldByOther = activeRes && !heldByMe;

                // Determine row highlight
                let rowBg = "hover:bg-surface-container-low transition-colors";
                if (heldByMe) {
                  rowBg = "bg-primary-container/5 hover:bg-primary-container/10 transition-colors";
                }

                return (
                  <tr key={`${node.domain}-${node.id}`} className={rowBg}>
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-3">
                        <span className="material-symbols-outlined text-primary text-[20px]">
                          {DOMAIN_ICON[node.domain] || "router"}
                        </span>
                        <span className="font-bold text-sm text-on-surface">{node.name}</span>
                      </div>
                    </td>
                    <td className="px-6 py-3">
                      <span className="px-2 py-0.5 bg-surface-container-high text-on-surface-variant rounded text-[10px] font-bold uppercase tracking-tighter">
                        {node.kind}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-xs">
                      {heldByMe && (
                        <div className="flex items-center gap-2">
                          <div className="w-5 h-5 rounded-full bg-primary flex items-center justify-center text-[9px] font-bold text-white">
                            ME
                          </div>
                          <span className="font-bold">You</span>
                        </div>
                      )}
                      {heldByOther && (
                        <div className="flex items-center gap-2">
                          <div className="w-5 h-5 rounded-full bg-secondary-container flex items-center justify-center text-[9px] font-bold text-on-secondary-container">
                            {initials(activeRes.user)}
                          </div>
                          <span>{activeRes.user}</span>
                        </div>
                      )}
                      {!activeRes && (
                        <span className="text-on-surface-variant italic">
                          Unoccupied
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-3 font-mono text-xs">
                      {activeRes ? (
                        <span className="text-secondary font-bold">
                          {formatSlotTime(activeRes.start_at).replace(", ", " ")} - {new Date(activeRes.end_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })}
                        </span>
                      ) : upcomingRes.length > 0 ? (
                        <span className="text-on-surface-variant">
                          Next: {formatSlotTime(upcomingRes[0].start_at)}
                        </span>
                      ) : (
                        <span className="text-on-surface-variant">
                          No upcoming bookings
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-right">
                      {heldByMe ? (
                        <Link
                          className="px-3 py-1 bg-primary text-on-primary text-xs font-bold rounded-lg shadow hover:bg-primary-container transition-all active:scale-95 inline-block"
                          to={`/ssh/${node.domain}/${node.id}`}
                        >
                          Console
                        </Link>
                      ) : activeRes || upcomingRes.length > 0 ? (
                        <button
                          className="px-3 py-1 border border-primary text-primary text-xs font-bold rounded-lg hover:bg-primary hover:text-white transition-all active:scale-95"
                          onClick={() => {
                            const lastEnd = activeRes
                              ? activeRes.end_at
                              : upcomingRes[upcomingRes.length - 1].end_at;
                            openReserveModal(node, lastEnd, "book");
                          }}
                        >
                          Book Next Slot
                        </button>
                      ) : (
                        <button
                          className="px-3 py-1 bg-secondary text-on-secondary text-xs font-bold rounded-lg shadow hover:opacity-90 transition-all active:scale-95"
                          onClick={() => openReserveModal(node, null, "schedule")}
                        >
                          Book Now
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="px-6 py-4 border-t border-outline-variant flex items-center justify-between text-on-surface-variant">
          <p className="font-label-sm text-label-sm">Showing {allNodes.length} nodes</p>
        </div>
      </div>

      {/* Access Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-on-surface/40 backdrop-blur-sm p-4">
          <div className="bg-surface-container-lowest w-full max-w-md rounded-2xl shadow-2xl border border-outline-variant overflow-hidden">
            <div className="px-6 py-4 border-b border-outline-variant flex items-center justify-between bg-surface-bright">
              <h3 className="font-title-lg text-title-lg text-on-surface">
                {modalMode === "book"
                  ? "Book Next Slot"
                  : modalMode === "schedule"
                  ? "Book Now"
                  : "Reserve Access"}{" "}
                — {targetNode?.name}
              </h3>
              <button
                className="material-symbols-outlined text-on-surface-variant hover:bg-surface-container rounded-full p-1"
                onClick={() => setModalOpen(false)}
              >
                close
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div>
                <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1">
                  Target Component
                </label>
                <div className="w-full p-2.5 bg-surface-container-low border border-outline-variant rounded-lg font-body-md font-bold text-on-surface flex items-center justify-between">
                  <span>{targetNode?.name}</span>
                  <span className="text-xs font-mono font-normal text-on-surface-variant px-2 py-0.5 bg-surface-container rounded uppercase">
                    {targetNode?.domain} &middot; {targetNode?.kind}
                  </span>
                </div>
              </div>

              <div>
                <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1">
                  Date
                </label>
                <input
                  className="w-full p-2.5 bg-surface-container-low border border-outline-variant rounded-lg font-body-md"
                  type="date"
                  value={formDate}
                  onChange={(e) => setFormDate(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1">
                    Start Time
                  </label>
                  <input
                    className="w-full p-2.5 bg-surface-container-low border border-outline-variant rounded-lg font-body-md"
                    type="time"
                    value={formStart}
                    onChange={(e) => setFormStart(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1">
                    End Time
                  </label>
                  <input
                    className="w-full p-2.5 bg-surface-container-low border border-outline-variant rounded-lg font-body-md"
                    type="time"
                    value={formEnd}
                    onChange={(e) => setFormEnd(e.target.value)}
                  />
                </div>
              </div>

              <p className="text-secondary font-label-sm text-label-sm font-bold">
                Duration: {modalDurationText}
              </p>

              <div>
                <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1">
                  Purpose (Optional)
                </label>
                <textarea
                  className="w-full p-2.5 bg-surface-container-low border border-outline-variant rounded-lg font-body-md h-20"
                  placeholder="e.g. Testing Massive MIMO beamforming algorithms..."
                  value={formNote}
                  onChange={(e) => setFormNote(e.target.value)}
                />
              </div>

              {modalError && (
                <div className="p-3 bg-error-container text-on-error-container text-xs rounded-lg font-medium">
                  {modalError}
                </div>
              )}
            </div>

            <div className="px-6 py-4 bg-surface-container-low flex gap-3 justify-end">
              <button
                className="px-6 py-2 text-on-surface-variant font-label-lg text-label-lg hover:bg-surface-container rounded-lg transition-colors"
                onClick={() => setModalOpen(false)}
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                className="px-6 py-2 bg-primary text-on-primary font-label-lg text-label-lg rounded-lg shadow-md hover:bg-primary-container transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={handleConfirmReservation}
                disabled={submitting}
                title=""
              >
                {submitting
                  ? "Booking..."
                  : modalMode === "book" || modalMode === "schedule"
                  ? "Confirm Booking"
                  : "Confirm Reservation"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}