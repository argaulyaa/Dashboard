"""
Adapter layer for the O-RAN control dashboard.

Each adapter below is a MOCK implementation. It exists so the dashboard
has something real to render and control end-to-end before it is wired
to an actual testbed. When you're ready to integrate:

- CoreAdapter   -> replace mock calls with SBI (HTTP/2 REST) calls to
                   AMF/SMF/UPF, or docker/k8s API calls to restart NF
                   containers.
- RanAdapter    -> replace with SSH/CLI calls to the OAI gNB (softmodem),
                   or a config-management call if you expose one.
- RicAdapter    -> replace with E2 interface calls (near-RT RIC / xApps)
                   via FlexRIC's SDK, and A1 policy calls to the non-RT RIC.

Keep the function signatures the same so the FastAPI routes in main.py
don't need to change when you swap the implementation.
"""

import asyncio
import json
import os
import random
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional

# Plain str instead of typing.Literal use, kept simple for broad Python
# version compatibility (works fine on Python 3.8+).
Status = str


@dataclass
class Component:
    id: str
    name: str
    kind: str          # e.g. "AMF", "SMF", "UPF", "gNB", "xApp"
    status: Status
    detail: str = ""    # (dulu bernama "ddetail" -- typo, sudah diperbaiki)
    host: str = ""      # SSH-reachable host/IP, if applicable
    cpu_pct: float = 0.0
    mem_gb: float = 0.0
    mem_pct: float = 0.0
    throughput_mbps: float = 0.0
    port: int = 0
    latency_ms: float = 0.0
    active_ues: int = 0     # jumlah UE yang konek, relevan utk gNB/CU/DU
    last_updated: float = field(default_factory=time.time)
    started_at: float = field(default_factory=time.time)  # reset only on restart, drives uptime

    def to_dict(self):
        d = asdict(self)
        d["uptime_seconds"] = time.time() - self.started_at
        return d


class BaseAdapter:
    """Shared in-memory mock store + fake restart behavior."""

    def __init__(self, components: List[Component]):
        self._components = {c.id: c for c in components}

    def list(self) -> List[dict]:
        return [c.to_dict() for c in self._components.values()]

    def get(self, comp_id: str) -> Optional[dict]:
        c = self._components.get(comp_id)
        return c.to_dict() if c else None

    async def restart(self, comp_id: str) -> Optional[dict]:
        c = self._components.get(comp_id)
        if not c:
            return None
        c.status = "restarting"
        c.last_updated = time.time()
        await asyncio.sleep(1.5)  # simulate real restart latency
        c.status = "healthy"
        c.detail = "Restarted successfully"
        c.last_updated = time.time()
        c.started_at = time.time()  # uptime clock restarts here
        return c.to_dict()

    def jitter_health(self):
        """Randomly wobble one component's status - stands in for real telemetry."""
        c = random.choice(list(self._components.values()))
        if c.status == "restarting":
            return
        c.status = random.choices(
            ["healthy", "degraded", "down"], weights=[0.82, 0.14, 0.04]
        )[0]
        c.last_updated = time.time()

    def get_logs(self, comp_id: str, tail: int = 100) -> str:
        c = self._components.get(comp_id)
        if not c:
            return f"Component '{comp_id}' not found."
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return (
            f"{now_str} [INFO] [{c.name}] Initializing {c.kind} service...\n"
            f"{now_str} [INFO] [{c.name}] Binding listener on {c.host or '127.0.0.1'}:{c.port or 8080}\n"
            f"{now_str} [INFO] [{c.name}] Health Status: {c.status.upper()} — {c.detail}\n"
            f"{now_str} [DEBUG] [{c.name}] Metrics report: CPU={c.cpu_pct}%, MEM={c.mem_gb}GB ({c.mem_pct}%)\n"
            f"{now_str} [INFO] [{c.name}] Running active operations nominal.\n"
        )


# ---------------------------------------------------------------------------
# Core adapters
# ---------------------------------------------------------------------------

CORE_KIND_LABELS = {
    "amf": "Access & Mobility Mgmt",
    "smf": "Session Mgmt",
    "upf": "User Plane Function",
    "ausf": "Authentication",
    "nrf": "NF Repository",
    "udm": "Unified Data Mgmt",
    "udr": "Unified Data Repository",
}


class CoreAdapter(BaseAdapter):
    """Mock 5G Core adapter — data statis, cocok sebelum testbed OAI siap."""

    def __init__(self):
        super().__init__([
            Component("amf", "AMF", "Access & Mobility Mgmt", "healthy", "N2/N1 signaling nominal",
                       host="10.0.25.144", cpu_pct=24, mem_gb=3.2, mem_pct=40,
                       throughput_mbps=12.4, port=38412, latency_ms=4.2),
            Component("smf", "SMF", "Session Mgmt", "healthy", "PDU sessions: 12 active",
                       host="10.0.25.145", cpu_pct=18, mem_gb=2.8, mem_pct=35,
                       throughput_mbps=8.2, port=38415, latency_ms=3.1),
            Component("upf", "UPF", "User Plane Function", "healthy", "Throughput: 340 Mbps",
                       host="10.0.25.146", cpu_pct=45, mem_gb=6.4, mem_pct=60,
                       throughput_mbps=450.1, port=2152, latency_ms=2.5),
            Component("ausf", "AUSF", "Authentication", "healthy", "Auth success rate 99.8%",
                       host="10.0.25.147", cpu_pct=12, mem_gb=1.8, mem_pct=22,
                       throughput_mbps=2.1, port=38414, latency_ms=1.8),
            Component("nrf", "NRF", "NF Repository", "healthy", "8 NFs registered",
                       host="10.0.25.148", cpu_pct=10, mem_gb=1.5, mem_pct=19,
                       throughput_mbps=1.4, port=38413, latency_ms=1.5),
            Component("udm", "UDM", "Unified Data Mgmt", "healthy", "Subscriber profile management active",
                       host="10.0.25.149", cpu_pct=15, mem_gb=2.1, mem_pct=26,
                       throughput_mbps=3.5, port=38416, latency_ms=2.0),
            Component("udr", "UDR", "Unified Data Repository", "healthy", "Unified database query nominal",
                       host="10.0.25.150", cpu_pct=20, mem_gb=4.0, mem_pct=48,
                       throughput_mbps=5.0, port=38417, latency_ms=1.7),
        ])


