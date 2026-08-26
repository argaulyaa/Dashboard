"""Unit test SshK8sCoreAdapter — TANPA network (mock _fetch_deployments).

Run: python3 test_k8s_adapter.py
"""
import os

# Pastikan provider k8s fallback mock saat import adapters di main.py nanti.
os.environ.pop("K8S_SSH_HOST", None)
os.environ["DATABASE_URL"] = "sqlite:///./test_oran_k8s.db"

import time
from typing import Optional

sys_path_hack = __import__("sys")
sys_path_hack.path.insert(0, ".")
from k8s_adapter import SshK8sCoreAdapter  # noqa: E402


def make_adapter() -> SshK8sCoreAdapter:
    return SshK8sCoreAdapter(
        deploy_map={
            "amf":  {"deploy": "oai-amf", "kind": "AMF"},
            "smf":  {"deploy": "oai-smf", "kind": "SMF"},
            "upf":  {"deploy": "oai-upf", "kind": "UPF"},
            "mysql": {"deploy": "mysql", "kind": "MySQL"},
        },
        ssh_host="10.91.2.156", ssh_user="telmat", ssh_password="x",
        namespace="5g-core",
    )


FAKE_ROWS = {
    "oai-amf": {"replicas": 1, "available": 1, "ready": True,
                "phase": "Running", "restarts": 0,
                "started_at": "2026-08-26T07:30:07Z"},
    "oai-smf": {"replicas": 1, "available": 0, "ready": False,
                "phase": "Pending", "restarts": 3,
                "started_at": "2026-08-24T01:00:00Z"},
}


def test_healthy_and_degraded():
    a = make_adapter()
    a._fetch_deployments = lambda: dict(FAKE_ROWS)  # type: ignore[method-assign]
    a._maybe_refresh()
    amf: Optional[dict] = a.get("amf")
    assert amf is not None
    assert amf["status"] == "healthy", amf
    assert amf["detail"] == "1/1 replica ready"
    smf = a.get("smf") or {}
    assert smf.get("status") == "degraded", smf
    assert smf.get("started_at", 0) > 0
    print("PASS healthy/degraded mapping")


def test_missing_and_error():
    a = make_adapter()
    # smf/upf/mysql tidak ada di hasil query -> down "tidak ditemukan"
    a._fetch_deployments = lambda: {"oai-amf": FAKE_ROWS["oai-amf"]}  # type: ignore[method-assign]
    a._maybe_refresh()
    for cid in ("smf", "upf", "mysql"):
        c = a.get(cid) or {}
        assert c.get("status") == "down" and "tidak ditemukan" in c.get("detail", ""), c

    # Error query: semua komponen ditandai down dgn reason "query error"
    def boom():
        raise RuntimeError("ssh refused")

    a2 = make_adapter()
    a2._fetch_deployments = boom  # type: ignore[method-assign]
    a2._last_fetch = 0  # force refresh -> exception path
    a2._maybe_refresh()
    upf = a2.get("upf") or {}
    assert upf.get("status") == "down" and "query error" in upf.get("detail", ""), upf
    print("PASS missing-deployment + query-error handling")


def test_restart_readonly():
    import asyncio

    a = make_adapter()
    called = {"exec": 0}

    def fake_exec(cmd, timeout=25):
        called["exec"] += 1
        return "", ""

    a._exec = fake_exec  # type: ignore[method-assign]
    a._fetch_deployments = lambda: dict(FAKE_ROWS)  # type: ignore[method-assign]
    res = asyncio.run(a.restart("amf"))
    assert res is not None and res["status"] == "healthy", res
    assert "Read-only mode" in res["detail"], res
    assert called["exec"] == 0, "restart TIDAK BOLEH eksekusi command ke cluster"
    assert asyncio.run(a.restart("tidakada")) is None
    print("PASS restart read-only no-op (0 exec)")


def test_logs_exec():
    a = make_adapter()
    captured = {}

    def fake_exec(cmd, timeout=25):
        captured["cmd"] = cmd
        return "log-line-1\nlog-line-2", ""

    a._exec = fake_exec  # type: ignore[method-assign]
    out = a.get_logs("amf", tail=50)
    assert "log-line-1" in out
    assert "logs deployment/oai-amf" in captured["cmd"]
    assert "--tail=50 --timestamps" in captured["cmd"]
    print("PASS get_logs command shape:", captured["cmd"])


if __name__ == "__main__":
    test_healthy_and_degraded()
    test_missing_and_error()
    test_restart_readonly()
    test_logs_exec()
    print("")
    print("SEMUA TEST PASS")
