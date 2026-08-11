import React from "react";

const WS_LABEL = {
  live: "Telemetry live",
  connecting: "Connecting...",
  offline: "Disconnected",
};

const WS_DOT = {
  live: "bg-secondary animate-pulse",
  connecting: "bg-tertiary",
  offline: "bg-error",
};

export default function TopBar({ wsStatus }) {
  return (
    <header className="fixed top-0 right-0 h-16 md:ml-sidebar-width w-full md:w-[calc(100%-280px)] bg-surface-bright border-b border-outline-variant flex justify-between items-center px-gutter z-40">
      <div className="flex items-center flex-grow max-w-xl">
        <div className="relative w-full hidden sm:block">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-[20px]">
            search
          </span>
          <input
            className="w-full bg-surface-container-low border-none rounded-xl pl-10 pr-4 py-2 text-body-md focus:ring-2 focus:ring-primary-container"
            placeholder="Search infrastructure..."
            type="text"
          />
        </div>
      </div>
      <div className="flex items-center gap-4 ml-gutter">
        <div className="hidden md:flex items-center gap-2 bg-secondary-container px-3 py-1 rounded-full text-on-secondary-container">
          <span className={`w-2 h-2 rounded-full ${WS_DOT[wsStatus] || WS_DOT.connecting}`} />
          <span className="font-label-sm">{WS_LABEL[wsStatus] || WS_LABEL.connecting}</span>
        </div>
        <button className="material-symbols-outlined text-on-surface-variant hover:text-primary transition-all" title="Notifikasi">
          notifications
        </button>
        <button className="material-symbols-outlined text-on-surface-variant hover:text-primary transition-all" title="Bantuan">
          help_outline
        </button>
      </div>
    </header>
  );
}