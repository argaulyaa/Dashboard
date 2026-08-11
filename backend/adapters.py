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

    # --- OAI Core via Docker ---
    oai_containers_raw = os.environ.get("OAI_CORE_CONTAINERS", "")
    oai_docker_host = os.environ.get("OAI_DOCKER_HOST", "") or None
    if oai_containers_raw:
        try:
            container_map = json.loads(oai_containers_raw)
            adapter = DockerCoreAdapter(container_map, docker_host=oai_docker_host)
        except Exception:
            # Docker tidak reachable atau env tidak valid → fallback ke mock
            adapter = CoreAdapter()
    else:
        adapter = CoreAdapter()  # fallback mock
    providers["oai"] = {
        "label": "OAI 5GC",
        "icon": "cloud_done",
        "desc": "OpenAirInterface 5G Core (Docker Engine API)",
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


DOMAIN_PROVIDERS = {
    "core": _build_core_providers(),
    "ran": {
        "oai": {
            "label": "OAI RAN",
            "icon": "settings_input_antenna",
            "desc": "OpenAirInterface gNB (softmodem mock)",
            "adapter": RanAdapter(),
        },
    },
    "ric": {
        "oai": {
            "label": "FlexRIC",
            "icon": "memory",
            "desc": "FlexRIC near-RT RIC & xApps (mock)",
            "adapter": RicAdapter(),
        },
    },
}