class DockerCoreAdapter:
    """
    Adapter Core berbasis Docker Engine API.

    Diaktifkan saat OAI_CORE_CONTAINERS (atau OPEN5GS_CORE_CONTAINERS) di-set
    di .env. Kalau env kosong, backend tetap jalan — cukup gunakan CoreAdapter
    (mock) sebagai fallback.

    container_map: dict pemetaan comp_id -> nama container Docker,
    contoh: {"amf": "oai-amf", "smf": "oai-smf", ...}
    """

    def __init__(self, container_map: dict, docker_host: str = None):
        import docker  # lazy import — hanya butuh kalau adapter ini dipakai
        self._map = container_map  # comp_id -> container_name
        client_kwargs = {}
        if docker_host:
            client_kwargs["base_url"] = docker_host
        self._client = docker.DockerClient(**client_kwargs)

    # ------------------------------------------------------------------
    # Kontrak adapter (harus konsisten dengan BaseAdapter)
    # ------------------------------------------------------------------

    def list(self) -> List[dict]:
        return [self._read_component(comp_id) for comp_id in self._map]

    def get(self, comp_id: str) -> Optional[dict]:
        if comp_id not in self._map:
            return None
        return self._read_component(comp_id)

    async def restart(self, comp_id: str) -> Optional[dict]:
        if comp_id not in self._map:
            return None
        container_name = self._map[comp_id]
        try:
            container = self._client.containers.get(container_name)
            container.restart()
        except Exception as e:
            # Log tapi jangan crash — kembalikan status "restarting" supaya UI update
            pass
        await asyncio.sleep(2)
        return self.get(comp_id)

    def jitter_health(self):
        """No-op untuk adapter nyata — status datang dari Docker, bukan random."""
        pass

    def get_logs(self, comp_id: str, tail: int = 100) -> str:
        if comp_id not in self._map:
            return f"Component '{comp_id}' not mapped in Docker configuration."
        container_name = self._map[comp_id]
        try:
            container = self._client.containers.get(container_name)
            logs_bytes = container.logs(tail=tail, timestamps=True)
            return logs_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            return f"[Docker Error] Could not retrieve logs for container '{container_name}': {e}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_component(self, comp_id: str) -> dict:
        container_name = self._map[comp_id]
        try:
            container = self._client.containers.get(container_name)
            status = self._map_status(container.status)
            attrs = container.attrs or {}
            state = attrs.get("State", {})
            started_at_str = state.get("StartedAt", "")
            started_at = self._parse_started_at(started_at_str)
            return {
                "id": comp_id,
                "name": comp_id.upper(),
                "kind": CORE_KIND_LABELS.get(comp_id, comp_id.upper()),
                "status": status,
                "detail": f"Container: {container_name} ({container.status})",
                "host": "",          # isi kalau ada IP yg bisa di-SSH
                "cpu_pct": 0.0,      # butuh docker stats stream, belum diimplementasi
                "mem_gb": 0.0,
                "mem_pct": 0.0,
                "throughput_mbps": 0.0,
                "port": 0,
                "latency_ms": 0.0,
                "active_ues": 0,
                "last_updated": time.time(),
                "uptime_seconds": time.time() - started_at if started_at else 0,
                "started_at": started_at or time.time(),
            }
        except Exception as e:
            return {
                "id": comp_id,
                "name": comp_id.upper(),
                "kind": CORE_KIND_LABELS.get(comp_id, comp_id.upper()),
                "status": "down",
                "detail": f"Container tidak ditemukan: {container_name}",
                "host": "",
                "cpu_pct": 0.0, "mem_gb": 0.0, "mem_pct": 0.0,
                "throughput_mbps": 0.0, "port": 0, "latency_ms": 0.0,
                "active_ues": 0,
                "last_updated": time.time(),
                "uptime_seconds": 0,
                "started_at": time.time(),
            }

    @staticmethod
    def _map_status(docker_status: str) -> Status:
        """Map status Docker ke empat nilai yang dikenal frontend."""
        mapping = {
            "running": "healthy",
            "restarting": "restarting",
            "paused": "degraded",
            "exited": "down",
            "dead": "down",
            "created": "degraded",
            "removing": "restarting",
        }
        return mapping.get(docker_status, "degraded")

    @staticmethod
    def _parse_started_at(started_at_str: str) -> Optional[float]:
        """Parse ISO timestamp dari Docker attrs ke epoch float."""
        if not started_at_str or started_at_str.startswith("0001"):
            return None
        try:
            from datetime import datetime, timezone
            # Format: "2024-01-15T10:30:00.123456789Z"
            ts = started_at_str[:26].rstrip("Z").rstrip("0").rstrip(".")
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return None


