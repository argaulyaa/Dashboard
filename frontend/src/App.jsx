import React, { useEffect, useState, useCallback } from "react";
import { HashRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar.jsx";
import TopBar from "./components/TopBar.jsx";
import { PageHeaderProvider } from "./components/PageHeaderContext.jsx";
import MobileNav from "./components/MobileNav.jsx";
import ControlDrawer from "./components/ControlDrawer.jsx";
import Overview from "./pages/Overview.jsx";
import RicPage from "./pages/RicPage.jsx";
import CorePage from "./pages/CorePage.jsx";
import RanPage from "./pages/RanPage.jsx";
import { fetchComponents, restartComponent, openTelemetrySocket } from "./api.js";
import { getUser, clearUser, getRole } from "./user.js";
import ReservationsPage from "./pages/Reservation.jsx";
import Console from "./pages/Console.jsx";
import Login from "./pages/Login.jsx";
import Profile from "./pages/Profile.jsx";
import Register from "./pages/Register.jsx";
import VerifyEmail from "./pages/VerifyEmail.jsx";
import AuditLogs from "./pages/AuditLogs.jsx";
import { isAuthenticated, logout } from "./auth.js";

// const DOMAIN_META = {
//   core: { title: "Core", subtitle: "5G Core network functions" },
//   ran: { title: "RAN", subtitle: "gNB / CU / DU (OAI)" },
//   ric: { title: "RIC", subtitle: "near-RT & non-RT RIC" },
// };

// Komponen ini WAJIB berada di dalam <HashRouter> karena pakai useLocation.
// Tugasnya: matikan scroll restoration bawaan browser saat pertama load,
// dan reset scroll ke atas (di semua kemungkinan elemen scroll) setiap
// kali route berubah, supaya konten atas halaman tidak tertutup TopBar.
function ScrollToTopOnNavigate() {
  const location = useLocation();

  useEffect(() => {
    if ("scrollRestoration" in window.history) {
      window.history.scrollRestoration = "manual";
    }
  }, []);

  useEffect(() => {
    const resetScroll = () => {
      window.scrollTo(0, 0);
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
      const mainEl = document.querySelector("main");
      if (mainEl) mainEl.scrollTop = 0;
    };
    resetScroll();
    const t = setTimeout(resetScroll, 100);
    return () => clearTimeout(t);
  }, [location.pathname]);

  return null;
}

export default function App() {
  const [data, setData] = useState({ core: [], ran: [], ric: [] });
  const [selected, setSelected] = useState(null); // { domain, component }
  const [wsStatus, setWsStatus] = useState("connecting");
  const [error, setError] = useState(null);
  const [currentUser, setCurrentUser] = useState(getUser());
  const [opsCount, setOpsCount] = useState(0);
  const [lastTelemetryAt, setLastTelemetryAt] = useState(null); 

  useEffect(() => {
    (async () => {
      try {
        const [core, ran, ric] = await Promise.all([
          fetchComponents("core"),
          fetchComponents("ran"),
          fetchComponents("ric"),
        ]);
        setData({ core, ran, ric });
      } catch (e) {
        setError(e.message);
      }
    })();
  }, []);

  useEffect(() => {
  const ws = openTelemetrySocket((snapshot) => {
    setWsStatus("live");
    setData(snapshot);
    setLastTelemetryAt(Date.now());
  });
    ws.onopen = () => setWsStatus("live");
    ws.onerror = () => setWsStatus("offline");
    ws.onclose = () => setWsStatus("offline");
    return () => ws.close();
  }, []);

  const handleSelect = useCallback((domainKey, component) => {
    setSelected({ domain: domainKey, component });
  }, []);

  const handleRestart = useCallback(async (domainKey, id) => {
  const updated = await restartComponent(domainKey, id);
  setData((prev) => ({
    ...prev,
    [domainKey]: prev[domainKey].map((c) => (c.id === id ? updated : c)),
  }));
  setSelected((prev) =>
    prev && prev.component.id === id ? { ...prev, component: updated } : prev
  );
  setOpsCount((n) => n + 1);
}, []);

const handleLogout = useCallback(() => {
  clearUser();
  logout();
  window.location.reload();
}, []);

  const handleReservationChange = useCallback((domainKey, id, reservation) => {
    setData((prev) => ({
      ...prev,
      [domainKey]: prev[domainKey].map((c) => (c.id === id ? { ...c, reservation } : c)),
    }));
    setSelected((prev) =>
      prev && prev.component.id === id
        ? { ...prev, component: { ...prev.component, reservation } }
        : prev
    );
  }, []);

  if (!isAuthenticated()) {
    return (
      <HashRouter>
        <Routes>
          <Route path="/login" element={<Login onLoginSuccess={setCurrentUser} />} />
          <Route path="/register" element={<Register onLoginSuccess={setCurrentUser} />} />
          <Route path="/verify" element={<VerifyEmail />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </HashRouter>
    );
  }

  return (
    <HashRouter>
      <ScrollToTopOnNavigate />
      <div className="min-h-screen bg-surface">
        <Sidebar
          currentUser={currentUser}
          onUserChange={setCurrentUser}
          onLogout={handleLogout}
        />
        <TopBar wsStatus={wsStatus} />
        <MobileNav />

        {/* TopBar kini sticky in-flow (bukan fixed), jadi <main> tidak butuh
            padding-top tinggi — cukup jarak kecil di mobile. */}
        <main className="pt-4 md:ml-sidebar-width min-h-screen px-container-padding-mobile md:px-container-padding-desktop pb-24 md:pb-10">
          {error && (
          <div className="text-error font-mono text-[13px] mb-4">Failed to load data: {error}</div>
          )}

          {/* PageHeaderProvider: page aktif set judul/subtitle via usePageHeader(),
              TopBar sticky membacanya. Membungkus seluruh <Routes>. */}
          <PageHeaderProvider>
          <Routes>
            <Route
              path="/"
              element={
                <Overview
                  data={data}
                  currentUser={currentUser}
                  onSelect={handleSelect}
                  onReservationChange={handleReservationChange}
                />
              }
            />
            <Route
  path="/core"
  element={
    <CorePage
      components={data.core || []}
      currentUser={currentUser}
      onSelect={(component) => handleSelect("core", component)}
      onRestart={handleRestart}
    />
  }
/>

            <Route
              path="/ran"
              element={
                <RanPage
                  components={data.ran || []}
                  currentUser={currentUser}
                  onSelect={(component) => handleSelect("ran", component)}
                  onRestart={handleRestart}
                />
              }
            />

            <Route
              path="/ric"
              element={
                <RicPage
                  components={data.ric || []}
                  ranComponents={data.ran || []}
                  currentUser={currentUser}
                  onSelect={(component) => handleSelect("ric", component)}
                  onRestart={handleRestart}
                />
              }
            />

<Route
  path="/reservations"
  element={
    /* RBAC 2-role: semua role ('user'/'admin') boleh reservasi */
    false ? (
      <Navigate to="/" replace />
    ) : (
      <ReservationsPage
        data={data}
        currentUser={currentUser}
        onReservationChange={handleReservationChange}
      />
    )
  }
/>

            <Route
              path="/profile"
              element={
                <Profile
                  currentUser={currentUser}
                  onUserChange={setCurrentUser}
                  onLogout={handleLogout}
                  opsCount={opsCount}
                  lastTelemetryAt={lastTelemetryAt}
                />
              }
            />

            <Route
              path="/audit-logs"
              element={
                currentUser === "admin" || getRole() === "admin" ? (
                  <AuditLogs currentUser={currentUser} />
                ) : (
                  <Navigate to="/" replace />
                )
              }
            />

            <Route
              path="/ssh/:domain/:componentId"
              element={<Console data={data} currentUser={currentUser} />}
            />
          </Routes>
          </PageHeaderProvider>
        </main>

        {selected && (
          <ControlDrawer
            domain={selected.domain}
            component={selected.component}
            currentUser={currentUser}
            onClose={() => setSelected(null)}
            onRestart={handleRestart}
            onReservationChange={handleReservationChange}
          />
        )}
      </div>
    </HashRouter>
  );
}