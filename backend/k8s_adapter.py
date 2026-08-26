"""SshK8sCoreAdapter — provider K8s read-only untuk Core domain (Fase 1).

Kontrak adapter identik dengan SshDockerCoreAdapter (list/get/logs),
TAPI restart() adalah no-op read-only: Fase 1 tidak boleh mengubah
cluster. Restart via kubectl (rollout restart) disiapkan di Fase 2.

Data diambil via SSH ke node master (kubectl --kubeconfig=...) dengan
sudo NOPASSWD, lalu di-cache CACHE_TTL detik agar telemetry loop 3s
tidak spam SSH.
"""
import json
import time
from typing import List, Optional

import paramiko

# comp_id -> {deploy: nama Deployment, kind: jenis NF utk label}
DEFAULT_K8S_CORE_MAP = {
    "amf":  {"deploy": "oai-amf",  "kind": "AMF"},
    "smf":  {"deploy": "oai-smf",  "kind": "SMF"},
    "upf":  {"deploy": "oai-upf",  "kind": "UPF"},
    "nrf":  {"deploy": "oai-nrf",  "kind": "NRF"},
    "ausf": {"deploy": "oai-ausf", "kind": "AUSF"},
    "udm":  {"deploy": "oai-udm",  "kind": "UDM"},
    "udr":  {"deploy": "oai-udr",  "kind": "UDR"},
    "mysql": {"deploy": "mysql",   "kind": "MySQL"},
}


def _to_float(s) -> float:
    try:
        return float(s)
    except Exception:
        return 0.0