class SshDockerCoreAdapter(DockerCoreAdapter):
    """
    DockerCoreAdapter berbasis SSH untuk Core di mesin remote (mini PC testbed).

    Perintah docker dijalankan remote via paramiko di node Core (mis. 10.91.2.151),
    jadi TIDAK perlu mengekspos Docker daemon lewat TCP (lebih aman daripada
    OAI_DOCKER_HOST=tcp://...). Cocok saat backend berjalan di PC lain (laptop
    developer) dan node Core cuma bisa diakses via SSH.

    Konfigurasi via .env:
      OAI_SSH_HOST / OAI_SSH_PORT / OAI_SSH_USER / OAI_SSH_PASSWORD
    Pemetaan container tetap lewat OAI_CORE_CONTAINERS (comp_id -> nama container).

    Kontrak adapter sama persis dengan DockerCoreAdapter
    (list/get/restart/jitter_health/get_logs) — frontend tidak perlu diubah.
    """

    CACHE_TTL = 2.5  # detik; telemetry push tiap 3 detik, hindari spam SSH

    def __init__(self, container_map: dict, ssh_host: str, ssh_user: str,
                 ssh_password: str, ssh_port: int = 22):
        self._map = container_map
        self._ssh = {
            "host": ssh_host,
            "port": ssh_port,
            "user": ssh_user,
            "password": ssh_password,
        }
        self._conn = None          # paramiko client persistent (lazy connect)
        self._cache: dict = {}     # comp_id -> dict komponen
        self._last_fetch = 0.0

    # ------------------------------------------------------------------
    # Kontrak adapter
    # ------------------------------------------------------------------

    def list(self) -> List[dict]:
        self._maybe_refresh()
        return [self._cache[c] for c in self._map]

    def get(self, comp_id: str) -> Optional[dict]:
        if comp_id not in self._map:
            return None
        self._maybe_refresh()
        return self._cache.get(comp_id)

    async def restart(self, comp_id: str) -> Optional[dict]:
        if comp_id not in self._map:
            return None
        name = self._map[comp_id]
        err = ""
        try:
            out, err = self._exec(f"docker restart {name}")
        except Exception as e:
            err = str(e)
        # Paksa refresh supaya status terbaru di-fetch ulang
        self._last_fetch = 0
        await asyncio.sleep(2)
        result = self.get(comp_id)
        if result and err and result["status"] != "restarting":
            result = dict(result)
            result["detail"] = f"Restart error: {err[:120]}"
        return result

    def jitter_health(self):
        """No-op — data datang dari Docker nyata, bukan simulasi."""
        pass

    def get_logs(self, comp_id: str, tail: int = 100) -> str:
        if comp_id not in self._map:
            return f"Component '{comp_id}' not mapped in OAI configuration."
        name = self._map[comp_id]
        try:
            out, _ = self._exec(f"docker logs --tail {int(tail)} --timestamps {name}")
            return out or "(tidak ada log)"
        except Exception as e:
            return f"[SSH Error] Gagal ambil log container '{name}': {e}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _maybe_refresh(self):
        now = time.time()
        if now - self._last_fetch < self.CACHE_TTL:
            return
        self._last_fetch = now
        try:
            out, err = self._exec(
                "docker inspect -f '{{.Name}}|{{.State.Status}}|{{.State.StartedAt}}' $(docker ps -aq) 2>/dev/null; "
                "echo '===STATS==='; "
                "docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}' 2>/dev/null"
            )
        except Exception as e:
            print(f"[SshDockerCoreAdapter] SSH ke {self._ssh['host']} gagal: {e}", flush=True)
            for comp_id in self._map:
                self._cache[comp_id] = self._down_component(
                    comp_id, f"SSH ke node Core gagal: {e}")
            return

        inspect_data, stats_data = {}, {}
        if "===STATS===" in out:
            inspect_part, stats_part = out.split("===STATS===", 1)
        else:
            inspect_part, stats_part = out, ""
        for line in inspect_part.splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                name = parts[0].lstrip("/")
                inspect_data[name] = {"state": parts[1], "started_at": parts[2]}
        for line in stats_part.splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) >= 4:
                stats_data[parts[0]] = {
                    "cpu": self._to_float(parts[1]),
                    "mem_usage": parts[2],
                    "mem_pct": self._to_float(parts[3]),
                }

        for comp_id, name in self._map.items():
            info = inspect_data.get(name)
            if info is None:
                self._cache[comp_id] = self._down_component(
                    comp_id, f"Container tidak ditemukan: {name}")
                continue
            stat = stats_data.get(name, {})
            started_at = self._parse_started_at(info["started_at"])
            self._cache[comp_id] = {
                "id": comp_id,
                "name": comp_id.upper(),
                "kind": CORE_KIND_LABELS.get(comp_id, comp_id.upper()),
                "status": self._map_status(info["state"]),
                "detail": f"Container: {name} ({info['state']})",
                "host": self._ssh["host"],   # target SSH console
                "cpu_pct": stat.get("cpu", 0.0),
                "mem_gb": self._parse_mem_usage_gb(stat.get("mem_usage", "")),
                "mem_pct": stat.get("mem_pct", 0.0),
                "throughput_mbps": 0.0,
                "port": 0,
                "latency_ms": 0.0,
                "active_ues": 0,
                "last_updated": time.time(),
                "uptime_seconds": (time.time() - started_at) if started_at else 0,
                "started_at": started_at or time.time(),
            }

    def _down_component(self, comp_id: str, reason: str) -> dict:
        return {
            "id": comp_id,
            "name": comp_id.upper(),
            "kind": CORE_KIND_LABELS.get(comp_id, comp_id.upper()),
            "status": "down",
            "detail": reason,
            "host": self._ssh["host"],
            "cpu_pct": 0.0, "mem_gb": 0.0, "mem_pct": 0.0,
            "throughput_mbps": 0.0, "port": 0, "latency_ms": 0.0,
            "active_ues": 0,
            "last_updated": time.time(),
            "uptime_seconds": 0,
            "started_at": time.time(),
        }

    def _exec(self, cmd: str):
        """Jalankan command di node Core via paramiko (koneksi persistent)."""
        import paramiko
        conn = self._conn
        if conn is None or not conn.get_transport() or not conn.get_transport().is_active():
            conn = paramiko.SSHClient()
            conn.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            conn.connect(
                hostname=self._ssh["host"],
                port=self._ssh["port"],
                username=self._ssh["user"],
                password=self._ssh["password"],
                timeout=8,
                banner_timeout=10,
            )
            self._conn = conn
        _, stdout, stderr = conn.exec_command(cmd, timeout=20)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return out, err

    @staticmethod
    def _to_float(s: str) -> float:
        try:
            return float(str(s).replace("%", "").strip())
        except Exception:
            return 0.0

    @staticmethod
    def _parse_mem_usage_gb(mem_usage: str) -> float:
        """'123MiB / 15.6GiB' -> 0.12 (GB, bagian usage saja)."""
        try:
            usage = mem_usage.split("/")[0].strip()
            num = float(usage[:-3].strip())   # hilangkan suffix KiB/MiB/GiB
            unit = usage[-3:].lower()
            if unit == "kib":
                return num / (1024 ** 2)
            if unit == "mib":
                return num / 1024
            if unit == "gib":
                return num
            return 0.0
        except Exception:
            return 0.0


