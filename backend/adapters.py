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


def _sh_quote(s: str) -> str:
    """Quote aman utk shell (shlex.quote; fallback manual kalau modul hilang)."""
    try:
        import shlex
        return shlex.quote(s)
    except Exception:
        return "'" + str(s).replace("'", "'\\''") + "'"


# Port kanonik per NF (informasi UI; bukan hasil probe aktif — jujur & statis)
NF_PORT_HINTS = {
    "amf": 38412,   # N2 SCTP
    "smf": 38412,   # PFCP/N4 ke UPF via smf (N4 8805 UDP utk open5gs; OAI PFCP)
    "upf": 2152,    # GTP-U
    "nrf": 8080,    # SBI HTTP-2 / REST
    "ausf": 8080,
    "udm": 8080,
    "udr": 8080,
}

# Pemetaan default comp_id -> prefix pod di namespace K8s 5g-core
# (deployment oai-amf -> pod oai-amf-<rs>-<hash>). Bisa dioverride via
# env OAI_K8S_COMPONENT_MAP (JSON) tanpa ubah kode.
DEFAULT_OAI_K8S_COMPONENT_MAP = {
    "amf": "oai-amf",
    "smf": "oai-smf",
    "upf": "oai-upf",
    "nrf": "oai-nrf",
    "ausf": "oai-ausf",
    "udm": "oai-udm",
    "udr": "oai-udr",
}

