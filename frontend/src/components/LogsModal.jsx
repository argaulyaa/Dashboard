import React, { useEffect, useState } from "react";
import { fetchComponentLogs } from "../api.js";

function formatTimestamp(ts) {
  if (!ts) return "";
  const date = new Date(ts * 1000);
  return date.toLocaleTimeString("en-US", { hour12: false }) + "." + String(date.getMilliseconds()).padStart(3, "0");
}

export default function LogsModal({ domain, compId, compName, onClose }) {
  const [logs, setLogs] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterText, setFilterText] = useState("");
  const [copied, setCopied] = useState(false);

  const loadLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchComponentLogs(domain, compId, null, 150);
      setLogs(data.logs || "No logs output recorded.");
    } catch (e) {
      setError(e.message || "Failed to load component logs.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (domain && compId) {
      loadLogs();
    }
  }, [domain, compId]);

  const lines = logs.split("\n").filter((l) => l.trim() !== "");
  const filteredLines = filterText
    ? lines.filter((l) => l.toLowerCase().includes(filterText.toLowerCase()))
    : lines;

  const handleCopy = () => {
    navigator.clipboard.writeText(logs);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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
                  {domain}
                </span>
              </h3>
              <p className="text-xs text-slate-400">Live container & service execution stdout/stderr</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-colors"
              onClick={loadLogs}
              disabled={loading}
              title="Refresh Logs"
            >
              <span className={`material-symbols-outlined text-sm ${loading ? "animate-spin" : ""}`}>
                refresh
              </span>
              Refresh
            </button>
            <button
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-colors"
              onClick={handleCopy}
              title="Copy All Logs"
            >
              <span className="material-symbols-outlined text-sm">
                {copied ? "check" : "content_copy"}
              </span>
              {copied ? "Copied!" : "Copy"}
            </button>
            <button
              className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition-colors ml-2"
              onClick={onClose}
            >
              <span className="material-symbols-outlined text-lg">close</span>
            </button>
          </div>
        </div>

        {/* Toolbar Filter */}
        <div className="px-6 py-2.5 bg-slate-900/80 border-b border-slate-800/80 flex items-center justify-between text-xs gap-3">
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
          <span className="text-slate-400 font-mono text-[11px]">
            Showing {filteredLines.length} of {lines.length} lines
          </span>
        </div>

        {/* Console Log Content Area */}
        <div className="p-4 bg-slate-950 flex-1 overflow-y-auto font-mono text-xs text-emerald-400 leading-relaxed select-text min-h-[300px]">
          {loading ? (
            <div className="flex flex-col items-center justify-center h-48 text-slate-400 gap-2">
              <span className="material-symbols-outlined text-2xl animate-spin">sync</span>
              <p>Fetching container logs...</p>
            </div>
          ) : error ? (
            <div className="p-4 rounded-lg bg-rose-950/40 border border-rose-800/50 text-rose-300 text-xs">
              <p className="font-bold flex items-center gap-2 mb-1">
                <span className="material-symbols-outlined text-sm">error</span>
                Error Loading Logs
              </p>
              <p>{error}</p>
            </div>
          ) : filteredLines.length === 0 ? (
            <p className="text-slate-500 italic text-center py-12">No matching log entries found.</p>
          ) : (
            <div className="space-y-1">
              {filteredLines.map((line, idx) => (
                <div key={idx} className="flex gap-3 hover:bg-slate-900/60 px-2 py-0.5 rounded">
                  <span className="text-slate-600 select-none text-[11px] w-8 text-right shrink-0">
                    {idx + 1}
                  </span>
                  <span className="break-all whitespace-pre-wrap">{line}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950 flex justify-between items-center text-xs text-slate-400">
          <span>Component: <strong className="text-slate-200">{compId}</strong></span>
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