# ---------------------------------------------------------------------------
# RAN adapters
# ---------------------------------------------------------------------------

class RanAdapter(BaseAdapter):
    """Mock RAN adapter — OAI gNB (softmodem). Sambungkan via SSH/CLI nanti."""

    def __init__(self):
        super().__init__([
            Component("gnb-1", "gNB-1", "OAI gNB (softmodem)", "healthy", "RRC connected UEs: 3",
                       host="172.20.0.110", cpu_pct=42, mem_gb=8.4, mem_pct=52,
                       latency_ms=4.2, active_ues=124),
            Component("gnb-2", "gNB-2", "OAI gNB (softmodem)", "degraded", "High PRB utilization",
                       host="172.20.0.101", cpu_pct=78, mem_gb=11.2, mem_pct=70,
                       latency_ms=9.5, active_ues=61),
            Component("cu", "CU", "Central Unit", "healthy", "F1 link up",
                       host="172.20.0.110", cpu_pct=30, mem_gb=4.1, mem_pct=35, latency_ms=3.8),
            Component("du", "DU", "Distributed Unit", "healthy", "F1 link up",
                       host="172.20.0.110", cpu_pct=25, mem_gb=3.0, mem_pct=28, latency_ms=2.1),
        ])


class SshRanAdapter:
    """
    Adapter RAN berbasis SSH untuk node gNB (mini PC RAN testbed, 10.91.2.152).

    Mendeteksi gNB yang sedang jalan — OAI nr-softmodem ATAU srsRAN (binary `gnb`)
    — lalu melaporkan status proses, uptime, CPU/RAM, konfig (band/freq/PRB/PLMN),
    status koneksi N2 (SCTP 38412) dan E2 (SCTP 36421/36422), plus perkiraan UE
    dari log gNB. Semua data nyata dari mesin, bukan simulasi.

    Konfigurasi via .env:
      OAI_SSH_RAN_HOST / OAI_SSH_RAN_PORT / OAI_SSH_RAN_USER / OAI_SSH_RAN_PASSWORD
    """

    CACHE_TTL = 2.5

    def __init__(self, ssh_host: str, ssh_user: str, ssh_password: str, ssh_port: int = 22):
        self._ssh = {"host": ssh_host, "port": ssh_port, "user": ssh_user, "password": ssh_password}
        self._conn = None
        self._cache: dict = {}
        self._last_fetch = 0.0
        self._cfg = {}        # {type, conf, band, bw, arfcn, plmn, n2_ip} — cache per gNB identity

    # ---------------- kontrak adapter ----------------
    def list(self) -> List[dict]:
        self._maybe_refresh()
        return [self._cache[c] for c in ["gnb"]]

    def get(self, comp_id: str) -> Optional[dict]:
        self._maybe_refresh()
        return self._cache.get(comp_id)

    async def restart(self, comp_id: str) -> Optional[dict]:
        # Restart gNB RF berbahaya saat eksperimen live — dikembalikan apa adanya.
        return self.get(comp_id)

    def jitter_health(self):
        pass

    def get_logs(self, comp_id: str, tail: int = 100) -> str:
        log = self._cfg.get("log", "/home/ran/srsgnb.log")
        try:
            out, _ = self._exec(f"tail -n {int(tail)} {log}")
            return out or "(tidak ada log)"
        except Exception as e:
            return f"[SSH Error] Gagal ambil log gNB: {e}"

    # ---------------- refresh ----------------
    def _maybe_refresh(self):
        now = time.time()
        if now - self._last_fetch < self.CACHE_TTL:
            return
        self._last_fetch = now
        try:
            out, _ = self._exec(
                "for name in gnb nr-softmodem srsgnb; do "
                "m=$(ps -C $name --no-headers -o pid=,etime=,pcpu=,rss=,args= 2>/dev/null | head -1); "
                "[ -n \"$m\" ] && echo \"PROC|$name|$m\"; done; "
                "L=$(ls -t /home/ran/srsgnb*.log /home/ran/gnb*.log 2>/dev/null | head -1); "
                "echo \"LOG|$L\"; "
                "echo \"UE|$(tail -2000 \"$L\" 2>/dev/null | grep -oiE 'rnti[ =]?0x[0-9a-f]+' | sort -u | wc -l)\"; "
                "echo \"N2|$(sudo ss -Sn 2>/dev/null | grep ':38412' | grep -c ESTAB)\"; "
                "echo \"E2|$(sudo ss -Sn 2>/dev/null | grep -E ':36421|:36422' | grep -c ESTAB)\"; "
                "echo \"N2IP|$(sudo ss -Sn 2>/dev/null | grep ':38412' | grep ESTAB | grep -oE '[0-9.]+:38412' | head -1)\""
            )
        except Exception as e:
            print(f"[SshRanAdapter] SSH ke {self._ssh['host']} gagal: {e}", flush=True)
            self._cache["gnb"] = self._down(f"SSH ke node RAN gagal: {e}")
            return

        gtype, proc = None, None
        n2_count = e2_count = ue_count = 0
        n2_ip = ""
        for ln in out.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            if ln.startswith("PROC|"):
                parts = ln.split("|")
                if len(parts) >= 3:
                    gtype = parts[1]
                    rest = parts[2].split(None, 4)  # pid etime pcpu rss [args...]
                    if len(rest) >= 4:
                        proc = {"pid": rest[0], "etime": rest[1], "pcpu": self._to_float(rest[2]),
                                "rss_kb": self._to_float(rest[3]),
                                "args": rest[4] if len(rest) > 4 else ""}
            elif ln.startswith("LOG|"):
                self._cfg["log"] = ln.split("|", 1)[1].strip() or "/home/ran/srsgnb.log"
            elif ln.startswith("UE|"):
                ue_count = int(ln.split("|", 1)[1] or 0)
            elif ln.startswith("N2|"):
                n2_count = int(ln.split("|", 1)[1] or 0)
            elif ln.startswith("E2|"):
                e2_count = int(ln.split("|", 1)[1] or 0)
            elif ln.startswith("N2IP|"):
                n2_ip = ln.split("|", 1)[1] or ""

        if not proc:
            self._cache["gnb"] = self._down("gNB tidak jalan (nr-softmodem/srsRAN tidak ditemukan di RAN)")
            return

        # Ambil config gNB (cache per identity: type + args)
        signature = f"{gtype}::{proc['args']}"
        if self._cfg.get("_sig") != signature:
            # keep log path (bisa berubah saat gNB restart) tapi config di-refetch
            self._cfg = self._fetch_config(gtype, proc["args"])
            self._cfg["_sig"] = signature

        n2_desc = n2_ip if n2_ip else f"{n2_count} koneksi"
        e2_desc = f"{e2_count} sesi E2" if e2_count else "tidak ada"
        uptime = self._parse_etime(proc["etime"])
        mem_gb = proc["rss_kb"] / (1024 * 1024)
        mem_total = 15.9  # total RAM node RAN (GB) — dipakai buat mem_pct kasaran
        mem_pct = round(min(100.0, mem_gb / mem_total * 100), 2)

        detail = (
            f"{self._cfg.get('type', gtype)} | n{self._cfg.get('band', '?')} "
            f"{self._cfg.get('bw', '?')}MHz | ARFCN {self._cfg.get('arfcn', '?')} | PLMN {self._cfg.get('plmn', '?')} "
            f"| N2: {n2_desc} | E2: {e2_desc}"
        )
        self._cache["gnb"] = {
            "id": "gnb",
            "name": "gNB",
            "kind": self._cfg.get("type", "gNB"),
            "status": "healthy",
            "detail": detail,
            "host": self._ssh["host"],
            "cpu_pct": round(proc["pcpu"], 2),
            "mem_gb": round(mem_gb, 2),
            "mem_pct": mem_pct,
            "throughput_mbps": 0.0,
            "port": 38412,
            "latency_ms": 0.0,
            "active_ues": ue_count if ue_count else 0,
            "last_updated": time.time(),
            "uptime_seconds": uptime,
            "started_at": time.time() - uptime,
        }
        # simpankan juga log aktif buat get_logs
        if "log" not in self._cfg:
            self._cfg["log"] = self._guess_active_log(gtype)

    # ---------------- helpers ----------------
    def _guess_active_log(self, gtype) -> str:
        try:
            out, _ = self._exec(
                "ls -t /home/ran/gnb*.log /home/ran/srsgnb*.log 2>/dev/null | head -1")
            p = out.strip().splitlines()
            return p[0] if p and p[0].strip() else "/home/ran/srsgnb.log"
        except Exception:
            return "/home/ran/srsgnb.log"

    def _fetch_config(self, gtype, args) -> dict:
        import re
        cfg = {"type": "", "band": "", "bw": "", "arfcn": "", "plmn": ""}
        if gtype == "nr-softmodem":
            cfg["type"] = "OAI nr-softmodem"
            m = re.search(r"-O\s+(\S+)", args)
            path = m.group(1) if m else None
            if path and "/" not in path:
                path = f"/home/ran/{path}"
            if path:
                try:
                    o, _ = self._exec(f"grep -iE 'dl_frequencyBand|dl_carrierBandwidth|bands[[:space:]]*=' {path} | head -5")
                    for ln in o.splitlines():
                        kv = re.search(r'([A-Za-z_]+)\s*=\s*([^;]+)', ln)
                        if kv:
                            k, v = kv.group(1).lower(), kv.group(2).strip()
                            if "band" in k and not cfg["band"]:
                                cfg["band"] = v
                            elif "carrierbandwidth" in k and not cfg["bw"]:
                                cfg["bw"] = v
                    cfg["conf"] = path
                except Exception:
                    pass
        else:
            cfg["type"] = "srsRAN gNB"
            m = re.search(r"-c\s+(\S+)", args)
            path = m.group(1) if m else None
            if path and not path.startswith("/"):
                path = f"/home/ran/{path}"
            cfg["conf"] = path or ""
            if path:
                try:
                    o, _ = self._exec(
                        f"grep -iE 'band:|dl_arfcn:|channel_bandwidth_MHz|plmn:' {path} | head -8")
                    for ln in o.splitlines():
                        kv = re.search(r'([A-Za-z_]+)\s*:\s*"?([A-Za-z0-9_.]+)', ln)
                        if kv:
                            k = kv.group(1).lower()
                            v = kv.group(2)
                            if k == "band":
                                cfg["band"] = v
                            elif k == "dl_arfcn":
                                cfg["arfcn"] = v
                            elif "bandwidth" in k:
                                cfg["bw"] = v
                            elif k == "plmn":
                                cfg["plmn"] = v
                except Exception:
                    pass
        return cfg

    def _down(self, reason) -> dict:
        return {
            "id": "gnb", "name": "gNB", "kind": "gNB", "status": "down",
            "detail": reason, "host": self._ssh["host"],
            "cpu_pct": 0.0, "mem_gb": 0.0, "mem_pct": 0.0,
            "throughput_mbps": 0.0, "port": 38412, "latency_ms": 0.0, "active_ues": 0,
            "last_updated": time.time(), "uptime_seconds": 0, "started_at": time.time(),
        }

    def _exec(self, cmd):
        import paramiko
        conn = self._conn
        if conn is None or not conn.get_transport() or not conn.get_transport().is_active():
            conn = paramiko.SSHClient()
            conn.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            conn.connect(hostname=self._ssh["host"], port=self._ssh["port"],
                         username=self._ssh["user"], password=self._ssh["password"],
                         timeout=8, banner_timeout=10)
            self._conn = conn
        _, stdout, stderr = conn.exec_command(cmd, timeout=20)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return out, err

    @staticmethod
    def _to_float(s) -> float:
        try:
            return float(str(s).replace("%", "").strip())
        except Exception:
            return 0.0

    @staticmethod
    def _parse_etime(etime) -> int:
        try:
            d = 0
            hms = etime
            if "-" in etime:
                d, hms = etime.split("-", 1)
                d = int(d)
            parts = [int(x) for x in hms.split(":")]
            if len(parts) == 3:
                h, m, s = parts
            elif len(parts) == 2:
                h, m, s = 0, parts[0], parts[1]
            else:
                h, m, s = 0, 0, parts[0]
            return d * 86400 + h * 3600 + m * 60 + s
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# srsRAN-specific SSH adapter
# ---------------------------------------------------------------------------

