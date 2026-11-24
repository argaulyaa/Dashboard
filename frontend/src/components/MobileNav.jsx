import React from "react";
import { NavLink } from "react-router-dom";
import { getRole } from "../user.js";

const ITEMS = [
  { to: "/", label: "Overview", icon: "dashboard", end: true },
  { to: "/ran", label: "Nodes", icon: "router" },
  { to: "/remote-devices", label: "Devices", icon: "phonelink" },
  { to: "/ric", label: "RIC", icon: "hub" },
  { to: "/reservations", label: "Book", icon: "calendar_today" },
  { to: "/audit-logs", label: "Audit", icon: "shield" },
  { to: "/profile", label: "Profile", icon: "person" },
];

export default function MobileNav({ currentUser }) {
  const role = getRole();
  const isAdmin = currentUser === "admin" || role === "admin";
  const visibleItems = ITEMS.filter((item) => {
    if (item.to === "/reservations" && !(role === "user" || role === "admin")) return false;
    if (item.to === "/audit-logs" && !isAdmin) return false;
    return true;
  });

  return (
    <nav className="fixed bottom-0 w-full md:hidden z-50 bg-surface border-t border-outline-variant shadow-[0_-4px_12px_rgba(0,0,0,0.06)] flex justify-start gap-1 overflow-x-auto items-center h-16 px-2">
      {visibleItems.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            `flex shrink-0 flex-col items-center justify-center rounded-xl px-3 py-1 ${
              isActive ? "bg-primary-container text-white" : "text-on-surface-variant"
            }`
          }
        >
          <span className="material-symbols-outlined">{item.icon}</span>
          <span className="font-label-sm text-label-sm">{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}