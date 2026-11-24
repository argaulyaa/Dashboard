import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchMobileDeviceInfo,
  fetchMobileDevices,
  openMobileScreenSocket,
  sendMobileKey,
  sendMobileText,
  setMobileAirplaneMode,
  tapMobileScreen,
  wakeMobileDevice,
} from "../api.js";

const ANDROID_KEYS = {
  Enter: "ENTER",
  Backspace: "BACKSPACE",
  Escape: "ESCAPE",
  Tab: "TAB",
  Home: "HOME",
  ArrowUp: "UP",
  ArrowDown: "DOWN",
  ArrowLeft: "LEFT",
  ArrowRight: "RIGHT",
  " ": "SPACE",
};

function Icon({ children, className = "" }) {
  return <span className={`material-symbols-outlined ${className}`}>{children}</span>;
}

export default function RemoteDevices() {
  const [devices, setDevices] = useState([]);
  const [serial, setSerial] = useState("");
  const [deviceInfo, setDeviceInfo] = useState(null);
  const [screenUrl, setScreenUrl] = useState("");
  const [streamStatus, setStreamStatus] = useState("idle");
  const [loadingDevices, setLoadingDevices] = useState(true);
  const [deviceRefresh, setDeviceRefresh] = useState(0);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const screenUrlRef = useRef("");
  const screenRef = useRef(null);

  const refreshDevices = useCallback(async () => {
    setLoadingDevices(true);
    setDeviceRefresh((version) => version + 1);
    setError("");
    try {
      const result = await fetchMobileDevices();
      setDevices(result);
      setSerial((current) => {
        if (result.some((device) => device.serial === current)) return current;
        return result.find((device) => device.state === "device")?.serial || result[0]?.serial || "";
      });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoadingDevices(false);
    }
  }, []);

  useEffect(() => {
    refreshDevices();
  }, [refreshDevices]);

  useEffect(() => {
    if (!serial) {
      setDeviceInfo(null);
      setStreamStatus("idle");
      return undefined;
    }

    let active = true;
    const previousUrl = screenUrlRef.current;
    if (previousUrl) URL.revokeObjectURL(previousUrl);
    screenUrlRef.current = "";
    setScreenUrl("");
    setDeviceInfo(null);
    setStreamStatus("connecting");

    fetchMobileDeviceInfo(serial)
      .then((info) => {
        if (active) setDeviceInfo(info);
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      });

    const socket = openMobileScreenSocket(serial);
    socket.binaryType = "arraybuffer";
    socket.onopen = () => {
      if (active) setStreamStatus("live");
    };
    socket.onmessage = (event) => {
      if (!active) return;
      if (typeof event.data === "string") {
        try {
          const payload = JSON.parse(event.data);
          if (payload.error) setError(payload.error);
        } catch {
          setError("The screen stream returned an unreadable error.");
        }
        return;
      }
      const nextUrl = URL.createObjectURL(new Blob([event.data], { type: "image/png" }));
      const oldUrl = screenUrlRef.current;
      screenUrlRef.current = nextUrl;
      setScreenUrl(nextUrl);
      if (oldUrl) URL.revokeObjectURL(oldUrl);
    };
    socket.onerror = () => {
      if (active) {
        setStreamStatus("error");
        setError("Could not open the screen stream. Check the device ADB connection.");
      }
    };
    socket.onclose = () => {
      if (active) setStreamStatus((current) => current === "error" ? current : "offline");
    };

    return () => {
      active = false;
      socket.close();
      if (screenUrlRef.current) URL.revokeObjectURL(screenUrlRef.current);
      screenUrlRef.current = "";
    };
  }, [serial, deviceRefresh]);

  const runAction = useCallback(async (name, action, successMessage) => {
    if (!serial) return;
    setBusyAction(name);
    setError("");
    setNotice("");
    try {
      const result = await action();
      if (result?.enabled !== undefined) {
        setDeviceInfo((current) => current ? { ...current, airplane_mode: result.enabled } : current);
      }
      setNotice(successMessage);
      return true;
    } catch (requestError) {
      setError(requestError.message);
      return false;
    } finally {
      setBusyAction("");
    }
  }, [serial]);

  const handleScreenKeyDown = (event) => {
    if (event.ctrlKey || event.metaKey || event.altKey || !serial) return;
    const androidKey = ANDROID_KEYS[event.key];
    if (androidKey) {
      event.preventDefault();
      sendMobileKey(serial, androidKey).catch((requestError) => setError(requestError.message));
      return;
    }
    if (event.key.length === 1 && !event.repeat) {
      event.preventDefault();
      sendMobileText(serial, event.key).catch((requestError) => setError(requestError.message));
    }
  };

  const handleScreenTap = (event) => {
    if (!serial || !event.currentTarget.naturalWidth) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
    const y = Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height));
    tapMobileScreen(serial, x, y).catch((requestError) => setError(requestError.message));
  };

  const selectedDevice = devices.find((device) => device.serial === serial);
  const deviceReady = selectedDevice?.state === "device";
  const airplaneEnabled = deviceInfo?.airplane_mode === true;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-1 text-xs font-bold uppercase tracking-[0.18em] text-primary">Device Lab</p>
          <h1 className="text-2xl font-bold text-on-surface sm:text-3xl">Remote Devices</h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            Stream and control Android phones connected to the ADB host.
          </p>
        </div>
        <button
          type="button"
          onClick={refreshDevices}
          disabled={loadingDevices}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-outline-variant bg-surface-container-low px-4 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container disabled:opacity-50"
        >
          <Icon className={loadingDevices ? "animate-spin" : ""}>refresh</Icon>
          Refresh devices
        </button>
      </header>

      {error && (
        <div role="alert" className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          <Icon className="text-lg">error</Icon>
          <span>{error}</span>
        </div>
      )}
      {notice && (
        <div role="status" className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          <Icon className="text-lg">check_circle</Icon>
          <span>{notice}</span>
        </div>
      )}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section className="overflow-hidden rounded-2xl border border-outline-variant bg-surface-container-lowest shadow-sm">
          <div className="flex flex-col gap-3 border-b border-outline-variant px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <div className="flex min-w-0 items-center gap-3">
              <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${streamStatus === "live" ? "bg-emerald-500" : "bg-slate-400"}`} />
              <div className="min-w-0">
                <h2 className="truncate font-semibold text-on-surface">
                  {selectedDevice?.model || "Phone screen"}
                </h2>
                <p className="truncate font-mono text-xs text-on-surface-variant">
                  {serial || "No device selected"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className={`text-xs font-semibold ${streamStatus === "live" ? "text-emerald-700" : "text-on-surface-variant"}`}>
                {streamStatus === "live" ? "LIVE · ~2 FPS" : streamStatus === "connecting" ? "Connecting…" : streamStatus === "error" ? "Stream error" : "Stream offline"}
              </span>
              <select
                aria-label="Select a device"
                value={serial}
                onChange={(event) => {
                  setError("");
                  setNotice("");
                  setSerial(event.target.value);
                }}
                className="max-w-48 rounded-lg border border-outline-variant bg-surface-container-low px-3 py-2 text-sm text-on-surface"
              >
                {!devices.length && <option value="">No devices</option>}
                {devices.map((device) => (
                  <option key={device.serial} value={device.serial}>
                    {device.model} · {device.state}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex min-h-[420px] items-center justify-center bg-slate-950 p-4 sm:min-h-[620px] sm:p-8">
            {!serial ? (
              <div className="max-w-sm text-center text-slate-300">
                <Icon className="mb-3 text-5xl text-slate-500">phonelink_off</Icon>
                <p className="font-semibold text-white">No devices connected</p>
                <p className="mt-2 text-sm text-slate-400">
                  Connect a phone to the backend host over USB or ADB TCP/IP, then refresh the device list.
                </p>
              </div>
            ) : !deviceReady ? (
              <div className="text-center text-slate-300">
                <Icon className="mb-3 text-5xl text-amber-400">phonelink_lock</Icon>
                <p className="font-semibold text-white">Device not ready</p>
                <p className="mt-2 text-sm text-slate-400">ADB status: {selectedDevice?.state || "unknown"}</p>
              </div>
            ) : screenUrl ? (
              <div
                ref={screenRef}
                tabIndex={0}
                role="application"
                aria-label="Phone screen. Type to send text; use arrow keys, Enter, Backspace, or Escape to control the device."
                onKeyDown={handleScreenKeyDown}
                onMouseDown={() => screenRef.current?.focus()}
                className="max-h-[72vh] max-w-full overflow-hidden rounded-[1.7rem] border-[7px] border-slate-700 bg-black shadow-2xl outline-none focus:border-primary"
              >
                <img
                  src={screenUrl}
                  alt={`Live screen from ${selectedDevice?.model || serial}`}
                  onClick={handleScreenTap}
                  draggable="false"
                  className="block max-h-[68vh] max-w-full cursor-crosshair select-none object-contain"
                />
              </div>
            ) : (
              <div className="text-center text-slate-300">
                <Icon className="mb-3 animate-pulse text-5xl text-primary">smartphone</Icon>
                <p className="font-semibold text-white">
                  {streamStatus === "error" ? "Stream unavailable" : "Connecting to device…"}
                </p>
                <p className="mt-2 text-sm text-slate-400">Make sure USB debugging is enabled and authorized on the phone.</p>
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-outline-variant px-4 py-3 text-xs text-on-surface-variant sm:px-5">
            <span>Click the screen to tap · Focus the screen to use your keyboard</span>
            <span>{deviceInfo ? `${deviceInfo.width} × ${deviceInfo.height}` : "ADB screen stream"}</span>
          </div>
        </section>

        <aside className="space-y-5">
          <section className="rounded-2xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm">
            <div className="mb-4 flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon>tune</Icon>
              </span>
              <div>
                <h2 className="font-semibold text-on-surface">Device controls</h2>
                <p className="text-xs text-on-surface-variant">Commands are sent over ADB</p>
              </div>
            </div>
            <div className="space-y-3">
              <button
                type="button"
                disabled={!deviceReady || !!busyAction}
                onClick={() => runAction("wake", () => wakeMobileDevice(serial), "Device screen awakened.")}
                className="flex w-full items-center gap-3 rounded-xl border border-outline-variant bg-surface-container-low px-4 py-3 text-left text-sm font-semibold text-on-surface transition hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Icon className="text-primary">light_mode</Icon>
                <span className="flex-1">Wake screen</span>
                {busyAction === "wake" && <Icon className="animate-spin text-base">progress_activity</Icon>}
              </button>
              <button
                type="button"
                disabled={!deviceReady || !!busyAction}
                onClick={() => runAction(
                  "airplane",
                  () => setMobileAirplaneMode(serial, !airplaneEnabled),
                  `Airplane mode ${airplaneEnabled ? "disabled" : "enabled"}.`
                )}
                className={`flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${
                  airplaneEnabled
                    ? "border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100"
                    : "border-outline-variant bg-surface-container-low text-on-surface hover:bg-surface-container"
                }`}
              >
                <Icon className={airplaneEnabled ? "text-amber-700" : "text-on-surface-variant"}>airplanemode_active</Icon>
                <span className="flex-1">{airplaneEnabled ? "Disable airplane mode" : "Enable airplane mode"}</span>
                {busyAction === "airplane" && <Icon className="animate-spin text-base">progress_activity</Icon>}
              </button>
              <p className="px-1 text-[11px] leading-relaxed text-on-surface-variant">
                Airplane mode control depends on Android version and device policy support.
              </p>
            </div>
          </section>

          <div className="flex items-start gap-3 rounded-xl border border-outline-variant bg-surface-container-low px-4 py-3 text-xs leading-relaxed text-on-surface-variant">
            <Icon className="shrink-0 text-primary">info</Icon>
            Only devices connected to and authorized on the backend ADB host can be controlled.
          </div>
        </aside>
      </div>
    </div>
  );
}