class SrsRanSshAdapter(SshRanAdapter):
    """Adapter RAN khusus srsRAN gNB — monitoer proses 'gnb' saja via SSH.

    Warisan dari SshRanAdapter, tapi override _maybe_refresh() supaya
    hanya mencari proses srsRAN (gnb), bukan OAI (nr-softmodem).
    Env vars sama: SRSRAN_SSH_HOST / SRSRAN_SSH_USER / SRSRAN_SSH_PASSWORD / SRSRAN_SSH_PORT
    """

    def __init__(self, ssh_host: str, ssh_user: str, ssh_password: str, ssh_port: int = 22):
        super().__init__(ssh_host, ssh_user, ssh_password, ssh_port)

    def _maybe_refresh(self):
        now = time.time()
        if now - self._last_fetch < self.CACHE_TTL:
            return
        self._last_fetch = now
        try:
            out, _ = self._exec(
                "m=$(ps -C gnb --no-headers -o pid=,etime=,pcpu=,rss=,args= 2>/dev/null | head -1); "
                "[ -n \"$m\" ] && echo \"PROC|gnb|$m\"; "
                "L=$(ls -t /home/ran/gnb*.log 2>/dev/null | head -1); "
                "echo \"LOG|$L\"; "
                "echo \"UE|$(tail -2000 \"$L\" 2>/dev/null | grep -oiE 'rnti[ =]?0x[0-9a-f]+' | sort -u | wc -l)\"; "
                "echo \"N2|$(sudo ss -Sn 2>/dev/null | grep ':38412' | grep -c ESTAB)\"; "
                "echo \"E2|$(sudo ss -Sn 2>/dev/null | grep -E ':36421|:36422' | grep -c ESTAB)\"; "
                "echo \"N2IP|$(sudo ss -Sn 2>/dev/null | grep ':38412' | grep ESTAB | grep -oE '[0-9.]+:38412' | head -1)\""
            )
        except Exception as e:
            print(f"[SrsRanSshAdapter] SSH ke {self._ssh['host']} gagal: {e}", flush=True)
            self._cache["gnb"] = self._down(f"SSH ke node RAN gagal: {e}")
            return

        gtype, proc = None, None
        n2_count = e2_count = ue_count = 0
        n2_ip = ""
        for ln in out.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            if ln.startswith("PROC|"):
                parts = ln.split("|")
                if len(parts) >= 3:
                    gtype = parts[1]
                    rest = parts[2].split(None, 4)
                    if len(rest) >= 4:
                        proc = {"pid": rest[0], "etime": rest[1], "pcpu": self._to_float(rest[2]),
                                "rss_kb": self._to_float(rest[3]),
                                "args": rest[4] if len(rest) > 4 else ""}
            elif ln.startswith("LOG|"):
                self._cfg["log"] = ln.split("|", 1)[1].strip() or "/home/ran/gnb.log"
            elif ln.startswith("UE|"):
                ue_count = int(ln.split("|", 1)[1] or 0)
            elif ln.startswith("N2|"):
                n2_count = int(ln.split("|", 1)[1] or 0)
            elif ln.startswith("E2|"):
                e2_count = int(ln.split("|", 1)[1] or 0)
            elif ln.startswith("N2IP|"):
                n2_ip = ln.split("|", 1)[1] or ""

        if not proc:
            self._cache["gnb"] = self._down("srsRAN gNB tidak jalan (proses 'gnb' tidak ditemukan di RAN)")
            return

        signature = f"{gtype}::{proc['args']}"
        if self._cfg.get("_sig") != signature:
            self._cfg = self._fetch_config(gtype, proc["args"])
            self._cfg["_sig"] = signature

        n2_desc = n2_ip if n2_ip else f"{n2_count} koneksi"
        e2_desc = f"{e2_count} sesi E2" if e2_count else "tidak ada"
        uptime = self._parse_etime(proc["etime"])
        mem_gb = proc["rss_kb"] / (1024 * 1024)
        mem_total = 15.9
        mem_pct = round(min(100.0, mem_gb / mem_total * 100), 2)

        detail = (
            f"srsRAN gNB | n{self._cfg.get('band', '?')} "
            f"{self._cfg.get('bw', '?')}MHz | ARFCN {self._cfg.get('arfcn', '?')} | PLMN {self._cfg.get('plmn', '?')} "
            f"| N2: {n2_desc} | E2: {e2_desc}"
        )
        self._cache["gnb"] = {
            "id": "gnb",
            "name": "srsRAN gNB",
            "kind": "srsRAN gNB",
            "status": "healthy",
            "detail": detail,
            "host": self._ssh["host"],
            "cpu_pct": round(proc["pcpu"], 2),
            "mem_gb": round(mem_gb, 2),
            "mem_pct": mem_pct,
            "throughput_mbps": 0.0,
            "port": 38412,
            "latency_ms": 0.0,
            "active_ues": ue_count if ue_count else 0,
            "last_updated": time.time(),
            "uptime_seconds": uptime,
            "started_at": time.time() - uptime,
        }
        if "log" not in self._cfg:
            self._cfg["log"] = self._guess_active_log(gtype)


