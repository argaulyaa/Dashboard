import React from "react";
import { useLocation } from "react-router-dom";
import { usePageHeader } from "./PageHeaderContext.jsx";

// Fallback judul per halaman — kunci adalah path route di App.jsx.
// Dipakai hanya kalau page aktif belum set header via usePageHeader();
// halaman Core/RAN/RIC selalu set sendiri (judul + subtitle).
const PAGE_TITLES = {
  "/": "Overview",
  "/core": "Core Network Management",
  "/ran": "Radio Access Network",
  "/ric": "RIC Management",
  "/reservations": "Reservations",
  "/profile": "Profile",
  "/audit-logs": "Audit Logs",
};

// Header atas halaman: sticky (tetap terlihat saat scroll) dan TITLE-ONLY —
// isi judul/subtitle datang dari page aktif lewat usePageHeader()
// (PageHeaderProvider dibungkus di App.jsx di sekeliling <Routes>).
//
// Revisi owner (t_6c29abe5): badge Current Operator TIDAK lagi dirender di
// sini. Kotak operator pindah ke body halaman Core/RAN, sejajar dengan
// provider tabs. Search, telemetry, ikon notifikasi & bantuan juga tetap
// dihapus sesuai t_2d1fb375.
//
// Catatan arsitektur: TopBar sticky in-flow (bukan fixed), jadi <main> tidak
// butuh padding-top tinggi (lihat App.jsx).
export default function TopBar() {
  const location = useLocation();
  // Tanpa argumen = mode GET: baca header yang sedang diset page aktif.
  const pageHeader = usePageHeader();

  const title = pageHeader?.title || PAGE_TITLES[location.pathname] || "";
  const subtitle = pageHeader?.subtitle || "";

  return (
    <header className="sticky top-0 z-40 min-h-16 w-full md:w-[calc(100%-280px)] md:ml-sidebar-width bg-surface-bright border-b border-outline-variant flex justify-between items-center gap-4 px-gutter py-2">
      {/* Kiri: judul (+subtitle opsional) halaman aktif — tanpa slot kanan */}
      <div className="min-w-0">
        <h2 className="text-headline-md font-headline-md text-on-surface truncate">
          {title}
        </h2>
        {subtitle && (
          <p className="text-sm text-on-surface-variant truncate -mt-0.5">
            {subtitle}
          </p>
        )}
      </div>
    </header>
  );
}