# Pemetaan default open5gs: helm chart open5gs-chart -> open5gs-amf
# Label K8s: app.kubernetes.io/name=<comp_id> (e.g. amf), app.kubernetes.io/instance=open5gs-chart
# Bisa dioverride via env OPEN5GS_K8S_COMPONENT_MAP (JSON).
DEFAULT_OPEN5GS_K8S_COMPONENT_MAP = {
    "amf": "open5gs-amf",
    "smf": "open5gs-smf",
    "upf": "open5gs-upf",
    "ausf": "open5gs-ausf",
    "nrf": "open5gs-nrf",
    "udm": "open5gs-udm",
    "udr": "open5gs-udr",
    "pcf": "open5gs-pcf",
    "bsf": "open5gs-bsf",
    "nssf": "open5gs-nssf",
    "scp": "open5gs-scp",
    "sepp": "open5gs-sepp",
    "mongodb": "open5gs-mongodb",
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


class KubectlOaiCoreAdapter:
    """
    Adapter Core OAI berbasis Kubernetes — membaca state 5GC langsung dari
    cluster K8s (Fase 1 plan exclusive-core-ran: read-only visibility).

    Latar belakang: OAI 5GC sudah migrasi Docker Compose -> Kubernetes.
    Adapter lama (SshDockerCoreAdapter) salah sasaran karena SSH ke node core
    lalu docker-exec kontainer Open5GS legacy di network demo-oai-public-net
    (192.168.70.128/26) — itu BUKAN 5GC yang aktif. Adapter ini menggantikan
    mekanisme pembacaannya: tetap via paramiko SSH, tapi perintahnya kubectl:

        sudo kubectl --kubeconfig=/etc/kubernetes/admin.conf -n 5g-core ...

    Node target = master K8s (OAI_K8S_SSH_HOST, default 10.91.2.156). Hanya
    master yang punya /etc/kubernetes/admin.conf; worker .151/.152 tidak.
    admin.conf root-only (600), jadi tiap perintah dibungkus `sudo -S`
    dengan password dari env (K8S_SUDO_PASSWORD, fallback OAI_SSH_PASSWORD).

    READ-ONLY: hanya get/describe/top/logs. Tidak ada actuation cluster
    (scale/delete/apply/restart) dan tidak menyentuh N2/N3/GTP routes.
    restart() komponen sengaja TIDAK dieksekusi ke cluster — cukup bookkeeping
    status restarting sesuai kontrak adapter (aktuator menyusul di Fase 2+).

    Konfigurasi via .env:
      OAI_K8S_SSH_HOST     (default 10.91.2.156)
      OAI_K8S_SSH_PORT     (default 22)
      OAI_K8S_SSH_USER     (default telmat)
      OAI_K8S_SSH_PASSWORD / K8S_SUDO_PASSWORD
      OAI_K8S_NAMESPACE    (default 5g-core)
      OAI_K8S_ADMIN_CONF   (default /etc/kubernetes/admin.conf)

    Kontrak adapter sama dengan adapter core lain
    (list/get/restart/jitter_health/get_logs) — frontend tidak berubah.
    """

    CACHE_TTL = 2.5  # detik; telemetry push tiap 3 dtk, hindari spam SSH

    def __init__(self, component_map: dict, ssh_host: str, ssh_user: str,
                 ssh_password: str = "", sudo_password: str = "",
                 ssh_port: int = 22, namespace: str = "5g-core",
                 kubeconfig: str = "/etc/kubernetes/admin.conf",
                 kubectl_bin: str = "kubectl"):
        self._map = dict(component_map)  # comp_id -> prefix pod (mis. "oai-amf")
        self._ssh = {
            "host": ssh_host,
            "port": int(ssh_port),
            "user": ssh_user,
            "password": ssh_password,
            "sudo": sudo_password or ssh_password,
        }
        self._ns = namespace
        self._kubeconfig = kubeconfig
        self._kubectl = kubectl_bin
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
        """Read-only Fase 1: TIDAK mengeksekusi apa pun ke cluster.

        Status 'restarting' murni indikasi UI sesaat (kontrak adapter),
        lalu data live berikutnya dari cluster yang menentukan lagi.
        Actuation (rollout restart dsb.) masuk Fase 2 dengan approval."""
        if comp_id not in self._map:
            return None
        await asyncio.sleep(1.5)
        self.get(comp_id)
        result = dict(self._cache.get(comp_id) or {})
        if result and result.get("status") == "healthy":
            result["status"] = "restarting"
            result["detail"] = (
                "Restart request noted (read-only mode; no cluster action)")
            result["last_updated"] = time.time()
        return result

    def jitter_health(self):
        """No-op — status datang dari cluster nyata, bukan simulasi."""
        pass

    def get_logs(self, comp_id: str, tail: int = 100) -> str:
        """Log pod NF via kubectl logs (read-only)."""
        if comp_id not in self._map:
            return f"Component '{comp_id}' not mapped in K8s configuration."
        try:
            out, err = self._exec(
                f"{self._kctl()} -n {self._ns} logs --tail={int(tail)} "
                f"--timestamps -l app={self._map[comp_id]}")
            return (out or "").strip() or (
                err.strip() or f"(tidak ada log untuk {self._map[comp_id]})")
        except Exception as e:
            return f"[SSH Error] Gagal ambil log '{comp_id}' via kubectl: {e}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _kctl(self) -> str:
        """Prefix perintah kubectl lengkap dengan kubeconfig admin."""
        return (f"sudo -S -p '' {self._kubectl} "
                f"--kubeconfig={self._kubeconfig}")

    def _exec(self, cmd: str):
        """Jalankan command di node K8s via paramiko (koneksi persistent).

        Password sudo dikirim via stdin (echo <pw> | sudo -S) — tidak pernah
        masuk argv proses maupun log. cmd TIDAK boleh berisi input user."""
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
        full = f"echo {_sh_quote(self._ssh['sudo'])} | {cmd}"
        _, stdout, stderr = conn.exec_command(full, timeout=25)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return out, err

    def _maybe_refresh(self):
        """Fetch ulang state cluster (dibatasi CACHE_TTL supaya tidak spam SSH).

        Satu round-trip SSH menggabungkan 4 bacaan read-only:
          1. get pods -o wide          -> phase/status/node/pod-ip per NF
          2. get pods custom-columns   -> status.startTime (sumber uptime)
          3. kubectl top pods          -> CPU/mem real (butuh metrics-server)
          4. get svc amf,upf           -> ClusterIP endpoint AMF(N2)/UPF(GTP)
        """
        now = time.time()
        if now - self._last_fetch < self.CACHE_TTL:
            return
        self._last_fetch = now
        kc = self._kctl()
        try:
            out, err = self._exec(
                f"{kc} -n {self._ns} get pods -o wide --no-headers; "
                f"echo '===STARTED==='; "
                f"{kc} -n {self._ns} get pods -o custom-columns="
                f"':metadata.name,:status.startTime' --no-headers; "
                f"echo '===METRICS==='; "
                f"{kc} -n {self._ns} top pods --no-headers 2>/dev/null; "
                f"echo '===SVC==='; "
                f"{kc} -n {self._ns} get svc amf,upf -o custom-columns="
                f"':metadata.name,:spec.clusterIP' --no-headers 2>/dev/null"
            )
        except Exception as e:
            print(f"[KubectlOaiCoreAdapter] SSH ke {self._ssh['host']} gagal: {e}",
                  flush=True)
            for comp_id in self._map:
                self._cache[comp_id] = self._down_component(
                    comp_id, f"SSH ke node K8s gagal: {e}")
            return

        if "===STARTED===" not in out:
            # kubectl/sudo gagal total (password salah, admin.conf hilang, dsb.)
            reason = (err or out or "kubectl tidak mengembalikan data").strip()
            for comp_id in self._map:
                self._cache[comp_id] = self._down_component(
                    comp_id, f"kubectl gagal: {reason[:160]}")
            return

        pods, started, metrics, svcs = {}, {}, {}, {}
        section = "pods"
        for raw in out.splitlines():
            line = raw.strip()
            if line == "===STARTED===":
                section = "started"; continue
            if line == "===METRICS===":
                section = "metrics"; continue
            if line == "===SVC===":
                section = "svc"; continue
            if not line:
                continue
            if section == "pods":
                # Robust parse: NAME READY STATUS RESTARTS AGE IP NODE ...
                # but RESTARTS field may be "100 (79s ago)" -> extra tokens, so IP not fixed index
                # Detect IP by regex and node is token after IP
                import re
                tokens = line.split()
                if len(tokens) >= 6:
                    name = tokens[0]
                    ready = tokens[1] if len(tokens) > 1 else ""
                    phase = tokens[2] if len(tokens) > 2 else ""
                    restarts = tokens[3] if len(tokens) > 3 else "0"
                    pod_ip = ""
                    node = ""
                    for idx, tok in enumerate(tokens):
                        if re.match(r'^\d+\.\d+\.\d+\.\d+$', tok) and tok != "<none>":
                            pod_ip = tok
                            if idx + 1 < len(tokens):
                                node = tokens[idx + 1]
                            break
                        if tok == "<none>":
                            pod_ip = "<none>"
                    pods[name] = {
                        "ready": ready, "phase": phase,
                        "restarts": restarts,
                        "pod_ip": pod_ip,
                        "node": node,
                    }
            elif section == "started":
                p = line.split()
                if len(p) >= 2:
                    started[p[0]] = "" if p[1] == "<none>" else p[1]
            elif section == "metrics":
                p = line.split()
                # metrics-server formats: either 5 cols (NAME CPU CPU% MEM MEM%) or 3 cols (NAME CPU MEM)
                # contoh baru k8s 1.29: open5gs-amf-xyz 1m 104Mi
                if len(p) >= 5:
                    metrics[p[0]] = {
                        "cpu_pct": self._cpu_to_pct(p[1]),
                        "mem_mi": self._to_float_mi(p[3]),
                    }
                elif len(p) >= 3:
                    metrics[p[0]] = {
                        "cpu_pct": self._cpu_to_pct(p[1]),
                        "mem_mi": self._to_float_mi(p[2]),
                    }
            elif section == "svc":
                p = line.split()
                if len(p) >= 2:
                    svcs[p[0]] = p[1]

        for comp_id, prefix in self._map.items():
            entry = None
            for pod_name, info in pods.items():
                if pod_name == prefix or pod_name.startswith(prefix + "-"):
                    entry = (pod_name, info)
                    break
            if entry is None:
                self._cache[comp_id] = self._down_component(
                    comp_id, f"Pod tidak ditemukan di ns {self._ns}: {prefix}*")
                continue
            pod_name, info = entry
            phase = info["phase"]
            status = self._map_k8s_status(phase, info["restarts"])
            start_iso = started.get(pod_name, "")
            started_at = self._parse_start_time(start_iso)
            met = metrics.get(pod_name, {})
            detail_bits = [f"Pod {pod_name} ({phase}, {info['ready']})"]
            if info["node"]:
                detail_bits.append(f"node {info['node']}")
            if info["pod_ip"]:
                detail_bits.append(f"podIP {info['pod_ip']}")
            if status == "degraded" and info["restarts"] not in ("0",):
                detail_bits.append(f"restarts={info['restarts']}")
            ep = svcs.get(comp_id)
            if comp_id == "amf" and svcs.get("amf") not in (None, "None"):
                detail_bits.append(f"N2 endpoint svc/amf {svcs['amf']}")
            elif ep and ep != "None":
                detail_bits.append(f"svc {comp_id} {ep}")
            # Sanitize: strip any raw ss/ESTAB IP:port noise if it leaks into detail
            detail_str = " • ".join(detail_bits)
            detail_str = self._strip_estab(detail_str)
            self._cache[comp_id] = {
                "id": comp_id,
                "name": comp_id.upper(),
                "kind": CORE_KIND_LABELS.get(comp_id, comp_id.upper()),
                "status": status,
                "detail": detail_str,
                "host": info["pod_ip"] if info["pod_ip"] and info["pod_ip"] != "<none>" else None,
                "cpu_pct": met.get("cpu_pct", 0.0),
                "mem_gb": round(met.get("mem_mi", 0.0) / 1024.0, 2),
                "mem_pct": 0.0,  # persen butuh kapasitas node; sengaja 0 (jujur)
                "throughput_mbps": 0.0,
                "port": NF_PORT_HINTS.get(comp_id, 0),
                "latency_ms": 0.0,
                "active_ues": 0,
                "last_updated": time.time(),
                "uptime_seconds": (time.time() - started_at) if started_at else 0,
                "started_at": started_at or time.time(),
            }

    @staticmethod
    def _strip_estab(detail: str) -> str:
        """Remove raw ss ESTAB IP:port fragments from detail (e.g. 'ESTAB 0 0 10.91.2.152:37713 ...', '%enp1s0')."""
        import re
        if not detail or "ESTAB" not in detail:
            return detail
        parts = [p for p in detail.split(" • ") if "ESTAB" not in p and "%enp" not in p]
        cleaned = " • ".join(parts)
        cleaned = re.sub(r'ESTAB[^•|]*', '', cleaned)
        cleaned = re.sub(r'\|\s*', ' • ', cleaned)
        cleaned = re.sub(r'•\s*•', '•', cleaned)
        cleaned = re.sub(r'^\s*•\s*|\s*•\s*$', '', cleaned).strip()
        return cleaned.strip() or detail.split(" • ")[0]

    @staticmethod
    def _map_k8s_status(phase: str, restarts: str = "0") -> Status:
        """Map fase/status kolom `kubectl get pods` ke 4 nilai frontend."""
        s = (phase or "").lower()
        if "running" in s:
            # Running tapi restart count tinggi = crash-loop tersembunyi
            try:
                if int(str(restarts).split("(")[0]) >= 10:
                    return "degraded"
            except Exception:
                pass
            return "healthy"
        if "pending" in s or "containercreating" in s or "init:" in s:
            return "degraded"
        if "crashloopbackoff" in s or "error" in s or "evicted" in s:
            return "down"
        if "terminated" in s or "completed" in s:
            return "degraded"
        return "degraded"

    @staticmethod
    def _parse_start_time(iso_str: str) -> Optional[float]:
        """ISO timestamp Kubernetes (mis. 2026-08-26T07:01:33Z) -> epoch."""
        if not iso_str:
            return None
        try:
            from datetime import datetime, timezone
            s = iso_str.strip().rstrip("Z")
            if "." in s:
                s = s.split(".")[0]
            dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return None

    @staticmethod
    def _cpu_to_pct(cpu_cores: str) -> float:
        """'125054n' (nanocores) atau '125m' (millicores) -> persen 1 core."""
        try:
            c = cpu_cores.strip().lower()
            if c.endswith("n"):
                return round(float(c[:-1]) / 1e7, 1)   # nano -> % of 1 core
            if c.endswith("m"):
                return round(float(c[:-1]) / 10.0, 1)  # milli -> %
            return round(float(c), 1)
        except Exception:
            return 0.0

    @staticmethod
    def _to_float_mi(mem_val: str) -> float:
        """'25392Mi' / '1Gi' -> MiB float."""
        try:
            v = mem_val.strip().lower()
            if v.endswith("mi"):
                return float(v[:-2])
            if v.endswith("gi"):
                return float(v[:-2]) * 1024
            if v.endswith("ki"):
                return float(v[:-2]) / 1024
            return float(v)
        except Exception:
            return 0.0

    def _down_component(self, comp_id: str, reason: str) -> dict:
        return {
            "id": comp_id,
            "name": comp_id.upper(),
            "kind": CORE_KIND_LABELS.get(comp_id, comp_id.upper()),
            "status": "down",
            "detail": reason,
            "host": None,
            "cpu_pct": 0.0, "mem_gb": 0.0, "mem_pct": 0.0,
            "throughput_mbps": 0.0, "port": 0, "latency_ms": 0.0,
            "active_ues": 0,
            "last_updated": time.time(),
            "uptime_seconds": 0,
            "started_at": time.time(),
        }


class KubectlOpen5gsCoreAdapter:
    """
    Adapter Core open5gs berbasis Kubernetes — membaca state open5GS langsung
    dari cluster K8s (helm chart open5gs-chart, ns open5gs-chart).

    Clone dari KubectlOaiCoreAdapter tapi:
      - DEFAULT_OPEN5GS_K8S_COMPONENT_MAP (open5gs-amf/smf/upf/...)
      - Namespace OPEN5GS_K8S_NAMESPACE (default open5gs-chart -> fallback open5gs)
      - SSH host OPEN5GS_K8S_SSH_HOST fallback OAI_K8S_SSH_HOST (default 10.91.2.156)
      - Label selectors: app.kubernetes.io/name=<comp_id> (bukan app=oai-amf)
        + fallback app=<deploy> untuk kompatibilitas.

    READ-ONLY: hanya get/describe/top/logs. restart() tidak menyentuh cluster.
    host = pod IP (bukan SSH host) supaya frontend menampilkan alamat nyata pod.
    cpu/memory real via `kubectl top pods` (butuh metrics-server).
    """

    CACHE_TTL = 2.5

    def __init__(self, component_map: dict, ssh_host: str, ssh_user: str,
                 ssh_password: str = "", sudo_password: str = "",
                 ssh_port: int = 22, namespace: str = "open5gs-chart",
                 kubeconfig: str = "/etc/kubernetes/admin.conf",
                 kubectl_bin: str = "kubectl"):
        self._map = dict(component_map)
        self._ssh = {
            "host": ssh_host,
            "port": int(ssh_port),
            "user": ssh_user,
            "password": ssh_password,
            "sudo": sudo_password or ssh_password,
        }
        self._ns = namespace
        self._kubeconfig = kubeconfig
        self._kubectl = kubectl_bin
        self._conn = None
        self._cache: dict = {}
        self._last_fetch = 0.0

    def list(self) -> List[dict]:
        self._maybe_refresh()
        return [self._cache[c] for c in self._map]

    def get(self, comp_id: str) -> Optional[dict]:
        if comp_id not in self._map:
            return None
        self._maybe_refresh()
        return self._cache.get(comp_id)

    async def restart(self, comp_id: str) -> Optional[dict]:
        """Read-only Fase 1: TIDAK mengeksekusi apa pun ke cluster."""
        if comp_id not in self._map:
            return None
        await asyncio.sleep(1.5)
        self.get(comp_id)
        result = dict(self._cache.get(comp_id) or {})
        if result and result.get("status") == "healthy":
            result["status"] = "restarting"
            result["detail"] = "Restart request noted (read-only mode; no cluster action)"
            result["last_updated"] = time.time()
        return result

    def jitter_health(self):
        pass

    def get_logs(self, comp_id: str, tail: int = 100) -> str:
        """Log pod NF via kubectl logs dengan label open5gs."""
        if comp_id not in self._map:
            return f"Component '{comp_id}' not mapped in K8s configuration."
        try:
            # Prefer app.kubernetes.io/name, fallback app=deploy
            deploy = self._map[comp_id]
            out, err = self._exec(
                f"{self._kctl()} -n {self._ns} logs --tail={int(tail)} "
                f"--timestamps -l app.kubernetes.io/name={comp_id}")
            if out.strip():
                return out.strip()
            # fallback legacy label app=<deploy>
            out2, err2 = self._exec(
                f"{self._kctl()} -n {self._ns} logs --tail={int(tail)} "
                f"--timestamps -l app={deploy}")
            return (out2 or "").strip() or (err2.strip() or err.strip() or f"(tidak ada log untuk {deploy})")
        except Exception as e:
            return f"[SSH Error] Gagal ambil log '{comp_id}' via kubectl: {e}"

    def _kctl(self) -> str:
        return (f"sudo -S -p '' {self._kubectl} "
                f"--kubeconfig={self._kubeconfig}")

    def _exec(self, cmd: str):
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
        full = f"echo {_sh_quote(self._ssh['sudo'])} | {cmd}"
        _, stdout, stderr = conn.exec_command(full, timeout=25)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return out, err

    def _maybe_refresh(self):
        now = time.time()
        if now - self._last_fetch < self.CACHE_TTL:
            return
        self._last_fetch = now
        kc = self._kctl()
        try:
            out, err = self._exec(
                f"{kc} -n {self._ns} get pods -o wide --no-headers; "
                f"echo '===STARTED==='; "
                f"{kc} -n {self._ns} get pods -o custom-columns="
                f"':metadata.name,:status.startTime' --no-headers; "
                f"echo '===METRICS==='; "
                f"{kc} -n {self._ns} top pods --no-headers 2>/dev/null; "
                f"echo '===SVC==='; "
                f"{kc} -n {self._ns} get svc amf,upf -o custom-columns="
                f"':metadata.name,:spec.clusterIP' --no-headers 2>/dev/null"
            )
        except Exception as e:
            print(f"[KubectlOpen5gsCoreAdapter] SSH ke {self._ssh['host']} gagal: {e}", flush=True)
            for comp_id in self._map:
                self._cache[comp_id] = self._down_component(comp_id, f"SSH ke node K8s gagal: {e}")
            return

        if "===STARTED===" not in out:
            reason = (err or out or "kubectl tidak mengembalikan data").strip()
            for comp_id in self._map:
                self._cache[comp_id] = self._down_component(comp_id, f"kubectl gagal: {reason[:160]}")
            return

        pods, started, metrics, svcs = {}, {}, {}, {}
        section = "pods"
        for raw in out.splitlines():
            line = raw.strip()
            if line == "===STARTED===":
                section = "started"; continue
            if line == "===METRICS===":
                section = "metrics"; continue
            if line == "===SVC===":
                section = "svc"; continue
            if not line:
                continue
            if section == "pods":
                import re
                tokens = line.split()
                if len(tokens) >= 6:
                    name = tokens[0]
                    ready = tokens[1] if len(tokens) > 1 else ""
                    phase = tokens[2] if len(tokens) > 2 else ""
                    restarts = tokens[3] if len(tokens) > 3 else "0"
                    pod_ip = ""
                    node = ""
                    for idx, tok in enumerate(tokens):
                        if re.match(r'^\d+\.\d+\.\d+\.\d+$', tok) and tok != "<none>":
                            pod_ip = tok
                            if idx + 1 < len(tokens):
                                node = tokens[idx + 1]
                            break
                        if tok == "<none>":
                            pod_ip = "<none>"
                    pods[name] = {
                        "ready": ready, "phase": phase,
                        "restarts": restarts,
                        "pod_ip": pod_ip,
                        "node": node,
                    }
            elif section == "started":
                p = line.split()
                if len(p) >= 2:
                    started[p[0]] = "" if p[1] == "<none>" else p[1]
            elif section == "metrics":
                p = line.split()
                # open5gs: support 3-col (1m 104Mi) dan 5-col (100m 1% 250Mi 2%)
                if len(p) >= 5:
                    metrics[p[0]] = {
                        "cpu_pct": self._cpu_to_pct(p[1]),
                        "mem_mi": self._to_float_mi(p[3]),
                    }
                elif len(p) >= 3:
                    metrics[p[0]] = {
                        "cpu_pct": self._cpu_to_pct(p[1]),
                        "mem_mi": self._to_float_mi(p[2]),
                    }
            elif section == "svc":
                p = line.split()
                if len(p) >= 2:
                    svcs[p[0]] = p[1]

        for comp_id, prefix in self._map.items():
            entry = None
            for pod_name, info in pods.items():
                if pod_name == prefix or pod_name.startswith(prefix + "-"):
                    entry = (pod_name, info)
                    break
            if entry is None:
                self._cache[comp_id] = self._down_component(comp_id, f"Pod tidak ditemukan di ns {self._ns}: {prefix}*")
                continue
            pod_name, info = entry
            phase = info["phase"]
            status = self._map_k8s_status(phase, info["restarts"])
            start_iso = started.get(pod_name, "")
            started_at = self._parse_start_time(start_iso)
            met = metrics.get(pod_name, {})
            detail_bits = [f"Pod {pod_name} ({phase}, {info['ready']})"]
            if info["node"]:
                detail_bits.append(f"node {info['node']}")
            if info["pod_ip"]:
                detail_bits.append(f"podIP {info['pod_ip']}")
            if status == "degraded" and info["restarts"] not in ("0",):
                detail_bits.append(f"restarts={info['restarts']}")
            ep = svcs.get(comp_id)
            if comp_id == "amf" and svcs.get("amf") not in (None, "None"):
                detail_bits.append(f"N2 endpoint svc/amf {svcs['amf']}")
            elif ep and ep != "None":
                detail_bits.append(f"svc {comp_id} {ep}")
            # Sanitize: strip any raw ss/ESTAB IP:port noise if it leaks into detail
            detail_str = " • ".join(detail_bits)
            detail_str = self._strip_estab(detail_str)
            # host = pod IP (real), fallback to None if pod IP empty (e.g. pending) — never bare-metal 10.91.2.156
            host_val = info["pod_ip"] if info["pod_ip"] and info["pod_ip"] != "<none>" else None
            self._cache[comp_id] = {
                "id": comp_id,
                "name": comp_id.upper(),
                "kind": CORE_KIND_LABELS.get(comp_id, comp_id.upper()),
                "status": status,
                "detail": detail_str,
                "host": host_val,
                "cpu_pct": met.get("cpu_pct", 0.0),
                "mem_gb": round(met.get("mem_mi", 0.0) / 1024.0, 2),
                "mem_pct": 0.0,
                "throughput_mbps": 0.0,
                "port": NF_PORT_HINTS.get(comp_id, 0),
                "latency_ms": 0.0,
                "active_ues": 0,
                "last_updated": time.time(),
                "uptime_seconds": (time.time() - started_at) if started_at else 0,
                "started_at": started_at or time.time(),
            }

    @staticmethod
    def _strip_estab(detail: str) -> str:
        """Remove raw ss ESTAB IP:port fragments from detail (e.g. 'ESTAB 0 0 10.91.2.152:37713 ...', '%enp1s0')."""
        import re
        if not detail or "ESTAB" not in detail:
            return detail
        parts = [p for p in detail.split(" • ") if "ESTAB" not in p and "%enp" not in p]
        cleaned = " • ".join(parts)
        cleaned = re.sub(r'ESTAB[^•|]*', '', cleaned)
        cleaned = re.sub(r'\|\s*', ' • ', cleaned)
        cleaned = re.sub(r'•\s*•', '•', cleaned)
        cleaned = re.sub(r'^\s*•\s*|\s*•\s*$', '', cleaned).strip()
        return cleaned.strip() or detail.split(" • ")[0]

    @staticmethod
    def _map_k8s_status(phase: str, restarts: str = "0") -> Status:
        s = (phase or "").lower()
        if "running" in s:
            try:
                if int(str(restarts).split("(")[0]) >= 10:
                    return "degraded"
            except Exception:
                pass
            return "healthy"
        if "pending" in s or "containercreating" in s or "init:" in s:
            return "degraded"
        if "crashloopbackoff" in s or "error" in s or "evicted" in s:
            return "down"
        if "terminated" in s or "completed" in s:
            return "degraded"
        return "degraded"

    @staticmethod
    def _parse_start_time(iso_str: str) -> Optional[float]:
        if not iso_str:
            return None
        try:
            from datetime import datetime, timezone
            s = iso_str.strip().rstrip("Z")
            if "." in s:
                s = s.split(".")[0]
            dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return None

    @staticmethod
    def _cpu_to_pct(cpu_cores: str) -> float:
        try:
            c = cpu_cores.strip().lower()
            if c.endswith("n"):
                return round(float(c[:-1]) / 1e7, 1)
            if c.endswith("m"):
                return round(float(c[:-1]) / 10.0, 1)
            return round(float(c), 1)
        except Exception:
            return 0.0

    @staticmethod
    def _to_float_mi(mem_val: str) -> float:
        try:
            v = mem_val.strip().lower()
            if v.endswith("mi"):
                return float(v[:-2])
            if v.endswith("gi"):
                return float(v[:-2]) * 1024
            if v.endswith("ki"):
                return float(v[:-2]) / 1024
            return float(v)
        except Exception:
            return 0.0

    def _down_component(self, comp_id: str, reason: str) -> dict:
        return {
            "id": comp_id,
            "name": comp_id.upper(),
            "kind": CORE_KIND_LABELS.get(comp_id, comp_id.upper()),
            "status": "down",
            "detail": reason,
            "host": None,
            "cpu_pct": 0.0, "mem_gb": 0.0, "mem_pct": 0.0,
            "throughput_mbps": 0.0, "port": 0, "latency_ms": 0.0,
            "active_ues": 0,
            "last_updated": time.time(),
            "uptime_seconds": 0,
            "started_at": time.time(),
        }


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

    def __init__(self, ssh_host: str, ssh_user: str, ssh_password: str, ssh_port: int = 22,
                 binary_hints: list = None):
        self._ssh = {"host": ssh_host, "port": ssh_port, "user": ssh_user, "password": ssh_password}
        self._conn = None
        self._cache: dict = {}
        self._last_fetch = 0.0
        self._cfg = {}        # {type, conf, band, bw, arfcn, plmn, n2_ip} — cache per gNB identity
        # Binary names yang di-scan saat refresh. Pisahkan OAI (nr-softmodem) vs
        # srsRAN (gnb/srsgnb) kalau keduanya di host yang sama agar tidak saling "rebut" proses.
        self._binary_hints = binary_hints or ["gnb", "nr-softmodem", "srsgnb"]

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
            _bins = " ".join(self._binary_hints)
            out, _ = self._exec(
                f"for name in {_bins}; do "
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
        # Uptime: prefer systemctl (jika ada service), fallback ke ps etime — fallback 0 jika gagal
        uptime = self._get_systemd_uptime() or self._parse_etime(proc["etime"])
        mem_gb = proc["rss_kb"] / (1024 * 1024)
        mem_total = 15.9  # total RAM node RAN (GB) — dipakai buat mem_pct kasaran
        mem_pct = round(min(100.0, mem_gb / mem_total * 100), 2)
        # Host via bind_addr dari config (GNB_IPV4_ADDRESS_FOR_NG_AMF), fallback ke SSH host jujur
        host_ip = self._cfg.get("bind_addr") or self._ssh["host"]
        # Latency via ping ke AMF / core — fallback 0 jujur jika tidak reachable
        ping_target = self._cfg.get("amf_ip") or "10.91.2.151"
        latency_ms = self._get_latency_ms(ping_target)

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
            "host": host_ip,
            "cpu_pct": round(proc["pcpu"], 2),
            "mem_gb": round(mem_gb, 2),
            "mem_pct": mem_pct,
            "throughput_mbps": 0.0,
            "port": 38412,
            "latency_ms": latency_ms,
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
        cfg = {"type": "", "band": "", "bw": "", "arfcn": "", "plmn": "", "bind_addr": "", "amf_ip": ""}
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
                    # Host/IP via bind_addr (GNB_IPV4_ADDRESS_FOR_NG_AMF) — real testbed IP
                    o2, _ = self._exec(f"grep -iE 'GNB_IPV4_ADDRESS_FOR_NG_AMF|GNB_IPV4_ADDRESS_FOR_NGU|amf_ip_address' {path} | head -5")
                    for ln2 in o2.splitlines():
                        ip_m = re.search(r'(\d+\.\d+\.\d+\.\d+)', ln2)
                        if ip_m:
                            ip = ip_m.group(1)
                            if "amf_ip_address" in ln2.lower() and not cfg["amf_ip"]:
                                cfg["amf_ip"] = ip
                            elif not cfg["bind_addr"]:
                                cfg["bind_addr"] = ip
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

    def _get_latency_ms(self, target: str) -> float:
        """Ping target via SSH — honest 0.0 jika gagal/tidak reachable."""
        if not target:
            return 0.0
        try:
            out, _ = self._exec(f"ping -c 1 -W 1 {target} 2>/dev/null | grep -oE 'time=[0-9.]+' | head -1")
            import re
            m = re.search(r'time=([0-9.]+)', out)
            if m:
                return round(float(m.group(1)), 2)
        except Exception:
            pass
        return 0.0

    def _get_systemd_uptime(self) -> int:
        """Uptime via systemctl jika ada service gNB, else 0 biar fallback ke ps etime."""
        try:
            for svc in ["gnb", "nr-softmodem", "oai-gnb", "srsran-gnb"]:
                out, _ = self._exec(f"systemctl show {svc} --property=ActiveEnterTimestamp 2>/dev/null | head -1")
                if "ActiveEnterTimestamp=" in out and "n/a" not in out.lower():
                    import re
                    from datetime import datetime, timezone
                    ts_str = out.split("=", 1)[1].strip()
                    try:
                        dt = datetime.strptime(ts_str, "%a %Y-%m-%d %H:%M:%S %Z")
                        dt = dt.replace(tzinfo=timezone.utc)
                        import time as _time
                        return int(_time.time() - dt.timestamp())
                    except Exception:
                        continue
        except Exception:
            pass
        return 0

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
    """Adapter RAN khusus srsRAN gNB — monitor proses 'gnb' saja via SSH.

    Warisan dari SshRanAdapter, tapi override _maybe_refresh() supaya
    hanya mencari proses srsRAN (gnb), bukan OAI (nr-softmodem).
    Env vars: SRSRAN_SSH_HOST / SRSRAN_SSH_USER / SRSRAN_SSH_PASSWORD / SRSRAN_SSH_PORT
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
        uptime = self._get_systemd_uptime() or self._parse_etime(proc["etime"])
        mem_gb = proc["rss_kb"] / (1024 * 1024)
        mem_total = 15.9
        mem_pct = round(min(100.0, mem_gb / mem_total * 100), 2)
        host_ip = self._cfg.get("bind_addr") or self._ssh["host"]
        ping_target = self._cfg.get("amf_ip") or "10.91.2.151"
        latency_ms = self._get_latency_ms(ping_target)

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
            "host": host_ip,
            "cpu_pct": round(proc["pcpu"], 2),
            "mem_gb": round(mem_gb, 2),
            "mem_pct": mem_pct,
            "throughput_mbps": 0.0,
            "port": 38412,
            "latency_ms": latency_ms,
            "active_ues": ue_count if ue_count else 0,
            "last_updated": time.time(),
            "uptime_seconds": uptime,
            "started_at": time.time() - uptime,
        }
        if "log" not in self._cfg:
            self._cfg["log"] = self._guess_active_log(gtype)


# ---------------------------------------------------------------------------
# RIC adapters — real FlexRIC via SSH to 10.91.2.153 / K8s ns ric
# ---------------------------------------------------------------------------

class RicAdapter(BaseAdapter):
    """Mock RIC adapter — FlexRIC near-RT xApps + non-RT RIC (fallback)."""

    def __init__(self):
        super().__init__([
            Component("xapp-kpimon", "KPIMON", "near-RT RIC xApp", "healthy", "E2 subscription active", host="172.20.0.120"),
            Component("xapp-anomaly", "Anomaly-Detector", "near-RT RIC xApp", "healthy", "Model v0.3 loaded", host="172.20.0.121"),
            Component("xapp-healer", "Auto-Healer", "near-RT RIC xApp", "healthy", "Standing by", host="172.20.0.122"),
            Component("nonrt-ric", "non-RT RIC", "A1 policy controller", "healthy", "2 policies active",
                       host="172.20.0.123", cpu_pct=14.2, mem_gb=2.4, mem_pct=38, latency_ms=1.2),
        ])


class SshRicAdapter:
    """Adapter RIC real — FlexRIC nearRT-RIC bare-metal via SSH ke 10.91.2.153.

    Menggantikan RicAdapter(mock) ketika env RIC_SSH_HOST diisi (env: RIC_SSH_HOST,
    RIC_SSH_USER/PASSWORD/PORT). Data diambil live lewat 1 round-trip SSH:

      - ps -C nearRT-RIC -> PID/etime/pcpu/rss/args (cpu/mem/uptime)
      - ss --sctp -tln / ss --sctp -tan -> LISTEN + ESTAB (E2 connections)
      - systemctl show flexric (optional) -> uptime systemd fallback
      - ping ke RAN (10.91.2.152) -> latency_ms
      - free -m / mem total untuk mem_pct

    Kontrak sama dengan BaseAdapter: list/get/restart/jitter_health/get_logs.
    Status:
      healthy  = proses ada + SCTP 36421 LISTEN
      degraded = proses ada tapi tidak LISTEN (baru restart / bind gagal)
      down     = proses tidak ditemukan / SSH gagal
    Detail selalu jujur: "E2: N node(s) connected", PID, uptime, CPU.
    host = IP node RIC (10.91.2.153) agar Console SSH bisa dipakai.
    """

    CACHE_TTL = 2.5

    def __init__(self, ssh_host: str, ssh_user: str, ssh_password: str, ssh_port: int = 22):
        self._ssh = {"host": ssh_host, "port": int(ssh_port), "user": ssh_user, "password": ssh_password}
        self._conn = None
        self._cache: dict = {}
        self._last_fetch = 0.0

    # kontrak adapter -------------------------------------------------------
    def list(self) -> List[dict]:
        self._maybe_refresh()
        # jaga urutan: hero di frontend = cari nonrt-ric else first. Kita expose
        # 1 komponen real dengan id "ric" + alias "nonrt-ric" agar kedua key jalan.
        # list() hanya kembalikan primary "ric"; alias di-handle get() fallback.
        # Frontend memakai displayedComponents[0] sehingga hero tetap dapat nilai real.
        # Sertakan juga nonrt-ric duplicate agar hero find(\"nonrt-ric\") langsung match.
        # Untuk menghindari double-count di table, we return single primary and let
        # _with_alias handle get(). But list() with one entry is cleaner: hero
        # fallback to first entry works (verified RicPage.jsx). Keep one entry.
        return list(self._cache.values()) if self._cache else []

    def get(self, comp_id: str) -> Optional[dict]:
        self._maybe_refresh()
        if comp_id in self._cache:
            return self._cache[comp_id]
        # alias: frontend hero cari \"nonrt-ric\", dashboard restart may use \"ric\"
        # legacy ids xapp-* return down placeholder biar tidak 404 saat UI masih cache lama
        if comp_id in ("nonrt-ric", "flexric", "nearrt-ric", "ric"):
            vals = list(self._cache.values())
            return vals[0] if vals else None
        if comp_id.startswith("xapp-"):
            # xApp belum di-deploy bare-metal; tampilkan down jujur
            return {
                "id": comp_id, "name": comp_id, "kind": "near-RT RIC xApp",
                "status": "down", "detail": "xApp not deployed on bare-metal testbed (only nearRT-RIC running)",
                "host": self._ssh["host"], "cpu_pct": 0.0, "mem_gb": 0.0, "mem_pct": 0.0,
                "throughput_mbps": 0.0, "port": 36422, "latency_ms": 0.0, "active_ues": 0,
                "last_updated": time.time(), "uptime_seconds": 0, "started_at": time.time(),
            }
        return None

    async def restart(self, comp_id: str) -> Optional[dict]:
        if comp_id not in ("ric", "nonrt-ric", "flexric", "nearrt-ric"):
            # izinkan restart xapp mock tetap fake success supaya UI tidak error
            if comp_id.startswith("xapp-"):
                await asyncio.sleep(1)
                return self.get(comp_id)
            return None
        try:
            # coba systemd dulu (jika service enabled), fallback kill+start manual
            out, err = self._exec("systemctl is-active flexric 2>&1; echo __S1__; sudo systemctl restart flexric 2>&1 || systemctl restart flexric 2>&1; echo __RC__$?; sleep 2; ps -C nearRT-RIC --no-headers -o pid= 2>/dev/null | head -1")
        except Exception as e:
            err = str(e)
        self._last_fetch = 0
        await asyncio.sleep(1.5)
        result = self.get(comp_id if comp_id in self._cache else "ric")
        if result:
            result = dict(result)
            # kalau restart gagal total, tandai di detail
            if result.get("status") == "down":
                result["detail"] = "Restart attempted but RIC still down — check SSH/systemctl"
            else:
                result["status"] = "restarting"
                result["detail"] = "Restart requested via SSH (systemctl restart flexric)"
            result["last_updated"] = time.time()
        return result

    def jitter_health(self):
        pass

    def get_logs(self, comp_id: str, tail: int = 100) -> str:
        if comp_id not in ("ric", "nonrt-ric", "flexric", "nearrt-ric") and not comp_id.startswith("xapp-"):
            return f"Component '{comp_id}' not found."
        # xApp down placeholder
        if comp_id.startswith("xapp-"):
            return f"[RIC] xApp '{comp_id}' not deployed — no logs (only nearRT-RIC running on {self._ssh['host']})"
        try:
            # cek beberapa lokasi log umum
            out, _ = self._exec(
                "tail -n {t} ~/ric-script.log 2>/dev/null || tail -n {t} /var/log/flexric.log 2>/dev/null || journalctl -u flexric --no-pager -n {t} 2>/dev/null || echo '(tidak ada log)'".format(t=int(tail))
            )
            return (out or "").strip() or "(tidak ada log)"
        except Exception as e:
            return f"[SSH Error] Gagal ambil log RIC: {e}"

    # helpers ---------------------------------------------------------------
    def _maybe_refresh(self):
        now = time.time()
        if now - self._last_fetch < self.CACHE_TTL:
            return
        self._last_fetch = now
        try:
            out, _ = self._exec(
                "m=$(ps -C nearRT-RIC --no-headers -o pid=,etime=,pcpu=,rss=,args= 2>/dev/null | head -1); "
                "[ -n \"$m\" ] && echo \"PROC|ric|$m\"; "
                "echo \"MEMTOT|$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')\"; "
                "echo \"SCTP_LISTEN|$(ss -an 2>/dev/null | grep ':36421' | grep -c LISTEN)\"; "
                "echo \"SCTP_ESTAB|$(ss -an 2>/dev/null | grep ':36421' | grep -c ESTAB)\"; "
                "echo \"SCTP_PEERS|$(ss -an 2>/dev/null | grep ':36421' | grep ESTAB | head -5 | tr '\\n' ';')\"; "
                "echo \"UPTIME_SYS|$(systemctl show flexric --property=ActiveEnterTimestamp 2>/dev/null | head -1)\"; "
                "echo \"PING|$(ping -c 1 -W 1 10.91.2.152 2>/dev/null | grep -oE 'time=[0-9.]+' | head -1)\""
            )
        except Exception as e:
            print(f"[SshRicAdapter] SSH ke {self._ssh['host']} gagal: {e}", flush=True)
            self._cache = {"ric": self._down(f"SSH ke node RIC gagal: {e}")}
            return

        proc = None
        mem_total_m = 0
        sctp_listen = 0
        sctp_estab = 0
        sctp_peers = ""
        uptime_sys = ""
        ping_raw = ""
        for ln in out.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            if ln.startswith("PROC|"):
                parts = ln.split("|", 2)
                if len(parts) >= 3:
                    rest = parts[2].split(None, 4)
                    if len(rest) >= 4:
                        proc = {"pid": rest[0], "etime": rest[1], "pcpu": self._to_float(rest[2]), "rss_kb": self._to_float(rest[3]), "args": rest[4] if len(rest) > 4 else ""}
            elif ln.startswith("MEMTOT|"):
                try:
                    mem_total_m = int(ln.split("|", 1)[1] or 0)
                except Exception:
                    mem_total_m = 0
            elif ln.startswith("SCTP_LISTEN|"):
                try:
                    sctp_listen = int(ln.split("|", 1)[1] or 0)
                except Exception:
                    sctp_listen = 0
            elif ln.startswith("SCTP_ESTAB|"):
                try:
                    sctp_estab = int(ln.split("|", 1)[1] or 0)
                except Exception:
                    sctp_estab = 0
            elif ln.startswith("SCTP_PEERS|"):
                sctp_peers = ln.split("|", 1)[1] if "|" in ln else ""
            elif ln.startswith("UPTIME_SYS|"):
                uptime_sys = ln.split("|", 1)[1] if "|" in ln else ""
            elif ln.startswith("PING|"):
                ping_raw = ln.split("|", 1)[1] if "|" in ln else ""

        if not proc:
            self._cache = {"ric": self._down("FlexRIC nearRT-RIC tidak jalan (proses 'nearRT-RIC' tidak ditemukan) — coba systemctl start flexric")}
            return

        # uptime: prefer systemd ActiveEnterTimestamp else ps etime
        uptime = self._parse_systemd_uptime(uptime_sys) or self._parse_etime(proc["etime"])
        mem_gb = proc["rss_kb"] / (1024 * 1024)
        mem_total_gb = (mem_total_m / 1024) if mem_total_m else 29.8
        mem_pct = round(min(100.0, mem_gb / mem_total_gb * 100), 2) if mem_total_gb else 0.0
        # latency from ping time=XX
        latency_ms = 0.0
        if ping_raw and "time=" in ping_raw:
            try:
                import re as _re
                _m = _re.search(r"time=([0-9.]+)", ping_raw)
                if _m:
                    latency_ms = round(float(_m.group(1)), 2)
            except Exception:
                pass

        # status logic
        if proc and sctp_listen > 0:
            # jika ada ESTAB, healthy; tanpa ESTAB tapi LISTEN tetap healthy (RIC standby)
            status = "healthy" if sctp_estab > 0 else "healthy"
            # jika ESTAB 0 tapi LISTEN ada, tetap healthy tapi detail sebut waiting
        elif proc and sctp_listen == 0:
            status = "degraded"
        else:
            status = "down"

        # detail: host/cpu/mem/latency/status/E2 count/uptime
        peers_short = sctp_peers.strip().strip(";")
        if peers_short:
            import re as _re2
            ips = _re2.findall(r"\d+\.\d+\.\d+\.\d+:\d+", peers_short)
            peers_short = ", ".join(ips[:3]) if ips else peers_short.replace(";", ", ")[:120]
            if not peers_short:
                peers_short = "-"
        else:
            peers_short = "-"
        detail = (
            f"FlexRIC nearRT-RIC | PID {proc['pid']} | E2: {sctp_estab} node(s) connected"
            + (f" ({peers_short})" if sctp_estab and peers_short != "-" else "")
            + f" | SCTP :36421 {'LISTEN' if sctp_listen else 'not listening'}"
            + f" | uptime {self._fmt_uptime(uptime)} | CPU {proc['pcpu']}% MEM {round(mem_gb,2)}GB"
        )

        comp = {
            "id": "ric",
            "name": "FlexRIC RIC",
            "kind": "near-RT RIC",
            "status": status,
            "detail": detail,
            "host": self._ssh["host"],
            "cpu_pct": round(proc["pcpu"], 2),
            "mem_gb": round(mem_gb, 2),
            "mem_pct": mem_pct,
            "throughput_mbps": 0.0,
            "port": 36421,
            "latency_ms": latency_ms,
            "active_ues": sctp_estab,  # reuse field to surface E2 count di UI kalau mau
            "last_updated": time.time(),
            "uptime_seconds": uptime,
            "started_at": time.time() - uptime,
        }
        # keep both keys for frontend hero compatibility: primary \"ric\" and alias \"nonrt-ric\"
        self._cache = {"ric": comp, "nonrt-ric": dict(comp, id="nonrt-ric", name="FlexRIC RIC")}
        # also keep single canonical in list via _cache filtered in list() — but now cache has 2
        # list() will return both; frontend table akan show 2 rows identical — lebih jelas
        # hide duplicate: list() should return 1. So keep internal 2 untuk get alias, tapi
        # list() override di atas untuk filter. Simpler: simpan 1 saja dan alias di get().
        # Reset ke single entry internal, alias handled in get() fallback:
        self._cache = {"ric": comp}

    def _down(self, reason) -> dict:
        return {
            "id": "ric", "name": "FlexRIC RIC", "kind": "near-RT RIC", "status": "down",
            "detail": reason, "host": self._ssh["host"],
            "cpu_pct": 0.0, "mem_gb": 0.0, "mem_pct": 0.0,
            "throughput_mbps": 0.0, "port": 36421, "latency_ms": 0.0, "active_ues": 0,
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

    @staticmethod
    def _parse_systemd_uptime(line: str) -> int:
        if not line or "ActiveEnterTimestamp=" not in line or "n/a" in line.lower():
            return 0
        try:
            import re as _re
            from datetime import datetime, timezone
            ts_str = line.split("=", 1)[1].strip()
            # e.g. "Thu 2026-08-28 13:20:00 WIB" -> try parse
            for fmt in ("%a %Y-%m-%d %H:%M:%S %Z", "%a %Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %Z"):
                try:
                    dt = datetime.strptime(ts_str, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    import time as _time
                    return int(_time.time() - dt.timestamp())
                except Exception:
                    continue
        except Exception:
            pass
        return 0

    @staticmethod
    def _fmt_uptime(secs: int) -> str:
        try:
            d, r = divmod(int(secs), 86400)
            h, r = divmod(r, 3600)
            m, s = divmod(r, 60)
            if d:
                return f"{d}d{h}h{m}m"
            if h:
                return f"{h}h{m}m{s}s"
            if m:
                return f"{m}m{s}s"
            return f"{s}s"
        except Exception:
            return f"{secs}s"


class KubectlRicAdapter:
    """Adapter RIC via Kubernetes ns ric (Fase hostNetwork).

    Membaca state FlexRIC K8s pod di namespace ric via kubectl over SSH ke master
    (default 10.91.2.156, OAI_K8S_SSH_HOST) melalui /etc/kubernetes/admin.conf (sudo -n).
    Live metrics via:
      1. get pods -o wide        -> phase/ready/restarts/podIP/node (host=podIP)
      2. get pods custom-columns -> status.startTime (sumber uptime)
      3. top pods                -> CPU/mem real (butuh metrics-server)
      4. get svc                 -> endpoint svc (jika ada)
      5. ping                    -> latency_ms ke RAN (10.91.2.152)

    Map: component ric -> prefix flexric-nearrt-ric, label app=flexric-nearrt-ric
    (fallback app=flexric atau k8s-app=flexric untuk kompatibilitas). Port E2 36421/SCTP,
    detail: Pod <name> (<phase>, <ready>) • node <node> • podIP <ip> • E2 36421/SCTP hostNetwork • latency Xms.
    READ-ONLY — restart() hanya simulasi UI, tidak menyentuh cluster.
    """

    CACHE_TTL = 2.5

    def __init__(self, ssh_host: str, ssh_user: str, ssh_password: str = "", sudo_password: str = "",
                 ssh_port: int = 22, namespace: str = "ric",
                 kubeconfig: str = "/etc/kubernetes/admin.conf", kubectl_bin: str = "kubectl"):
        self._map = {"ric": "flexric-nearrt-ric"}
        self._ssh = {"host": ssh_host, "port": int(ssh_port), "user": ssh_user, "password": ssh_password, "sudo": sudo_password or ssh_password}
        self._ns = namespace
        self._kubeconfig = kubeconfig
        self._kubectl = kubectl_bin
        self._conn = None
        self._cache: dict = {}
        self._last_fetch = 0.0

    def list(self) -> List[dict]:
        self._maybe_refresh()
        return [self._cache[c] for c in self._map if c in self._cache]

    def get(self, comp_id: str) -> Optional[dict]:
        if comp_id not in self._map and comp_id not in ("nonrt-ric", "flexric", "nearrt-ric"):
            if comp_id.startswith("xapp-"):
                return {"id": comp_id, "name": comp_id, "kind": "near-RT RIC xApp", "status": "down", "detail": "xApp not in K8s ns ric (only nearRT-RIC deployed)", "host": self._ssh["host"], "cpu_pct": 0.0, "mem_gb": 0.0, "mem_pct": 0.0, "throughput_mbps": 0.0, "port": 36422, "latency_ms": 0.0, "active_ues": 0, "last_updated": time.time(), "uptime_seconds": 0, "started_at": time.time()}
            return None
        self._maybe_refresh()
        key = comp_id if comp_id in self._cache else "ric"
        return self._cache.get(key)

    async def restart(self, comp_id: str) -> Optional[dict]:
        await asyncio.sleep(1.5)
        self._maybe_refresh()
        result = dict(self._cache.get("ric") or {})
        if result and result.get("status") == "healthy":
            result["status"] = "restarting"
            result["detail"] = "Restart request noted (read-only K8s mode; no rollout executed)"
            result["last_updated"] = time.time()
        return result

    def jitter_health(self):
        pass

    def get_logs(self, comp_id: str, tail: int = 100) -> str:
        if comp_id not in self._map and comp_id not in ("nonrt-ric", "flexric", "nearrt-ric"):
            if comp_id.startswith("xapp-"):
                return f"[RIC] xApp '{comp_id}' not in K8s ns {self._ns} (only nearRT-RIC deployed)"
            return f"Component '{comp_id}' not mapped."
        try:
            # label fallback: app=flexric-nearrt-ric primary, then app=flexric, then k8s-app=flexric
            out, err = self._exec(f"{self._kctl()} -n {self._ns} logs --tail={int(tail)} --timestamps -l app=flexric-nearrt-ric 2>&1")
            if out.strip():
                return out.strip()
            out2, err2 = self._exec(f"{self._kctl()} -n {self._ns} logs --tail={int(tail)} --timestamps -l app=flexric 2>&1")
            if out2.strip():
                return out2.strip()
            out3, err3 = self._exec(f"{self._kctl()} -n {self._ns} logs --tail={int(tail)} --timestamps -l k8s-app=flexric 2>&1")
            return (out3 or "").strip() or (err3.strip() or err2.strip() or err.strip() or "(tidak ada log)")
        except Exception as e:
            return f"[SSH Error] Gagal ambil log RIC via kubectl: {e}"

    def _kctl(self) -> str:
        return f"sudo -n {self._kubectl} --kubeconfig={self._kubeconfig}"

    def _exec(self, cmd: str):
        import paramiko
        conn = self._conn
        if conn is None or not conn.get_transport() or not conn.get_transport().is_active():
            conn = paramiko.SSHClient()
            conn.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            conn.connect(hostname=self._ssh["host"], port=self._ssh["port"], username=self._ssh["user"], password=self._ssh["password"], timeout=8, banner_timeout=10)
            self._conn = conn
        _, stdout, stderr = conn.exec_command(cmd, timeout=25)
        return stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace")

    def _maybe_refresh(self):
        now = time.time()
        if now - self._last_fetch < self.CACHE_TTL:
            return
        self._last_fetch = now
        kc = self._kctl()
        try:
            # Use sudo -n (passwordless) as configured on master; avoid sudo -S pipe
            out, err = self._exec(
                f"{kc} -n {self._ns} get pods -o wide --no-headers 2>&1; echo '===STARTED==='; "
                f"{kc} -n {self._ns} get pods -o custom-columns=':metadata.name,:status.startTime' --no-headers 2>&1; echo '===METRICS==='; "
                f"{kc} -n {self._ns} top pods --no-headers 2>&1; echo '===SVC==='; "
                f"{kc} -n {self._ns} get svc -o custom-columns=':metadata.name,:spec.clusterIP' --no-headers 2>&1; echo '===PING==='; "
                f"ping -c 1 -W 1 10.91.2.152 2>/dev/null | grep -oE 'time=[0-9.]+' | head -1 || echo 'PING_NONE'"
            )
        except Exception as e:
            print(f"[KubectlRicAdapter] SSH ke {self._ssh['host']} gagal: {e}", flush=True)
            for k in self._map:
                self._cache[k] = self._down_component(k, f"SSH ke node K8s gagal: {e}")
            return
        if "===STARTED===" not in out:
            reason = (err or out or "kubectl tidak mengembalikan data").strip()
            for k in self._map:
                self._cache[k] = self._down_component(k, f"kubectl gagal: {reason[:160]}")
            return
        pods, started, metrics, svcs = {}, {}, {}, {}
        ping_ms = 0.0
        section = "pods"
        for raw in out.splitlines():
            line = raw.strip()
            if line == "===STARTED===": section = "started"; continue
            if line == "===METRICS===": section = "metrics"; continue
            if line == "===SVC===": section = "svc"; continue
            if line == "===PING===": section = "ping"; continue
            if not line: continue
            if section == "pods":
                import re
                toks = line.split()
                if len(toks) >= 6:
                    name = toks[0]
                    ready = toks[1] if len(toks) > 1 else ""
                    phase = toks[2] if len(toks) > 2 else ""
                    restarts = toks[3] if len(toks) > 3 else "0"
                    pod_ip = ""
                    node = ""
                    for idx, tok in enumerate(toks):
                        if re.match(r'^\d+\.\d+\.\d+\.\d+$', tok) and tok != "<none>":
                            pod_ip = tok
                            if idx + 1 < len(toks): node = toks[idx+1]
                            break
                        if tok == "<none>":
                            pod_ip = "<none>"
                    pods[name] = {"ready": ready, "phase": phase, "restarts": restarts, "pod_ip": pod_ip, "node": node}
            elif section == "started":
                p = line.split()
                if len(p) >= 2: started[p[0]] = "" if p[1] == "<none>" else p[1]
            elif section == "metrics":
                p = line.split()
                # metrics-server: 3 cols (NAME CPU MEM) or 5 cols (NAME CPU_CPU% MEM_MEM%)
                if len(p) >= 3:
                    # detect format: if len>=5 assume 5-col, else 3-col with CPU=milli/MEM=Mi
                    if len(p) >= 5:
                        metrics[p[0]] = {"cpu_pct": self._cpu_to_pct(p[1]), "mem_mi": self._to_float_mi(p[3])}
                    else:
                        metrics[p[0]] = {"cpu_pct": self._cpu_to_pct(p[1]), "mem_mi": self._to_float_mi(p[2])}
            elif section == "svc":
                p = line.split()
                if len(p) >= 2:
                    svcs[p[0]] = p[1]
            elif section == "ping":
                import re
                m = re.search(r'time=([0-9.]+)', line)
                if m:
                    try: ping_ms = round(float(m.group(1)), 2)
                    except: pass
        for comp_id, prefix in self._map.items():
            entry = None
            for pod_name, info in pods.items():
                if pod_name == prefix or pod_name.startswith(prefix + "-"):
                    entry = (pod_name, info); break
            if entry is None:
                self._cache[comp_id] = self._down_component(comp_id, f"Pod tidak ditemukan di ns {self._ns}: {prefix}*")
                continue
            pod_name, info = entry
            phase = info["phase"]
            status = self._map_k8s_status(phase, info["restarts"])
            start_iso = started.get(pod_name, "")
            started_at = self._parse_start_time(start_iso)
            met = metrics.get(pod_name, {})
            detail_bits = [f"Pod {pod_name} ({phase}, {info['ready']})"]
            if info["node"]: detail_bits.append(f"node {info['node']}")
            if info["pod_ip"] and info["pod_ip"] != "<none>": detail_bits.append(f"podIP {info['pod_ip']}")
            # E2 SCTP port explicit per task requirement
            detail_bits.append("E2 36421/SCTP hostNetwork" if info.get("pod_ip") == "10.91.2.153" else "E2 36421/SCTP")
            # also include service if exists
            if svcs:
                detail_bits.append(f"svc {','.join([f'{k}:{v}' for k,v in svcs.items()])}")
            # uptime human readable in detail
            uptime = (time.time() - started_at) if started_at else 0
            detail_bits.append(f"uptime {self._fmt_uptime(int(uptime))}" if uptime else "uptime -")
            if ping_ms:
                detail_bits.append(f"latency {ping_ms}ms")
            host_val = info["pod_ip"] if info["pod_ip"] and info["pod_ip"] != "<none>" else None
            self._cache[comp_id] = {
                "id": comp_id, "name": "FlexRIC RIC", "kind": "near-RT RIC", "status": status,
                "detail": " • ".join(detail_bits), "host": host_val,
                "cpu_pct": met.get("cpu_pct", 0.0), "mem_gb": round(met.get("mem_mi", 0.0) / 1024.0, 2), "mem_pct": 0.0,
                "throughput_mbps": 0.0, "port": 36421, "latency_ms": ping_ms, "active_ues": 0,
                "last_updated": time.time(), "uptime_seconds": uptime, "started_at": started_at or time.time(),
            }

    @staticmethod
    def _map_k8s_status(phase: str, restarts: str = "0") -> Status:
        s = (phase or "").lower()
        if "running" in s:
            try:
                if int(str(restarts).split("(")[0]) >= 10: return "degraded"
            except Exception: pass
            return "healthy"
        if "pending" in s or "containercreating" in s or "init:" in s: return "degraded"
        if "crashloopbackoff" in s or "error" in s or "evicted" in s: return "down"
        if "terminated" in s or "completed" in s: return "degraded"
        return "degraded"

    @staticmethod
    def _parse_start_time(iso_str: str) -> Optional[float]:
        if not iso_str: return None
        try:
            from datetime import datetime, timezone
            s = iso_str.strip().rstrip("Z")
            if "." in s: s = s.split(".")[0]
            dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception: return None

    @staticmethod
    def _cpu_to_pct(cpu_cores: str) -> float:
        try:
            c = cpu_cores.strip().lower()
            if c.endswith("n"): return round(float(c[:-1]) / 1e7, 1)
            if c.endswith("m"): return round(float(c[:-1]) / 10.0, 1)
            return round(float(c), 1)
        except Exception: return 0.0

    @staticmethod
    def _to_float_mi(mem_val: str) -> float:
        try:
            v = mem_val.strip().lower()
            if v.endswith("mi"): return float(v[:-2])
            if v.endswith("gi"): return float(v[:-2]) * 1024
            if v.endswith("ki"): return float(v[:-2]) / 1024
            return float(v)
        except Exception: return 0.0

    @staticmethod
    def _fmt_uptime(secs: int) -> str:
        try:
            d, r = divmod(int(secs), 86400)
            h, r = divmod(r, 3600)
            m, s = divmod(r, 60)
            if d: return f"{d}d{h}h{m}m"
            if h: return f"{h}h{m}m{s}s"
            if m: return f"{m}m{s}s"
            return f"{s}s"
        except Exception: return f"{secs}s"

    def _down_component(self, comp_id: str, reason: str) -> dict:
        return {"id": comp_id, "name": "FlexRIC RIC", "kind": "near-RT RIC", "status": "down", "detail": reason, "host": None, "cpu_pct": 0.0, "mem_gb": 0.0, "mem_pct": 0.0, "throughput_mbps": 0.0, "port": 36421, "latency_ms": 0.0, "active_ues": 0, "last_updated": time.time(), "uptime_seconds": 0, "started_at": time.time()}


# ---------------------------------------------------------------------------
# Magma Core adapter (skeleton — belum diimplementasi)
# ---------------------------------------------------------------------------

# Pemetaan default Deployment OAI 5GC di K8s (ns 5g-core) utk provider "k8s".
DEFAULT_K8S_CORE_MAP_K8S = {
    "amf":   {"deploy": "oai-amf",  "kind": "AMF"},
    "smf":   {"deploy": "oai-smf",  "kind": "SMF"},
    "upf":   {"deploy": "oai-upf",  "kind": "UPF"},
    "nrf":   {"deploy": "oai-nrf",  "kind": "NRF"},
    "ausf":  {"deploy": "oai-ausf", "kind": "AUSF"},
    "udm":   {"deploy": "oai-udm",  "kind": "UDM"},
    "udr":   {"deploy": "oai-udr",  "kind": "UDR"},
    "mysql": {"deploy": "mysql",    "kind": "MySQL"},
}


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
    adapter = None
    oai_desc = None

    # --- OAI Core via Kubernetes (Fase 1: read-only visibility) ---
    # 5GC aktif jalan di K8s (ns 5g-core). Adapter membaca state cluster via
    # kubectl over SSH ke node master yang memegang /etc/kubernetes/admin.conf.
    # Env lama OAI_SSH_* masih didukung sebagai jalur Docker-legacy untuk
    # setup non-K8s, tapi testbed ini TIDAK memakainya lagi (docker di node
    # core hanya berisi Open5GS demo lama — bukan 5GC aktif).
    oai_k8s_host = os.environ.get("OAI_K8S_SSH_HOST", "") or None
    if oai_k8s_host:
        try:
            k8s_map = dict(DEFAULT_OAI_K8S_COMPONENT_MAP)
            custom = os.environ.get("OAI_K8S_COMPONENT_MAP", "")
            if custom:
                try:
                    k8s_map.update(json.loads(custom))
                except Exception:
                    pass  # JSON rusak -> pakai pemetaan default
            adapter = KubectlOaiCoreAdapter(
                k8s_map,
                ssh_host=oai_k8s_host,
                ssh_user=os.environ.get("OAI_K8S_SSH_USER", "telmat"),
                ssh_password=os.environ.get("OAI_K8S_SSH_PASSWORD", ""),
                sudo_password=os.environ.get("K8S_SUDO_PASSWORD", ""),
                ssh_port=int(os.environ.get("OAI_K8S_SSH_PORT", "22")),
                namespace=os.environ.get("OAI_K8S_NAMESPACE", "5g-core"),
                kubeconfig=os.environ.get(
                    "OAI_K8S_ADMIN_CONF", "/etc/kubernetes/admin.conf"),
            )
            oai_desc = "OpenAirInterface 5G Core"
        except Exception:
            adapter = CoreAdapter()
            oai_desc = "OpenAirInterface 5G Core (fallback mock — env K8s invalid)"
    else:
        oai_desc = None  # jatuh ke blok Docker-legacy di bawah

    # --- Jalur Docker-legacy (hanya dipakai kalau OAI_K8S_SSH_HOST kosong) ---
    if oai_desc is None:
        oai_containers_raw = os.environ.get("OAI_CORE_CONTAINERS", "")
        oai_ssh_host = os.environ.get("OAI_SSH_HOST", "") or None
        oai_docker_host = os.environ.get("OAI_DOCKER_HOST", "") or None

        # Pemetaan default sesuai container compose OAI versi lama (non-K8s)
        DEFAULT_OAI_CONTAINER_MAP = {
            "amf": "oai-amf", "smf": "oai-smf", "upf": "oai-upf", "nrf": "oai-nrf",
            "ausf": "oai-ausf", "udm": "oai-udm", "udr": "oai-udr",
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
            # Mode SSH: perintah docker dijalankan remote via paramiko.
            # LEGACY: hanya untuk testbed Docker lama (Open5GS demo di
            # demo-oai-public-net) — BUKAN 5GC K8s yang sekarang aktif.
            adapter = SshDockerCoreAdapter(
                container_map,
                ssh_host=oai_ssh_host,
                ssh_user=os.environ.get("OAI_SSH_USER", "core"),
                ssh_password=os.environ.get("OAI_SSH_PASSWORD", ""),
                ssh_port=int(os.environ.get("OAI_SSH_PORT", "22")),
            )
            oai_desc = "OpenAirInterface 5G Core (Docker legacy via SSH)"
        elif container_map:
            try:
                adapter = DockerCoreAdapter(container_map, docker_host=oai_docker_host)
            except Exception:
                # Docker tidak reachable atau env tidak valid → fallback ke mock
                adapter = CoreAdapter()
                oai_desc = "OpenAirInterface 5G Core (mock fallback)"
            else:
                oai_desc = "OpenAirInterface 5G Core (Docker Engine API)"
        else:
            adapter = CoreAdapter()  # fallback mock
            oai_desc = "OpenAirInterface 5G Core (mock)"

    providers["oai"] = {
        "label": "OAI 5GC",
        "icon": "cloud_done",
        "desc": oai_desc,
        "adapter": adapter,
    }

    # --- open5gs via Kubernetes (live) else Docker else mock ---
    open5gs_k8s_host = os.environ.get("OPEN5GS_K8S_SSH_HOST", "") or os.environ.get("OAI_K8S_SSH_HOST", "") or None
    # If no dedicated open5gs host, fallback to OAI host (same master 10.91.2.156 holds both namespaces)
    if not open5gs_k8s_host:
        # also check legacy OAI_K8S_SSH_HOST already captured above, but fallback explicit
        open5gs_k8s_host = os.environ.get("OAI_K8S_SSH_HOST", "") or None
    adapter_5gs = None
    open5gs_desc = None
    if open5gs_k8s_host:
        try:
            k8s_map_5gs = dict(DEFAULT_OPEN5GS_K8S_COMPONENT_MAP)
            custom_5gs = os.environ.get("OPEN5GS_K8S_COMPONENT_MAP", "")
            if custom_5gs:
                try:
                    k8s_map_5gs.update(json.loads(custom_5gs))
                except Exception:
                    pass
            open5gs_ns = os.environ.get("OPEN5GS_K8S_NAMESPACE", "") or os.environ.get("OPEN5GS_NAMESPACE", "") or "open5gs-chart"
            # sanitize: if env contains open5gs value like "open5gs" use it, else default chart
            open5gs_user = os.environ.get("OPEN5GS_K8S_SSH_USER", "") or os.environ.get("OAI_K8S_SSH_USER", "telmat") or "telmat"
            open5gs_port = int(os.environ.get("OPEN5GS_K8S_SSH_PORT", "") or os.environ.get("OAI_K8S_SSH_PORT", "22") or "22")
            open5gs_pw = os.environ.get("OPEN5GS_K8S_SSH_PASSWORD", "") or os.environ.get("OAI_K8S_SSH_PASSWORD", "") or ""
            open5gs_sudo = os.environ.get("OPEN5GS_K8S_SUDO_PASSWORD", "") or os.environ.get("K8S_SUDO_PASSWORD", "") or open5gs_pw or ""
            open5gs_kubeconf = os.environ.get("OPEN5GS_K8S_ADMIN_CONF", "") or os.environ.get("OAI_K8S_ADMIN_CONF", "/etc/kubernetes/admin.conf") or "/etc/kubernetes/admin.conf"
            adapter_5gs = KubectlOpen5gsCoreAdapter(
                k8s_map_5gs,
                ssh_host=open5gs_k8s_host,
                ssh_user=open5gs_user,
                ssh_password=open5gs_pw,
                sudo_password=open5gs_sudo,
                ssh_port=open5gs_port,
                namespace=open5gs_ns,
                kubeconfig=open5gs_kubeconf,
            )
            open5gs_desc = "open5gs 5G Core"
        except Exception as e:
            print(f"[open5gs K8s] fallback mock due to {e}", flush=True)
            adapter_5gs = CoreAdapter()
            open5gs_desc = "open5gs 5G Core (fallback mock — env K8s invalid)"
    if adapter_5gs is None:
        open5gs_raw = os.environ.get("OPEN5GS_CORE_CONTAINERS", "")
        open5gs_docker_host = os.environ.get("OPEN5GS_DOCKER_HOST", "") or None
        if open5gs_raw:
            try:
                container_map = json.loads(open5gs_raw)
                adapter_5gs = DockerCoreAdapter(container_map, docker_host=open5gs_docker_host)
                open5gs_desc = "open5gs 5G Core (Docker Engine API)"
            except Exception:
                adapter_5gs = CoreAdapter()
                open5gs_desc = "open5gs 5G Core (mock fallback)"
        else:
            adapter_5gs = CoreAdapter()
            open5gs_desc = "open5gs 5G Core (mock)"
    providers["open5gs"] = {
        "label": "open5gs",
        "icon": "dns",
        "desc": open5gs_desc,
        "adapter": adapter_5gs,
    }

    # --- K8s 5GC & Magma: hidden (2026-08-27) ---
    # Provider "k8s" (OAI K8s) dan "magma" sengaja TIDAK diregistrasi
    # agar tab Core hanya menampilkan oai/open5gs (permintaan Ardeezy via Bill).
    # Kode adapter tetap ada (SshK8sCoreAdapter/MagmaCoreAdapter) untuk dipakai
    # lagi kapan pun — cukup uncomment blok di bawah dan aktifkan kembali.
    # --- K8s 5GC (read-only fase 1, via SSH kubectl ke master) - DISABLED ---
    # from k8s_adapter import SshK8sCoreAdapter
    # k8s_ssh_host = os.environ.get("K8S_SSH_HOST", "") or None
    # ... (hidden)
    # providers["k8s"] = {...}
    # --- Magma (Orc8R) - DISABLED ---
    # magma_url = os.environ.get("MAGMA_ORC8R_URL", "")
    # magma_adapter = MagmaCoreAdapter(...)
    # providers["magma"] = {...}

    return providers


def _build_ran_providers() -> dict:
    """RAN providers — aktif real via SSH kalau host di-set, fallback mock.

    Dua provider:
      - oai    : OAI nr-softmodem (OAI_SSH_RAN_HOST)
      - srsran : srsRAN gNB (SRSRAN_SSH_HOST — env var terpisah)
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
            binary_hints=["nr-softmodem"],
        )
        desc = "OAI nr-softmodem gNB (real via SSH)"
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


def _build_ric_providers() -> dict:
    """RIC providers — real via SSH bare-metal atau K8s ns ric, fallback mock.

    Prioritas:
      1) Jika RIC_K8S_SSH_HOST terisi -> KubectlRicAdapter (ns ric via 10.91.2.156)
      2) Elif RIC_SSH_HOST terisi -> SshRicAdapter bare-metal (10.91.2.153)
      3) fallback -> RicAdapter mock
    Env tambahan: RIC_K8S_NAMESPACE (default ric), RIC_K8S_SUDO_PASSWORD, dsb.
    """
    providers = {}
    # K8s ns ric via kubectl over SSH (hostNetwork deployment flexric-nearrt-ric)
    # Fallback: RIC_K8S_SSH_HOST else OAI_K8S_SSH_HOST (both default 10.91.2.156 -> same master)
    ric_k8s_host = os.environ.get("RIC_K8S_SSH_HOST", "") or os.environ.get("OAI_K8S_SSH_HOST", "") or None
    # also respect nested env from helm extraEnv: allow RIC_K8S_SSH_HOST set via values ric.k8s
    # namespace/kubeconfig via env fallback as specified in task: ric, /etc/kubernetes/admin.conf
    if ric_k8s_host:
        try:
            ric_ns = os.environ.get("RIC_K8S_NAMESPACE", "ric") or "ric"
            ric_kubeconf = os.environ.get("RIC_K8S_ADMIN_CONF", "/etc/kubernetes/admin.conf") or "/etc/kubernetes/admin.conf"
            # fallback chain: RIC_K8S_* -> OAI_K8S_* -> defaults (task: namespace ric, kubeconfig /etc/kubernetes/admin.conf)
            ric_user = os.environ.get("RIC_K8S_SSH_USER", "") or os.environ.get("OAI_K8S_SSH_USER", "telmat") or "telmat"
            ric_pw = os.environ.get("RIC_K8S_SSH_PASSWORD", "") or os.environ.get("OAI_K8S_SSH_PASSWORD", "") or ""
            ric_sudo = os.environ.get("RIC_K8S_SUDO_PASSWORD", "") or os.environ.get("K8S_SUDO_PASSWORD", "") or ric_pw or ""
            ric_port = int(os.environ.get("RIC_K8S_SSH_PORT", "") or os.environ.get("OAI_K8S_SSH_PORT", "22") or "22")
            adapter = KubectlRicAdapter(
                ssh_host=ric_k8s_host,
                ssh_user=ric_user,
                ssh_password=ric_pw,
                sudo_password=ric_sudo,
                ssh_port=ric_port,
                namespace=ric_ns,
                kubeconfig=ric_kubeconf,
            )
            desc = "FlexRIC nearRT-RIC"
        except Exception as e:
            print(f"[RIC K8s] fallback mock due to {e}", flush=True)
            adapter = RicAdapter()
            desc = "FlexRIC near-RT RIC (fallback mock — env K8s invalid)"
        providers["oai"] = {"label": "FlexRIC", "icon": "memory", "desc": desc, "adapter": adapter}
        return providers

    ssh_host = os.environ.get("RIC_SSH_HOST", "") or None
    if ssh_host:
        adapter = SshRicAdapter(
            ssh_host=ssh_host,
            ssh_user=os.environ.get("RIC_SSH_USER", "telmat"),
            ssh_password=os.environ.get("RIC_SSH_PASSWORD", ""),
            ssh_port=int(os.environ.get("RIC_SSH_PORT", "22")),
        )
        desc = f"FlexRIC nearRT-RIC — live bare-metal via SSH@{ssh_host} (SCTP :36421)"
    else:
        adapter = RicAdapter()
        desc = "FlexRIC near-RT RIC & xApps (mock)"
    providers["oai"] = {"label": "FlexRIC", "icon": "memory", "desc": desc, "adapter": adapter}
    return providers


DOMAIN_PROVIDERS = {
    "core": _build_core_providers(),
    "ran": _build_ran_providers(),
    "ric": _build_ric_providers(),
}