# ---------------------------------------------------------------------------
# RIC adapters
# ---------------------------------------------------------------------------

class RicAdapter(BaseAdapter):
    """Mock RIC adapter — FlexRIC near-RT xApps + non-RT RIC."""

    def __init__(self):
        super().__init__([
            Component("xapp-kpimon", "KPIMON", "near-RT RIC xApp", "healthy", "E2 subscription active", host="172.20.0.120"),
            Component("xapp-anomaly", "Anomaly-Detector", "near-RT RIC xApp", "healthy", "Model v0.3 loaded", host="172.20.0.121"),
            Component("xapp-healer", "Auto-Healer", "near-RT RIC xApp", "healthy", "Standing by", host="172.20.0.122"),
            Component("nonrt-ric", "non-RT RIC", "A1 policy controller", "healthy", "2 policies active",
                       host="172.20.0.123", cpu_pct=14.2, mem_gb=2.4, mem_pct=38, latency_ms=1.2),
        ])


# ---------------------------------------------------------------------------
# Magma Core adapter (skeleton — belum diimplementasi)
# ---------------------------------------------------------------------------

class MagmaCoreAdapter:
    """
    Adapter Core berbasis Magma Orchestrator (Orc8R) REST API.
    Jika belum dikonfigurasi, mengembalikan status 'down' secara rapi alih-alih raise 500.
    """

    def __init__(self, orc8r_url: str = "", api_key: str = "", network_id: str = ""):
        self.orc8r_url = orc8r_url
        self.api_key = api_key
        self.network_id = network_id
        self._components = ["agw-1", "agw-2", "orc8r"]

    def list(self) -> List[dict]:
        now = time.time()
        return [
            {
                "id": c,
                "name": c.upper(),
                "kind": "Magma AGW / Orc8R",
                "status": "down",
                "detail": "Magma Orchestrator REST API not connected",
                "host": self.orc8r_url or "",
                "cpu_pct": 0.0, "mem_gb": 0.0, "mem_pct": 0.0,
                "throughput_mbps": 0.0, "port": 0, "latency_ms": 0.0,
                "active_ues": 0,
                "last_updated": now,
                "uptime_seconds": 0,
                "started_at": now,
            }
            for c in self._components
        ]

    def get(self, comp_id: str) -> Optional[dict]:
        items = self.list()
        return next((i for i in items if i["id"] == comp_id), None)

    async def restart(self, comp_id: str) -> Optional[dict]:
        return self.get(comp_id)

    def get_logs(self, comp_id: str, tail: int = 100) -> str:
        return f"[Magma Orc8R Log] Component '{comp_id}' REST API endpoint ({self.orc8r_url or 'unconfigured'}) is currently offline."

    def jitter_health(self) -> None:
        pass  # no-op


