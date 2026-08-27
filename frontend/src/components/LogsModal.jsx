import React, { useEffect, useState, useRef } from "react";
import { fetchComponentLogs, openLogsSocket } from "../api.js";

export default function LogsModal({ domain, compId, compName, provider, onClose }) {
  const [logs, setLogs] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterText, setFilterText] = useState("");
  const [copied, setCopied] = useState(false);
  const [live, setLive] = useState(true);
  const [tail, setTail] = useState(100);
  const [wsStatus, setWsStatus] = useState("connecting");

  const wsRef = useRef(null);
  const logRef = useRef(null);
  const shouldAutoScroll = useRef(true);

  const prov = provider || (domain === "core" ? "oai" : domain === "ran" ? "oai" : "oai");

  const loadLogsRest = async (t = tail) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchComponentLogs(domain, compId, prov, t);
      setLogs(data.logs || "No logs output recorded.");
    } catch (e) {
      setError(e.message || "Failed to load component logs.");
    } finally {
      setLoading(false);
    }
  };

  // Live WS effect
  useEffect(() => {
    if (!domain || !compId) return;
    if (!live) {
      // fallback to REST when live off
      loadLogsRest(tail);
      return;
    }

    setLoading(true);
    setError(null);
    setLogs("");
    setWsStatus("connecting");

    let ws;
    try {
      ws = openLogsSocket(domain, prov, compId, tail);
      wsRef.current = ws;
    } catch (e) {
      setError("Failed to open live stream: " + e.message);
      setLive(false);
      loadLogsRest(tail);
      return;
    }

    let hasReceived = false;
    let fallbackDone = false;
    const fallbackToRest = () => {
      if (fallbackDone) return;
      fallbackDone = true;
      setWsStatus("fallback");
      setLive(false);
      loadLogsRest(tail);
    };

    ws.onopen = () => {
      setWsStatus("connected");
      setLoading(false);
    };
    ws.onmessage = (evt) => {
      const text = evt.data;
      if (!text) return;
      hasReceived = true;
      setLoading(false);
      setWsStatus("connected");
      // Append, handle chunk may contain multiple lines
      setLogs((prev) => {
        // Keep reasonable buffer: truncate if > 500KB
        const next = prev ? prev + text : text;
        if (next.length > 500 * 1024) {
          return next.slice(next.length - 400 * 1024);
        }
        return next;
      });
    };
    ws.onerror = () => {
      setWsStatus("error");
      if (!hasReceived) fallbackToRest();
      else setError("Live stream error — showing buffered logs, retry toggling Live.");
    };
    ws.onclose = (evt) => {
      if (!hasReceived && live && !fallbackDone) {
        // If closed quickly without data, fallback
        // 1000 normal, 1006 abnormal
        if (evt.code !== 1000 || !hasReceived) {
          // Only fallback if we never got data; otherwise just mark disconnected
          setTimeout(() => {
            if (!hasReceived) fallbackToRest();
          }, 500);
        }
      }
      if (hasReceived) setWsStatus("disconnected");
      else if (!fallbackDone) setWsStatus("closed");
    };

    return () => {
      try { ws.close(); } catch {}
      wsRef.current = null;
    };
  }, [domain, compId, prov, live, tail]);

  // Auto-scroll when logs change
  useEffect(() => {
    if (logRef.current && shouldAutoScroll.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs]);

  const handleScroll = () => {
    if (!logRef.current) return;
    const el = logRef.current;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    shouldAutoScroll.current = nearBottom;
  };

  const lines = logs.split("\n").filter((l) => l.trim() !== "");
  const filteredLines = filterText
    ? lines.filter((l) => l.toLowerCase().includes(filterText.toLowerCase()))
    : lines;

  const handleCopy = () => {
    navigator.clipboard.writeText(logs);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleTailChange = (e) => {
    const v = parseInt(e.target.value, 10);
    setTail(v);
    // WS will reconnect via effect
  };

  if (!domain || !compId) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fadeIn">
      <div className="bg-slate-900 border border-slate-700/60 text-slate-100 rounded-2xl shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950 flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center text-primary border border-primary/30">
              <span className="material-symbols-outlined">terminal</span>
            </div>
            <div>
              <h3 className="font-bold text-base text-white flex items-center gap-2">
                {compName || compId.toUpperCase()} Logs
                <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                  {domain}/{prov}
                </span>
                {live && wsStatus === "connected" && (
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-900 text-emerald-300 border border-emerald-700 animate-pulse">● LIVE</span>
                )}
              </h3>
              <p className="text-xs text-slate-400">Live container & service execution stdout/stderr {live ? "— streaming" : "— snapshot"}</p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Live toggle */}
            <button
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-colors border ${live ? "bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-500" : "bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700"}`}
              onClick={() => setLive((v) => !v)}
              title={live ? "Disable live streaming, use snapshot" : "Enable live streaming"}
            >
              <span className={`w-2 h-2 rounded-full ${live ? "bg-white animate-pulse" : "bg-slate-500"}`} />
              Live {live ? "ON" : "OFF"}
            </button>

            {/* Tail selector */}
            <select
              value={tail}
              onChange={handleTailChange}
              className="px-2 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold"
              title="Lines to tail"
            >
              <option value={100}>tail 100</option>
              <option value={500}>tail 500</option>
            </select>

            {!live && (
              <button
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-colors"
                onClick={() => loadLogsRest(tail)}
                disabled={loading}
                title="Refresh Logs"
              >
                <span className={`material-symbols-outlined text-sm ${loading ? "animate-spin" : ""}`}>refresh</span>
                Refresh
              </button>
            )}
            <button
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-colors"
              onClick={handleCopy}
              title="Copy All Logs"
            >
              <span className="material-symbols-outlined text-sm">{copied ? "check" : "content_copy"}</span>
              {copied ? "Copied!" : "Copy"}
            </button>
            <button
              className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition-colors ml-1"
              onClick={onClose}
            >
              <span className="material-symbols-outlined text-lg">close</span>
            </button>
          </div>
        </div>

        {/* Toolbar Filter */}
        <div className="px-6 py-2.5 bg-slate-900/80 border-b border-slate-800/80 flex items-center justify-between text-xs gap-3 flex-wrap">
          <div className="flex items-center gap-2 flex-1 max-w-xs">
            <span className="material-symbols-outlined text-slate-500 text-base">search</span>
            <input
              type="text"
              placeholder="Filter log lines..."
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-md px-2.5 py-1 w-full outline-none focus:border-primary/60"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-slate-400 font-mono text-[11px]">Showing {filteredLines.length} of {lines.length} lines</span>
            {live && <span className="text-[11px] text-emerald-400 font-mono">WS:{wsStatus}</span>}
          </div>
        </div>

        {/* Console Log Content Area */}
        <div ref={logRef} onScroll={handleScroll} className="p-4 bg-slate-950 flex-1 overflow-y-auto font-mono text-xs text-emerald-400 leading-relaxed select-text min-h-[300px]">
          {loading && !logs ? (
            <div className="flex flex-col items-center justify-center h-48 text-slate-400 gap-2">
              <span className="material-symbols-outlined text-2xl animate-spin">sync</span>
              <p>{live ? "Connecting live stream..." : "Fetching container logs..."}</p>
            </div>
          ) : error && !logs ? (
            <div className="p-4 rounded-lg bg-rose-950/40 border border-rose-800/50 text-rose-300 text-xs">
              <p className="font-bold flex items-center gap-2 mb-1">
                <span className="material-symbols-outlined text-sm">error</span>
                Error Loading Logs
              </p>
              <p>{error}</p>
              {live && <p className="mt-2 text-amber-300">Live failed — toggled to snapshot fallback.</p>}
            </div>
          ) : filteredLines.length === 0 ? (
            <p className="text-slate-500 italic text-center py-12">No matching log entries found.</p>
          ) : (
            <div className="space-y-1">
              {filteredLines.map((line, idx) => {
                const isHeartbeat = line.includes("· heartbeat") || (line.includes("heartbeat") && line.includes("waiting for new logs"));
                return (
                <div key={idx} className="flex gap-3 hover:bg-slate-900/60 px-2 py-0.5 rounded">
                  <span className="text-slate-600 select-none text-[11px] w-8 text-right shrink-0">{idx + 1}</span>
                  <span className={`break-all whitespace-pre-wrap ${isHeartbeat ? "text-slate-500 italic opacity-70" : ""}`}>{line}</span>
                </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950 flex justify-between items-center text-xs text-slate-400">
          <span>Component: <strong className="text-slate-200">{compId}</strong> <span className="text-slate-500">provider {prov} • {live ? "live" : "snapshot"} • tail {tail}</span></span>
          <button
            className="px-5 py-1.5 rounded-lg bg-primary text-white font-semibold hover:bg-primary-container transition-colors"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
