import React, { useState } from "react";
import { NavLink } from "react-router-dom";
import { setUser, getRole } from "../user.js";

const NAV_ITEMS = [
  { to: "/", label: "Overview", icon: "dashboard", end: true },
  { to: "/core", label: "Core", icon: "memory" },
  { to: "/ran", label: "RAN", icon: "settings_input_antenna" },
  { to: "/ric", label: "RIC", icon: "lan" },
  { to: "/reservations", label: "Reservation", icon: "event_available" },
  { to: "/audit-logs", label: "Audit Logs", icon: "shield" },
  { to: "/profile", label: "Profile", icon: "account_circle" },
];

export default function Sidebar({ currentUser, onUserChange, onLogout }) {
  const [editing, setEditing] = useState(!currentUser);
  const [value, setValue] = useState(currentUser || "");

  const role = getRole();
  const isAdmin = currentUser === "admin" || role === "admin";
  const initials = (currentUser || "?").trim().slice(0, 2).toUpperCase();

  const visibleNavItems = NAV_ITEMS.filter((item) => {
    if (item.to === "/reservations" && !(role === "user" || role === "admin")) return false;
    if (item.to === "/audit-logs" && !isAdmin) return false;
    return true;
  });

  return (
    <aside className="fixed left-0 top-0 h-full w-sidebar-width bg-surface shadow-[0_4px_12px_rgba(0,0,0,0.06)] flex-col border-r border-outline-variant hidden md:flex z-50">
      <div className="p-gutter flex items-center gap-3">
        <div className="w-10 h-10 bg-primary-container rounded-lg flex items-center justify-center text-white shrink-0">
          <span className="material-symbols-outlined text-title-lg">settings_input_antenna</span>
        </div>
        <div>
          <h1 className="font-title-lg text-title-lg font-bold text-primary leading-tight">Open RAN</h1>
          <p className="text-label-sm text-on-surface-variant opacity-70">Control Panel</p>
        </div>
      </div>

      <nav className="mt-8 flex-grow">
        {visibleNavItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `flex items-center px-gutter py-4 transition-colors border-r-4 ${
                isActive
                  ? "sidebar-item-active bg-surface-container-low border-primary"
                  : "text-on-surface-variant border-transparent hover:bg-surface-container-low"
              }`
            }
          >
            <span className="material-symbols-outlined mr-3">{item.icon}</span>
            <span className="font-body-md">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="p-gutter border-t border-outline-variant">
        {editing ? (
          <div className="flex items-center gap-2">
            <input
              className="w-full bg-surface-container-low border-none rounded-lg text-on-surface px-3 py-2 text-body-md focus:outline-none focus:ring-2 focus:ring-primary-container"
              placeholder="Your name..."
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && save()}
              autoFocus
            />
            <button
              className="shrink-0 px-3 py-2 rounded-lg bg-primary-container text-white text-label-sm font-semibold"
              onClick={save}
            >
              OK
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-3">
            <button
              className="flex items-center gap-3 min-w-0 bg-transparent"
              onClick={() => {
                setValue(currentUser || "");
                setEditing(true);
              }}
              title="Change username"
            >
              <div className="w-10 h-10 rounded-full bg-surface-container-highest text-primary flex items-center justify-center font-title-md shrink-0">
                {initials}
              </div>
              <div className="text-left min-w-0">
                <p className="font-title-md text-title-md text-on-surface truncate">{currentUser}</p>
                <span className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                  role === "admin" ? "bg-primary/10 text-primary" : "bg-primary/10 text-primary"
                }`}>
                  {role === "user" || role === "admin" ? role : "user"}
                </span>
              </div>
            </button>
            <button
              className="p-2 text-primary hover:bg-primary-fixed rounded-lg transition-colors flex items-center justify-center shrink-0"
              title="Logout"
              onClick={onLogout}
            >
              <span className="material-symbols-outlined">logout</span>
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}