# ---------------------------------------------------------------------------
# Provider registry — ini yang di-import main.py
# ---------------------------------------------------------------------------

def _build_core_providers() -> dict:
    """
    Membangun dict provider Core dari environment variables.
    Dipanggil SEKALI saat modul ini di-import (saat backend start).

    Urutan insert menentukan provider mana yang jadi "default" (first) —
    default provider dapat live update via WebSocket telemetry.
    Provider lain diambil sekali via REST saat tab-nya diklik di frontend.
    """
    providers = {}

    # --- OAI Core via Docker (SSH atau Docker Engine API) ---
    oai_containers_raw = os.environ.get("OAI_CORE_CONTAINERS", "")
    oai_ssh_host = os.environ.get("OAI_SSH_HOST", "") or None
    oai_docker_host = os.environ.get("OAI_DOCKER_HOST", "") or None

    # Pemetaan default sesuai container yang ada di mini PC testbed (CORE 10.91.2.151)
    DEFAULT_OAI_CONTAINER_MAP = {
        "amf": "oai-amf", "smf": "oai-smf", "upf": "oai-upf", "nrf": "oai-nrf",
        "ausf": "oai-ausf", "udm": "oai-udm", "udr": "oai-udr",
        "mysql": "mysql", "ext-dn": "oai-ext-dn",
    }
    if oai_containers_raw:
        try:
            container_map = json.loads(oai_containers_raw)
        except Exception:
            container_map = DEFAULT_OAI_CONTAINER_MAP
    elif oai_ssh_host or oai_docker_host:
        container_map = DEFAULT_OAI_CONTAINER_MAP
    else:
        container_map = {}

    if oai_ssh_host and container_map:
        # Mode SSH: perintah docker dijalankan remote via paramiko — paling pas
        # untuk backend di PC developer yang menembak mini PC testbed.
        adapter = SshDockerCoreAdapter(
            container_map,
            ssh_host=oai_ssh_host,
            ssh_user=os.environ.get("OAI_SSH_USER", "core"),
            ssh_password=os.environ.get("OAI_SSH_PASSWORD", ""),
            ssh_port=int(os.environ.get("OAI_SSH_PORT", "22")),
        )
    elif container_map:
        try:
            adapter = DockerCoreAdapter(container_map, docker_host=oai_docker_host)
        except Exception:
            # Docker tidak reachable atau env tidak valid → fallback ke mock
            adapter = CoreAdapter()
    else:
        adapter = CoreAdapter()  # fallback mock
    providers["oai"] = {
        "label": "OAI 5GC",
        "icon": "cloud_done",
        "desc": "OpenAirInterface 5G Core (Docker via SSH/API)",
        "adapter": adapter,
    }

    # --- open5gs via Docker ---
    open5gs_raw = os.environ.get("OPEN5GS_CORE_CONTAINERS", "")
    open5gs_docker_host = os.environ.get("OPEN5GS_DOCKER_HOST", "") or None
    if open5gs_raw:
        try:
            container_map = json.loads(open5gs_raw)
            adapter_5gs = DockerCoreAdapter(container_map, docker_host=open5gs_docker_host)
        except Exception:
            adapter_5gs = CoreAdapter()
    else:
        adapter_5gs = CoreAdapter()  # fallback mock
    providers["open5gs"] = {
        "label": "open5gs",
        "icon": "dns",
        "desc": "open5gs 5G Core (Docker Engine API)",
        "adapter": adapter_5gs,
    }

    # --- Magma (Orc8R) ---
    magma_url = os.environ.get("MAGMA_ORC8R_URL", "")
    magma_adapter = MagmaCoreAdapter(
        orc8r_url=magma_url,
        api_key=os.environ.get("MAGMA_API_KEY", ""),
        network_id=os.environ.get("MAGMA_NETWORK_ID", ""),
    )
    providers["magma"] = {
        "label": "Magma",
        "icon": "hub",
        "desc": "Magma AGW via Orchestrator REST API (belum tersambung)",
        "adapter": magma_adapter,
    }

    return providers


