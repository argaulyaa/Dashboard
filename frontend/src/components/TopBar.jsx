import React from "react";

// Header atas halaman. Search input, indikator telemetry, tombol notifikasi,
// dan tombol bantuan sudah dihapus atas permintaan owner — sisanya kosong.
export default function TopBar() {
  return (
    <header className="fixed top-0 right-0 h-16 md:ml-sidebar-width w-full md:w-[calc(100%-280px)] bg-surface-bright border-b border-outline-variant flex justify-between items-center px-gutter z-40">
    </header>
  );
}
