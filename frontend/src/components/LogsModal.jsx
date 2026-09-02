import React, { useEffect, useState, useRef } from "react";
import { fetchComponentLogs, openLogsSocket } from "../api.js";

function parseLine(line) {
  // Extract leading timestamp if present: 2024-02-13 12:34:56, 2024-02-13T12:34:56.123Z, 12:34:56.789, [12:34:56]
  const tsRegex = /^(\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?|\d{2}:\d{2}:\d{2}(?:[.,]\d+)?|\[\d{2}:\d{2}:\d{2}[^\]]*\]|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\s]*)/;
  const m = line.match(tsRegex);
  if (m) {
    return { ts: m[1], rest: line.slice(m[1].length).trimStart() };
  }
  return { ts: null, rest: line };
}

function levelMeta(text) {
  const t = text.toLowerCase();
  if (/(error|err\b|fail|fatal|exception|traceback)/.test(t)) return { label: "ERR", cls: "text-rose-400 bg-rose-950/30 border-rose-900/50" };
  if (/(warn|warning)/.test(t)) return { label: "WRN", cls: "text-amber-300 bg-amber-950/30 border-amber-900/50" };
  if (/(info)/.test(t)) return { label: "INF", cls: "text-sky-300 bg-sky-950/20 border-sky-900/40" };
  if (/(debug|trace)/.test(t)) return { label: "DBG", cls: "text-violet-300 bg-violet-950/20 border-violet-900/40" };
  return null;
}

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
      setLogs((prev) => {
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
        if (evt.code !== 1000 || !hasReceived) {
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
  };

  if (!domain || !compId) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-slate-900/70 backdrop-blur-sm animate-fadeIn">
      {/* outer card */}
      <div className="bg-slate-900 border border-slate-700/60 text-slate-100 rounded-2xl shadow-2xl w-full max-w-5xl max-h-[88vh] flex flex-col overflow-hidden">
        {/* Header — flex-wrap prevents overlap */}
        <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-slate-800 flex flex-wrap items-start sm:items-center justify-between gap-3 bg-slate-950 shrink-0">
          <div className="flex items-start gap-3 min-w-0 flex-1">
            <div className="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center text-primary border border-primary/30 shrink-0">
              <span className="material-symbols-outlined">terminal</span>
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="font-bold text-sm sm:text-base text-white flex flex-wrap items-center gap-2 leading-tight">
                <span className="truncate">{compName || compId.toUpperCase()} Logs</span>
                <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 shrink-0">
                  {domain}/{prov}
                </span>
                {live && wsStatus === "connected" && (
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-900 text-emerald-300 border border-emerald-700 animate-pulse shrink-0">● LIVE</span>
                )}
                {live && wsStatus !== "connected" && (
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 shrink-0">{wsStatus}</span>
                )}
              </h3>
              <p className="text-[11px] sm:text-xs text-slate-400 mt-0.5 leading-snug break-words">Live container & service stdout/stderr — {live ? "streaming" : "snapshot"} · tail {tail}</p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap shrink-0 w-full sm:w-auto justify-start sm:justify-end">
            <button
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-colors border shrink-0 ${live ? "bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-500" : "bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700"}`}
              onClick={() => setLive((v) => !v)}
              title={live ? "Disable live streaming, use snapshot" : "Enable live streaming"}
            >
              <span className={`w-2 h-2 rounded-full ${live ? "bg-white animate-pulse" : "bg-slate-500"}`} />
              Live {live ? "ON" : "OFF"}
            </button>

            <select
              value={tail}
              onChange={handleTailChange}
              className="px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-primary/40 shrink-0"
              title="Lines to tail"
            >
              <option value={100}>tail 100</option>
              <option value={500}>tail 500</option>
            </select>

            {!live && (
              <button
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-colors border border-slate-700 shrink-0"
                onClick={() => loadLogsRest(tail)}
                disabled={loading}
                title="Refresh logs"
              >
                <span className={`material-symbols-outlined text-sm ${loading ? "animate-spin" : ""}`}>refresh</span>
                Refresh
              </button>
            )}
            <button
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-colors border border-slate-700 shrink-0"
              onClick={handleCopy}
              title="Copy all logs"
            >
              <span className="material-symbols-outlined text-sm">{copied ? "check" : "content_copy"}</span>
              <span className="hidden sm:inline">{copied ? "Copied!" : "Copy"}</span>
              <span className="sm:hidden">{copied ? "✓" : "Copy"}</span>
            </button>
            <button
              className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition-colors border border-slate-700 shrink-0"
              onClick={onClose}
              aria-label="Close"
            >
              <span className="material-symbols-outlined text-lg">close</span>
            </button>
          </div>
        </div>

        {/* Toolbar Filter — flex-wrap prevents overlap, proper gap */}
        <div className="px-4 sm:px-6 py-2.5 bg-slate-900 border-b border-slate-800/80 flex flex-wrap items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-2 flex-1 min-w-[180px] max-w-sm">
            <span className="material-symbols-outlined text-slate-500 text-base shrink-0">search</span>
            <input
              type="text"
              placeholder="Filter log lines…"
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-1.5 w-full outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/30 placeholder:text-slate-500"
            />
            {filterText && (
              <button onClick={() => setFilterText("")} className="text-slate-500 hover:text-slate-300 shrink-0">
                <span className="material-symbols-outlined text-sm">close</span>
              </button>
            )}
          </div>
          <div className="flex items-center gap-3 text-[11px] font-mono shrink-0 flex-wrap">
            <span className="text-slate-400 whitespace-nowrap">Showing <b className="text-slate-200">{filteredLines.length}</b> of {lines.length} lines</span>
            {filteredLines.length !== lines.length && <span className="text-amber-400/80 whitespace-nowrap">filtered</span>}
            <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold whitespace-nowrap ${live ? (wsStatus === "connected" ? "bg-emerald-950/50 text-emerald-300 border-emerald-800" : wsStatus==="disconnected" ? "bg-slate-800 text-slate-400 border-slate-700" : "bg-amber-950/40 text-amber-300 border-amber-800") : "bg-slate-800 text-slate-400 border-slate-700"}`}>WS:{wsStatus}</span>
          </div>
        </div>

        {/* Console Log Content Area — fixed: preserve monospaced table with horizontal scroll */}
        <div
          ref={logRef}
          onScroll={handleScroll}
          className="flex-1 min-h-[280px] sm:min-h-[360px] overflow-x-auto overflow-y-auto bg-slate-950 logs-scrollbar"
        >
          <style>{`
            .logs-scrollbar { scrollbar-width: thin; scrollbar-color: #334155 #020617; }
            .logs-scrollbar::-webkit-scrollbar { width: 8px; height: 8px; }
            .logs-scrollbar::-webkit-scrollbar-track { background: #020617; }
            .logs-scrollbar::-webkit-scrollbar-thumb { background: #334155; border-radius: 9999px; border: 1px solid #1e293b; }
            .logs-scrollbar::-webkit-scrollbar-thumb:hover { background: #475569; }
            .logs-scrollbar::-webkit-scrollbar-corner { background: #020617; }
          `}</style>

          {loading && !logs ? (
            <div className="flex flex-col items-center justify-center flex-1 py-16 text-slate-400 gap-3">
              <span className="material-symbols-outlined text-2xl animate-spin">sync</span>
              <p className="text-xs font-mono">{live ? "Connecting live stream…" : "Fetching container logs…"}</p>
              <p className="text-[11px] text-slate-500">domain={domain} · {compId} · {prov} · tail {tail}</p>
            </div>
          ) : error && !logs ? (
            <div className="p-6">
              <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/50 text-rose-300 text-xs leading-relaxed">
                <p className="font-bold flex items-center gap-2 mb-1">
                  <span className="material-symbols-outlined text-sm">error</span>
                  Error loading logs
                </p>
                <p className="break-words whitespace-pre-wrap">{error}</p>
                {live && <p className="mt-2 text-amber-300">Live failed — switching to snapshot fallback.</p>}
              </div>
            </div>
          ) : filteredLines.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center py-16 gap-2">
              <span className="material-symbols-outlined text-slate-600 text-2xl">search_off</span>
              <p className="text-slate-500 italic text-xs">No matching log entries found.</p>
              <p className="text-[11px] text-slate-600 font-mono">{filterText ? `filter: "${filterText}"` : `${lines.length} lines total`}</p>
            </div>
          ) : (
            <div className="min-w-max">
              {/* column header — sticky top, no wrap so table header stays single line */}
              <div className="sticky top-0 z-10 flex items-center gap-0 py-1.5 bg-slate-950/95 backdrop-blur border-b border-slate-800/80 text-[10px] font-semibold tracking-widest uppercase text-slate-500 whitespace-nowrap">
                <span className="w-[3.25rem] sm:w-14 shrink-0 sticky left-0 z-10 bg-slate-950/95 backdrop-blur text-right pr-3 select-none">#</span>
                <span className="w-px self-stretch bg-slate-800/80 shrink-0 sticky left-[3.25rem] sm:left-14 z-10" />
                <span className="pl-3 pr-4">log output — monospaced · scroll → · {filteredLines.length} lines</span>
              </div>

              {filteredLines.map((line, idx) => {
                const isHeartbeat = line.includes("· heartbeat") || (line.includes("heartbeat") && line.includes("waiting for new logs"));
                const { ts, rest } = parseLine(line);
                const lvl = !isHeartbeat ? levelMeta(rest || line) : null;
                const rowBg = idx % 2 === 0 ? "bg-slate-950" : "bg-slate-900/40";
                const lineBg = idx % 2 === 0 ? "bg-slate-950" : "bg-slate-900";
                return (
                  <div
                    key={idx}
                    className={`flex items-start gap-0 group hover:bg-slate-800/60 border-b border-slate-900/50 last:border-0 whitespace-nowrap ${rowBg} ${isHeartbeat ? "opacity-60" : ""}`}
                  >
                    {/* line number — sticky left so it stays fixed while text scrolls horizontally */}
                    <span className={`w-[3.25rem] sm:w-14 shrink-0 sticky left-0 z-[1] text-right pr-3 pl-2 py-[5px] text-[11px] font-mono leading-[1.7] text-slate-600 group-hover:text-slate-400 select-none tabular-nums border-r border-slate-800/60 whitespace-nowrap ${lineBg}`}>
                      {idx + 1}
                    </span>
                    {/* level badge */}
                    {lvl && (
                      <span className={`hidden sm:inline-flex shrink-0 ml-2 mt-[4px] text-[9px] font-bold tracking-wider px-1.5 py-0.5 rounded border leading-none whitespace-nowrap ${lvl.cls}`}>
                        {lvl.label}
                      </span>
                    )}
                    {/* message — whitespace-pre keeps single line per entry, monospaced, horizontal scroll instead of wrapping */}
                    <span className="pl-2 sm:pl-3 pr-6 py-[5px] font-mono text-[12px] leading-[1.7] whitespace-pre select-text">
                      {ts ? (
                        <>
                          <span className="text-slate-500 font-normal">{ts}</span>
                          <span className="text-slate-600">{" · "}</span>
                          <span className={isHeartbeat ? "text-slate-500 italic" : lvl ? "" : "text-slate-200"}>{rest}</span>
                        </>
                      ) : (
                        <span className={isHeartbeat ? "text-slate-500 italic" : lvl ? (lvl.label === "ERR" ? "text-rose-300" : lvl.label === "WRN" ? "text-amber-200" : lvl.label === "INF" ? "text-sky-200" : "text-violet-200") : "text-emerald-300/90"}>{line}</span>
                      )}
                    </span>
                  </div>
                );
              })}
              {/* bottom anchor padding */}
              <div className="h-2" />
            </div>
          )}
        </div>

        {/* Footer — flex-wrap */}
        <div className="px-4 sm:px-6 py-3 border-t border-slate-800 bg-slate-950 flex flex-wrap justify-between items-center gap-3 text-xs text-slate-400 shrink-0">
          <span className="min-w-0 break-words">Component: <strong className="text-slate-200">{compId}</strong> <span className="text-slate-500">provider {prov} · {live ? "live" : "snapshot"} · tail {tail} · {filteredLines.length} lines</span></span>
          <button
            className="px-5 py-1.5 rounded-lg bg-primary text-white font-semibold hover:bg-primary-container transition-colors shrink-0"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