def _build_ran_providers() -> dict:
    """RAN providers — aktif real via SSH kalau host di-set, fallback mock.

    Dua provider:
      - oai    : OAI nr-softmodem (OAI_SSH_RAN_HOST)
      - srsran : srsRAN gNB (SRSRAN_SSH_HOST)
    """
    providers = {}

    # --- OAI RAN ---
    ssh_host = os.environ.get("OAI_SSH_RAN_HOST", "") or None
    if ssh_host:
        adapter = SshRanAdapter(
            ssh_host=ssh_host,
            ssh_user=os.environ.get("OAI_SSH_RAN_USER", "ran"),
            ssh_password=os.environ.get("OAI_SSH_RAN_PASSWORD", ""),
            ssh_port=int(os.environ.get("OAI_SSH_RAN_PORT", "22")),
        )
        desc = "OAI / srsRAN gNB (real via SSH)"
    else:
        adapter = RanAdapter()
        desc = "OpenAirInterface gNB (softmodem mock)"
    providers["oai"] = {
        "label": "OAI RAN",
        "icon": "settings_input_antenna",
        "desc": desc,
        "adapter": adapter,
    }

    # --- srsRAN ---
    srsran_host = os.environ.get("SRSRAN_SSH_HOST", "") or None
    if srsran_host:
        srsran_adapter = SrsRanSshAdapter(
            ssh_host=srsran_host,
            ssh_user=os.environ.get("SRSRAN_SSH_USER", "ran"),
            ssh_password=os.environ.get("SRSRAN_SSH_PASSWORD", ""),
            ssh_port=int(os.environ.get("SRSRAN_SSH_PORT", "22")),
        )
        srsran_desc = "srsRAN gNB (real via SSH)"
    else:
        srsran_adapter = RanAdapter()
        srsran_desc = "srsRAN gNB (mock)"
    providers["srsran"] = {
        "label": "srsRAN",
        "icon": "cell_tower",
        "desc": srsran_desc,
        "adapter": srsran_adapter,
    }

    return providers


DOMAIN_PROVIDERS = {
    "core": _build_core_providers(),
    "ran": _build_ran_providers(),
    "ric": {
        "oai": {
            "label": "FlexRIC",
            "icon": "memory",
            "desc": "FlexRIC near-RT RIC & xApps (mock)",
            "adapter": RicAdapter(),
        },
    },
}
