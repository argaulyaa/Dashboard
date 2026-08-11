import React, { useState } from "react";
import { setUser } from "../user.js";

export default function UserBadge({ currentUser, onChange }) {
  const [editing, setEditing] = useState(!currentUser);
  const [value, setValue] = useState(currentUser);

  const save = () => {
    const name = value.trim();
    if (!name) return;
    setUser(name);
    onChange(name);
    setEditing(false);
  };

  if (editing) {
    return (
      <div className="flex items-center gap-2 text-xs font-mono">
        <input
          className="bg-slate-100 border border-panel-border rounded-md text-ink px-2.5 py-1.5 text-xs font-sans focus:outline-none focus:ring-2 focus:ring-restarting/30"
          placeholder="Your name..."
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && save()}
          autoFocus
        />
        <button
          className="border border-panel-border rounded-lg px-3 py-1.5 text-xs font-semibold bg-transparent cursor-pointer text-ink"
          onClick={save}
        >
          Save
        </button>
      </div>
    );
  }

  return (
    <button
      className="flex items-center gap-2 text-xs font-mono border border-panel-border rounded-full px-3 py-1.5 text-ink cursor-pointer bg-transparent"
      onClick={() => setEditing(true)}
    >
      <span className="w-[7px] h-[7px] rounded-full bg-restarting inline-block" />
      {currentUser}
    </button>
  );
}