class SshK8sCoreAdapter:
    """Read-only Kubernetes adapter untuk 5G Core (namespace tunggal).

    Kontrak: list()/get()/restart()/jitter_health()/get_logs().
    restart() TIDAK melakukan apa pun pada cluster (read-only fase 1);
    ia hanya melaporkan status komponen tanpa mengubahnya.
    """

    CACHE_TTL = 5.0  # detik; lebih longgar dari SSH-docker (1 query kubectl gabungan)

    def __init__(self, deploy_map: dict, ssh_host: str, ssh_user: str,
                 ssh_password: str, ssh_port: int = 22,
                 namespace: str = "5g-core",
                 kubeconfig: str = "/etc/kubernetes/admin.conf"):
        self._map = deploy_map
        self._ssh = {
            "host": ssh_host,
            "port": ssh_port,
            "user": ssh_user,
            "password": ssh_password,
        }
        self._namespace = namespace
        self._kubeconfig = kubeconfig
        self._conn = None          # paramiko client persistent (lazy connect)
        self._cache: dict = {}     # comp_id -> dict komponen
        self._last_fetch = 0.0

    # ------------------------------------------------------------------
    # Kontrak adapter
    # ------------------------------------------------------------------

    def list(self) -> List[dict]:
        self._maybe_refresh()
        return [self._cache[c] for c in self._map if c in self._cache]

    def get(self, comp_id: str) -> Optional[dict]:
        if comp_id not in self._map:
            return None
        self._maybe_refresh()
        return self._cache.get(comp_id)

    async def restart(self, comp_id: str) -> Optional[dict]:
        """READ-ONLY Fase 1: tidak menjalankan mutasi apa pun ke cluster."""
        if comp_id not in self._map:
            return None
        result = self.get(comp_id)
        if result is None:
            return None
        result = dict(result)
        result["detail"] = ("Read-only mode (fase 1): restart dinonaktifkan "
                            "untuk provider k8s.")
        return result

    def jitter_health(self):
        """No-op — data datang dari cluster nyata, bukan simulasi."""
        pass

    def get_logs(self, comp_id: str, tail: int = 100) -> str:
        if comp_id not in self._map:
            return f"Component '{comp_id}' not mapped in k8s configuration."
        dep = self._map[comp_id]["deploy"]
        try:
            out, _ = self._exec(
                f"kubectl -n {self._namespace} logs deployment/{dep} "
                f"--tail={int(tail)} --timestamps"
            )
            return out or "(tidak ada log)"
        except Exception as e:
            return f"[k8s logs error] {e}"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _maybe_refresh(self):
        now = time.time()
        if now - self._last_fetch < self.CACHE_TTL and self._cache:
            return
        try:
            rows = self._fetch_deployments()
        except Exception as e:
            # Jangan kosongkan cache lama saat SSH/kubectl gagal sesaat;
            # tandai semua komponen down agar operator tahu datanya basi.
            for cid in self._map:
                cur = self._cache.get(cid)
                if cur is None or cur.get("status") != "down":
                    self._cache[cid] = self._down_component(cid, f"query error: {str(e)[:120]}")
            self._last_fetch = now
            return
        for cid, meta in self._map.items():
            dep = meta["deploy"]
            row = rows.get(dep)
            if row is None:
                self._cache[cid] = self._down_component(
                    cid, f"Deployment '{dep}' tidak ditemukan di ns {self._namespace}")
                continue
            self._cache[cid] = self._build_component(cid, meta["kind"], dep, row)
        self._last_fetch = now

    def _build_component(self, comp_id: str, kind: str, dep: str, row: dict) -> dict:
        ready = row.get("ready", False)
        phase = row.get("phase", "")
        replicas = int(_to_float(row.get("replicas", 0)))
        avail = int(_to_float(row.get("available", 0)))
        restarts = int(_to_float(row.get("restarts", 0)))
        started_at = row.get("started_at")  # ISO string atau ""

        if not ready and phase == "Running":
            status = "degraded"
            detail = f"{avail}/{replicas} replica ready"
        elif phase == "Running" and ready and avail >= replicas > 0:
            status = "healthy"
            detail = f"{avail}/{replicas} replica ready"
        elif phase in ("Failed", "Unknown") or not phase:
            status = "down"
            detail = f"pod phase={phase or 'n/a'}"
        else:
            # CrashLoopBackOff / Pending / ContainerCreating dst.
            status = "degraded"
            detail = f"phase={phase}, restarts={restarts}"

        started_ts = _parse_iso_utc(started_at)

        return {
            "id": comp_id,
            "name": dep,
            "kind": kind,
            "status": status,
            "detail": detail,
            "host": self._ssh["host"],
            "cpu_pct": 0.0,   # metrics-server tidak tersedia di cluster ini (fase 1)
            "mem_gb": 0.0,
            "mem_pct": 0.0,
            "throughput_mbps": 0.0,
            "port": 0,
            "latency_ms": 0.0,
            "active_ues": 0,
            "last_updated": time.time(),
            "started_at": started_ts or time.time(),
        }

    def _down_component(self, comp_id: str, reason: str) -> dict:
        meta = self._map[comp_id]
        return {
            "id": comp_id,
            "name": meta["deploy"],
            "kind": meta["kind"],
            "status": "down",
            "detail": reason,
            "host": self._ssh["host"],
            "cpu_pct": 0.0,
            "mem_gb": 0.0,
            "mem_pct": 0.0,
            "throughput_mbps": 0.0,
            "port": 0,
            "latency_ms": 0.0,
            "active_ues": 0,
            "last_updated": time.time(),
            "started_at": time.time(),
        }

    # ---- SSH + kubectl -------------------------------------------------

    def _connect(self):
        if self._conn is not None:
            try:
                tr = self._conn.get_transport()
                if tr is not None and tr.is_active():
                    return
            except Exception:
                pass
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(
            self._ssh["host"], port=self._ssh["port"],
            username=self._ssh["user"], password=self._ssh["password"],
            timeout=10, banner_timeout=10, auth_timeout=10,
            allow_agent=False, look_for_keys=False,
        )
        self._conn = c

    def _exec(self, cmd: str, timeout: int = 25):
        """Jalankan satu command di master via sudo bash -c (NOPASSWD)."""
        self._connect()
        wrapped = (
            f"KUBECONFIG={self._kubeconfig} sudo -n bash -c "
            + "'" + cmd.replace("'", "'\\''") + "'"
        )
        _, stdout, stderr = self._conn.exec_command(wrapped, timeout=timeout)
        if stdout is None or stderr is None:
            raise RuntimeError("paramiko exec_command returned no streams")
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        return out, err

    def _fetch_deployments(self) -> dict:
        """Satu round-trip: kubectl get deploy -o json, parse jadi {dep: row}."""
        ns = self._namespace
        cmd = (
            f"kubectl -n {ns} get deployments -o json"
        )
        out, err = self._exec(cmd)
        if not out.strip():
            raise RuntimeError((err or "empty output").strip()[:200])
        data = json.loads(out)
        rows = {}
        for item in data.get("items", []):
            name = item.get("metadata", {}).get("name", "")
            spec = item.get("spec", {})
            st = item.get("status", {})
            conds = {c.get("type"): c.get("status") for c in st.get("conditions", [])}
            rows[name] = {
                "replicas": spec.get("replicas", 0),
                "available": st.get("availableReplicas", 0),
                "ready": conds.get("Available") == "True"
                         and st.get("readyReplicas", 0) == spec.get("replicas", 0),
                "phase": "Running" if st.get("readyReplicas") else "Pending",
                "restarts": 0,  # level deployment; detail restart per-pod di fase 2
                # startTime terbaik yang tersedia read-only level Deployment:
                # creationTimestamp Deployment (bukan restart pod).
                "started_at": item.get("metadata", {}).get("creationTimestamp", "") or "",
            }
        return rows


def _parse_iso_utc(s: str) -> float:
    """Parse '2026-08-26T07:30:07Z' -> epoch seconds; 0.0 kalau gagal."""
    if not s:
        return 0.0
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0
