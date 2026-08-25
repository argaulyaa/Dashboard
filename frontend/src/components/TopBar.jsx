import React, { useMemo, useState, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { fetchProviders, fetchComponents } from "../api.js";

// Judul per halaman — kunci adalah path route di App.jsx.
const PAGE_TITLES = {
  "/": "Overview",
  "/core": "Core Network Management",
  "/ran": "Radio Access Network",
  "/ric": "RIC Management",
  "/reservations": "Node Reservations",
  "/profile": "Profile",
  "/audit-logs": "Audit Logs",
};

// Domain yang punya konsep "operator/provider aktif".
// Badge Current Operator hanya dirender di route-route ini.
const OPERATOR_DOMAINS = {
  "/core": "core",
  "/ran": "ran",
  "/ric": "ric",
};

const HEALTH_BADGE_LABEL = { healthy: "ONLINE", degraded: "DEGRADED", down: "OFFLINE" };
const HEALTH_BADGE_CLASS = {
  healthy: "bg-secondary-container text-on-secondary-container",
  degraded: "bg-tertiary-container text-on-tertiary-container",
  down: "bg-error-container text-on-error-container",
};

// Status agregat satu domain — logika sama dengan CorePage/RanPage:
// satu komponen down -> domain down, ada yang degraded -> degraded, sisanya healthy.
function domainHealth(components) {
  if (!components?.length) return "down";
  if (components.some((c) => c.status === "down")) return "down";
  if (components.some((c) => c.status === "degraded")) return "degraded";
  return "healthy";
}

// Header atas halaman: sticky (tetap terlihat saat scroll), berisi judul
// halaman aktif di kiri dan badge Current Operator di kanan untuk halaman
// Core/RAN/RIC. Search, telemetry indicator, notifikasi & bantuan tetap
// dihapus sesuai permintaan owner (t_2d1fb375).
//
// Catatan arsitektur: TopBar dulunya `fixed` sehingga App.jsx harus memberi
// padding-top pada <main>. Sekarang sticky in-flow, jadi <main> tidak butuh
// padding-top lagi (lihat App.jsx). Data operator tidak lewat WebSocket —
// TopBar global mem-poll REST ringan (health default provider) tiap 15 detik,
// sama seperti pola fetch di halaman.
export default function TopBar() {
  const location = useLocation();
  const title = PAGE_TITLES[location.pathname];
  const domain = OPERATOR_DOMAINS[location.pathname];

  // Daftar provider domain aktif (data-driven dari backend, sama pola halaman).
  const [providers, setProviders] = useState([]);
  // Health provider non-default (diambil sekali per mount domain).
  const [providerHealthMap, setProviderHealthMap] = useState({});
  // Health default provider — di-refresh berkala supaya badge live mengikuti
  // kondisi instance yang benar-benar jalan.
  const [defaultHealth, setDefaultHealth] = useState(null);

  useEffect(() => {
    if (!domain) return undefined;
    let cancelled = false;
    setProviders([]);
    setProviderHealthMap({});
    setDefaultHealth(null);

    fetchProviders(domain)
      .then((list) => {
        if (cancelled) return;
        setProviders(list || []);
        // Health semua provider non-default, sekali di background.
        (list || []).slice(1).forEach(async (p) => {
          try {
            const comps = await fetchComponents(domain, p.key);
            if (!cancelled) {
              setProviderHealthMap((prev) => ({ ...prev, [p.key]: domainHealth(comps) }));
            }
          } catch {
            if (!cancelled) {
              setProviderHealthMap((prev) => ({ ...prev, [p.key]: "down" }));
            }
          }
        });
      })
      .catch(() => {}); // gagal diam-diam: fitur badge bersifat opsional

    return () => {
      cancelled = true;
    };
  }, [domain]);

  // Poll health default provider tiap 15 detik selama user berada di
  // halaman domain terkait. Bersih-bersih interval saat pindah route.
  useEffect(() => {
    if (!domain || !providers.length) return undefined;
    let cancelled = false;
    const poll = async () => {
      try {
        const comps = await fetchComponents(domain);
        if (!cancelled) setDefaultHealth(domainHealth(comps));
      } catch {
        /* biarkan nilai terakhir */
      }
    };
    poll();
    const t = setInterval(poll, 15000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [domain, providers]);

  // Current Operator = provider pertama yang benar-benar jalan
  // (healthy lebih diprioritaskan daripada degraded), bukan tab yang diklik.
  const currentOperator = useMemo(() => {
    if (!domain || !providers.length) return null;
    const defaultKey = providers[0].key;
    const allHealth = {
      [defaultKey]: defaultHealth ?? "down",
      ...providerHealthMap,
    };
    const running =
      providers.find((p) => allHealth[p.key] === "healthy") ||
      providers.find((p) => allHealth[p.key] === "degraded");
    if (!running) return null;
    return { ...running, health: allHealth[running.key] };
  }, [domain, providers, providerHealthMap, defaultHealth]);

  return (
    <header className="sticky top-0 z-40 h-16 w-full md:w-[calc(100%-280px)] md:ml-sidebar-width bg-surface-bright border-b border-outline-variant flex justify-between items-center gap-4 px-gutter">
      {/* Kiri: judul halaman aktif */}
      <h2 className="text-headline-md font-headline-md text-on-surface truncate min-w-0">
        {title || ""}
      </h2>

      {/* Kanan: badge Current Operator (hanya di halaman Core/RAN/RIC) */}
      {domain && (
        <div className="shrink-0 glass-card border border-outline-variant rounded-xl px-4 py-1.5 shadow-sm flex items-center gap-3">
          <span className="material-symbols-outlined text-primary text-xl">
            {currentOperator?.icon || "cloud_off"}
          </span>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant leading-tight">
              Current Operator
            </p>
            <p className="font-bold text-sm text-on-surface leading-tight">
              {currentOperator?.label ?? "None"}
            </p>
            <span
              className={`inline-block mt-0.5 text-[10px] font-bold px-2 py-0 rounded-full ${
                currentOperator
                  ? HEALTH_BADGE_CLASS[currentOperator.health]
                  : "bg-surface-container text-on-surface-variant"
              }`}
            >
              ● {currentOperator ? HEALTH_BADGE_LABEL[currentOperator.health] : "NO ACTIVE PROVIDER"}
            </span>
          </div>
        </div>
      )}
    </header>
  );
}
