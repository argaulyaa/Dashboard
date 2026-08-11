import React, { useEffect, useRef, useState } from "react";
import { Terminal } from "xterm";
import { FitAddon } from "xterm-addon-fit";
import "xterm/css/xterm.css";

export default function SshTerminal({ domain, componentId, host, currentUser }) {
  const containerRef = useRef(null);
  const [form, setForm] = useState({ ssh_username: "", ssh_password: "", port: 22 });
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const termRef = useRef(null);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      termRef.current?.dispose();
    };
  }, []);

  const connect = () => {
    const term = new Terminal({
      convertEol: true,
      fontFamily: "IBM Plex Mono, monospace",
      fontSize: 13,
      theme: { background: "#0e1420" },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    fit.fit();
    termRef.current = term;

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const host =
      window.location.port === "5173"
        ? `${window.location.hostname}:8000`
        : window.location.host;
    const ws = new WebSocket(`${proto}://${host}/ws/ssh/${domain}/${componentId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ user: currentUser, ...form }));
      setConnected(true);
    };
    ws.onmessage = (evt) => term.write(evt.data);
    ws.onclose = () => term.write("\r\n[Connection closed]\r\n");
    ws.onerror = () => term.write("\r\n[WebSocket connection error]\r\n");

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(data);
    });

    const handleResize = () => {
      fit.fit();
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      }
    };
    window.addEventListener("resize", handleResize);
  };

  if (!connected) {
    return (
      <div className="flex flex-col gap-2.5 max-w-xs">
        <p className="text-xs text-dim leading-relaxed">
          Connecting to <strong>{host}</strong> via Console. Credentials are sent directly to the backend and are not stored.
        </p>
        <input
          className="bg-slate-100 border border-panel-border rounded-md text-ink px-2.5 py-1.5 text-xs font-sans focus:outline-none focus:ring-2 focus:ring-restarting/30"
          placeholder="Console Username"
          value={form.ssh_username}
          onChange={(e) => setForm((f) => ({ ...f, ssh_username: e.target.value }))}
        />
        <input
          className="bg-slate-100 border border-panel-border rounded-md text-ink px-2.5 py-1.5 text-xs font-sans focus:outline-none focus:ring-2 focus:ring-restarting/30"
          type="password"
          placeholder="Console Password"
          value={form.ssh_password}
          onChange={(e) => setForm((f) => ({ ...f, ssh_password: e.target.value }))}
        />
        <input
          className="bg-slate-100 border border-panel-border rounded-md text-ink px-2.5 py-1.5 text-xs font-sans focus:outline-none focus:ring-2 focus:ring-restarting/30"
          type="number"
          placeholder="Port (default 22)"
          value={form.port}
          onChange={(e) => setForm((f) => ({ ...f, port: e.target.value }))}
        />
        <button
          className="font-sans text-[13px] font-semibold px-4 py-2.5 rounded-lg border border-restarting/40 bg-transparent text-restarting cursor-pointer w-full hover:bg-restarting/[0.08] disabled:opacity-50 disabled:cursor-not-allowed"
          onClick={connect}
          disabled={!form.ssh_username}
        >
          Connect Console
        </button>
      </div>
    );
  }

  return <div className="bg-[#0e1420] rounded-xl p-2.5 h-[480px]" ref={containerRef} />;
}
