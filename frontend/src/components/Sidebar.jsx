import React, { useEffect, useState } from "react";
import { NavLink, Link } from "react-router-dom";
import { getRole } from "../user.js";
import { fetchMe } from "../auth.js";

const NAV_ITEMS = [
  { to: "/", label: "Overview", icon: "dashboard", end: true },
  { to: "/core", label: "Core", icon: "memory" },
  { to: "/ran", label: "RAN", icon: "settings_input_antenna" },
  { to: "/ric", label: "RIC", icon: "lan" },
  { to: "/remote-devices", label: "Remote Devices", icon: "phonelink" },
  { to: "/reservations", label: "Reservation", icon: "event_available" },
  { to: "/audit-logs", label: "Audit Logs", icon: "shield" },
];

export default function Sidebar({
  currentUser,
  fullName: fullNameProp,
  onUserChange,
  onLogout,
  darkMode,
  onToggleTheme,
}) {
  const role = getRole();
  const isAdmin = currentUser === "admin" || role === "admin";

  // displayName = full_name from /api/auth/me, fallback to username if empty, never email
  const [displayName, setDisplayName] = useState(() => {
    const f = (fullNameProp || "").trim();
    if (f) return f;
    return currentUser || "";
  });

  useEffect(() => {
    const propFn = (fullNameProp || "").trim();
    if (propFn) {
      setDisplayName(propFn);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const me = await fetchMe();
        if (cancelled) return;
        const fn = (me?.full_name || "").trim();
        if (fn) setDisplayName(fn);
        else setDisplayName(currentUser || "");
      } catch {
        if (!cancelled) setDisplayName(currentUser || "");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [currentUser, fullNameProp]);

  const initials = (displayName || currentUser || "?").trim().slice(0, 2).toUpperCase();

  const visibleNavItems = NAV_ITEMS.filter((item) => {
    if (item.to === "/reservations" && !(role === "user" || role === "admin")) return false;
    if (item.to === "/audit-logs" && !isAdmin) return false;
    return true;
  });

  return (
    <aside className="fixed left-0 top-0 h-full w-sidebar-width bg-surface shadow-[0_4px_12px_rgba(0,0,0,0.06)] flex-col border-r border-outline-variant hidden md:flex z-50">
      <div className="p-gutter flex items-center gap-3">
        <div className="w-10 h-10 bg-primary-container rounded-lg flex items-center justify-center text-white shrink-0">
          <img src="/favicon.png" alt="Open RAN" className="w-full h-full rounded-lg object-contain" />
        </div>
        <div>
          <h1 className="font-title-lg text-title-lg font-bold text-primary leading-tight">Open RAN</h1>
          <p className="text-label-sm text-on-surface-variant opacity-70">Control Panel</p>
        </div>
      </div>
      <div className="px-gutter mt-2 mb-3">
        <button
          type="button"
          role="switch"
          aria-checked={darkMode}
          aria-label="Dark theme"
          onClick={onToggleTheme}
          className="group flex w-full items-center gap-3 rounded-xl border border-outline-variant bg-surface-container-low px-3 py-2.5 text-left transition-colors hover:bg-surface-container"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-container-high text-primary">
            <span className="material-symbols-outlined text-xl">
              {darkMode ? "dark_mode" : "light_mode"}
            </span>
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-semibold leading-5 text-on-surface">Appearance</span>
            <span className="block text-xs leading-4 text-on-surface-variant">
              {darkMode ? "Dark theme" : "Light theme"}
            </span>
          </span>
          <span className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${darkMode ? "bg-primary" : "bg-outline-variant"}`}>
            <span className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-surface-container-lowest shadow-sm transition-transform ${darkMode ? "translate-x-4" : ""}`} />
          </span>
        </button>
      </div>

      <nav className="mt-2 flex-grow">
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
        <div className="flex items-center justify-between gap-3">
          <Link
            to="/profile"
            className="flex items-center gap-3 min-w-0 flex-1 rounded-xl px-2 py-1.5 -mx-2 hover:bg-surface-container-low transition-colors"
            title="Go to Profile"
          >
            <div className="w-10 h-10 rounded-full bg-surface-container-highest text-primary flex items-center justify-center font-title-md shrink-0">
              {initials}
            </div>
            <div className="text-left min-w-0">
              <p className="font-title-md text-title-md text-on-surface truncate">{displayName || currentUser}</p>
              <span className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                role === "admin" ? "bg-primary/10 text-primary" : "bg-primary/10 text-primary"
              }`}>
                {role === "user" || role === "admin" ? role : "user"}
              </span>
            </div>
          </Link>
          <button
            className="p-2 text-primary hover:bg-primary-fixed rounded-lg transition-colors flex items-center justify-center shrink-0"
            title="Logout"
            onClick={onLogout}
          >
            <span className="material-symbols-outlined">logout</span>
          </button>
        </div>
      </div>
    </aside>
  );
}
