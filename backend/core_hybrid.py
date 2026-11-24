"""
Hybrid Core exclusive switching — Open5GS (systemd) <-> OAI 5G Core (Docker
compose, oai-cn5g-fed) — node `core` (10.91.2.151), bare-metal 3-PC testbed.

Dibuat 13 Nov 2026 setelah root cause dataplane UPF OAI ditemukan & fixed
(lihat skill openran-dashboard-testbed): GTP-U paket "silently dropped" di
Docker bridge network -> fix `network_mode: host` + samain interface_name
N3/N4 + `extra_hosts` utk resolve NRF/AMF/SMF/dst (DNS Docker tidak jalan di
host-mode). Sudah diverifikasi end-to-end (speedtest ~25 Mbps UE fisik).

Kedua stack Core BENAR-BENAR exclusive secara fisik: sama-sama mau bind host
port yang SAMA di IP yang SAMA (AMF 38412/sctp, SMF/N4 8805/udp, UPF/N3
2152/udp, semua di 10.91.2.151). Tidak bisa dua-duanya hidup bersamaan.

Alur switch_core_provider() (sama persis pola ran_hybrid.connect_ran_to_core):
  1. target == provider yang SECARA FISIK aktif sekarang -> no-op (idempotent).
  2. Matikan provider LAMA penuh (systemctl stop 11 unit Open5GS, ATAU
     `docker compose down` seluruh stack oai-cn5g-fed).
  3. Verifikasi port 38412/8805/2152 benar-benar kosong (retry — TIME_WAIT
     kernel butuh jeda beberapa detik).
  4. Nyalakan provider BARU, tunggu, verifikasi AMF listen di :38412.
  5. Gagal di langkah manapun setelah stop -> ROLLBACK: coba nyalakan lagi
     provider lama, supaya testbed tidak tertinggal dalam keadaan "Core mati
     total".

Guardrail (AGENTS.md / skill openran-dashboard-testbed):
  - TIDAK PERNAH menyentuh isi config Open5GS atau srsRAN di sini — hanya
    lifecycle command (systemctl/docker compose), tidak ada edit file.
  - Config OAI (basic_nrf_config.yaml, docker-compose-*.yaml) juga TIDAK
    diubah oleh modul ini — itu sudah final hasil sesi troubleshooting hari
    ini, modul ini cuma start/stop stack yang sudah benar.
  - Lock (_CORE_SWITCH_LOCK) mencegah race dua switch bersamaan.
  - dry_run=True selalu tersedia untuk test tanpa actuation nyata.
"""
import os
import time
import threading
from fastapi import HTTPException

from ran_hybrid import _ssh_exec  # reuse SSH helper (support publickey Ed25519)

OPEN5GS_UNITS = [
    "open5gs-nrfd", "open5gs-scpd", "open5gs-amfd", "open5gs-smfd", "open5gs-upfd",
    "open5gs-ausfd", "open5gs-udmd", "open5gs-udrd", "open5gs-pcfd", "open5gs-nssfd",
    "open5gs-bsfd",
]

OAI_COMPOSE_DIR = "/home/core/oai-cn5g-fed/docker-compose"
OAI_COMPOSE_FILES = (
    "docker-compose-basic-nrf.yaml",
    "docker-compose-telmat-override.yaml",
    "docker-compose-telmat-hostip.yaml",
)
OAI_COMPOSE_CMD = "docker compose " + " ".join(f"-f {f}" for f in OAI_COMPOSE_FILES)

CORE_EXCLUSIVE_PORTS = [38412, 8805, 2152]  # AMF sctp, SMF/N4 pfcp, UPF/N3 gtp-u

_CORE_SWITCH_LOCK = threading.Lock()


def _core_ssh_creds():
    """Kredensial SSH node core — SAMA utk kedua provider (satu host fisik)."""
    host = os.environ.get("OPEN5GS_SYSTEMD_SSH_HOST", "10.91.2.151")
    user = os.environ.get("OPEN5GS_SYSTEMD_SSH_USER", "core")
    password = os.environ.get("OPEN5GS_SYSTEMD_SSH_PASSWORD", "")
    key_path = os.environ.get("OPEN5GS_SYSTEMD_SSH_KEY_PATH", "") or None
    port = int(os.environ.get("OPEN5GS_SYSTEMD_SSH_PORT", "22"))
    return host, user, password, port, key_path


def _ports_free(host, user, password, port, key_path, ports, retries=4, delay=3):
    """Cek port host (ss -an) benar2 kosong, retry karena TIME_WAIT butuh jeda."""
    pattern = "|".join(str(p) for p in ports)
    out = ""
    for attempt in range(retries):
        cmd = "ss -an 2>/dev/null | grep -E ':(" + pattern + r")\b'"
        out, err, code = _ssh_exec(host, user, password, port, cmd, key_path=key_path, timeout=10)
        if not out.strip():
            return True, ""
        if attempt < retries - 1:
            time.sleep(delay)
    return False, out.strip()


def core_provider_status():
    """Status FISIK kedua provider Core (bukan cuma bookkeeping DB)."""
    host, user, password, port, key_path = _core_ssh_creds()
    try:
        cmd = (
            "systemctl is-active open5gs-amfd 2>&1; echo __S1__; "
            "docker inspect oai-amf --format '{{.State.Status}}' 2>&1; echo __S2__; "
            "ss -an 2>/dev/null | grep -E ':(38412|8805|2152)\\b'; echo __END__"
        )
        out, err, code = _ssh_exec(host, user, password, port, cmd, key_path=key_path, timeout=15)
        s1, rem = out.split("__S1__", 1) if "__S1__" in out else (out, "")
        s2, rem2 = rem.split("__S2__", 1) if "__S2__" in rem else (rem, "")
        ports_raw = rem2.split("__END__")[0] if "__END__" in rem2 else rem2
        open5gs_active = s1.strip() == "active"
        oai_running = s2.strip() == "running"
        return {
            "open5gs": {"status": "active" if open5gs_active else "inactive"},
            "oai": {"status": "running" if oai_running else "stopped"},
            "ports_listening": [l.strip() for l in ports_raw.splitlines() if l.strip()],
        }
    except Exception as e:
        return {"error": str(e)[:300]}


def _current_physical_provider(status: dict):
    if "error" in status:
        return None
    if status["open5gs"]["status"] == "active":
        return "open5gs"
    if status["oai"]["status"] == "running":
        return "oai"
    return None


def reconcile_physical_provider():
    """Ditambah 24 Nov 2026 - deteksi drift antara DB bookkeeping & kondisi
    fisik nyata Core (misal ada yang switch manual via SSH, bukan lewat
    tombol dashboard, jadi DB ketinggalan). Dipanggil setiap kali endpoint
    GET /api/core/active-provider diakses (frontend poll tiap beberapa
    detik), supaya drift kekoreksi otomatis tanpa perlu intervensi manual.

    Return (physical_provider_or_None, conflict: bool, unknown: bool).
    - unknown=True kalau SSH/cek status gagal -> JANGAN sentuh DB, nggak ada
      cukup info buat mastiin kondisi fisik beneran.
    - conflict=True kalau Open5GS DAN OAI somehow jalan bersamaan (harusnya
      exclusive) -> JANGAN auto-pilih salah satu (ambigu), biarin DB apa
      adanya & biar user cek manual.
    """
    status = core_provider_status()
    if "error" in status:
        return None, False, True
    open5gs_active = status["open5gs"]["status"] == "active"
    oai_active = status["oai"]["status"] == "running"
    if open5gs_active and oai_active:
        return None, True, False
    if open5gs_active:
        return "open5gs", False, False
    if oai_active:
        return "oai", False, False
    return None, False, False


def _stop_provider(host, user, password, port, key_path, provider, actions):
    if provider == "open5gs":
        cmd = "sudo systemctl stop " + " ".join(OPEN5GS_UNITS) + " 2>&1; echo __CODE__$?"
        out, err, code = _ssh_exec(host, user, password, port, cmd, key_path=key_path, timeout=40)
        actions["stop_open5gs"] = (out + err)[:600]
    elif provider == "oai":
        cmd = f"cd {OAI_COMPOSE_DIR} && {OAI_COMPOSE_CMD} down 2>&1; echo __CODE__$?"
        out, err, code = _ssh_exec(host, user, password, port, cmd, key_path=key_path, timeout=60)
        actions["stop_oai"] = (out + err)[:600]


def _start_provider(host, user, password, port, key_path, provider, actions):
    if provider == "open5gs":
        cmd = (
            "sudo systemctl start " + " ".join(OPEN5GS_UNITS) +
            " 2>&1; echo __CODE__$?; sleep 5; ss --sctp -an 2>/dev/null | grep ':38412'"
        )
        out, err, code = _ssh_exec(host, user, password, port, cmd, key_path=key_path, timeout=60)
        actions["start_open5gs"] = (out + err)[:900]
        return ("LISTEN" in out) or ("ESTAB" in out)
    elif provider == "oai":
        cmd = (
            f"cd {OAI_COMPOSE_DIR} && {OAI_COMPOSE_CMD} up -d 2>&1; echo __CODE__$?; "
            "sleep 15; ss --sctp -an 2>/dev/null | grep ':38412'"
        )
        out, err, code = _ssh_exec(host, user, password, port, cmd, key_path=key_path, timeout=90)
        actions["start_oai"] = (out + err)[:900]
        return ("LISTEN" in out) or ("ESTAB" in out)
    return False


def deactivate_core_provider(requested_by: str, dry_run: bool = False):
    """Matikan provider Core yang SECARA FISIK aktif sekarang, tanpa nyalain
    yang lain (beda dari switch_core_provider yang selalu start target baru).

    Ditambah 13 Nov 2026 - sebelum ini tombol "Deactivate" di halaman Core
    cuma hapus baris bookkeeping DB, container/unit tetap nyala (gap yang
    ketemu user pas live-test tombol dashboard). Sekarang mirror pola
    ran_hybrid.disconnect_ran: actuation nyata (stop), bukan cuma DB."""
    host, user, password, port, key_path = _core_ssh_creds()
    status = core_provider_status()
    if "error" in status:
        raise HTTPException(500, f"core_status_check_failed: {status['error']}")

    current = _current_physical_provider(status)

    if dry_run:
        return {
            "status": "dry_run",
            "dry_run": True,
            "current_provider": current,
            "action": "no-op (tidak ada provider yang aktif secara fisik)" if not current
            else f"stop {current} sepenuhnya (tidak start apapun setelahnya)",
        }

    if not current:
        return {"status": "noop", "current_provider": None}

    actions = {}
    _stop_provider(host, user, password, port, key_path, current, actions)
    ok, remaining = _ports_free(host, user, password, port, key_path, CORE_EXCLUSIVE_PORTS)

    return {
        "status": "stopped",
        "previous_provider": current,
        "current_provider": None,
        "ports_free": ok,
        "remaining_ports": remaining if not ok else "",
        "actions": actions,
    }


def switch_core_provider(target_provider: str, requested_by: str, dry_run: bool = False):
    """Exclusive switch Core software: 'open5gs' <-> 'oai'. Lihat alur di
    docstring modul. Raise HTTPException kalau gagal (dengan detail actions
    yang sudah dijalankan + hasil rollback kalau sempat dicoba)."""
    if target_provider not in ("open5gs", "oai"):
        raise HTTPException(400, f"Unknown core provider '{target_provider}'")

    host, user, password, port, key_path = _core_ssh_creds()
    status = core_provider_status()
    if "error" in status:
        raise HTTPException(500, f"core_status_check_failed: {status['error']}")

    current = _current_physical_provider(status)

    if dry_run:
        return {
            "status": "dry_run",
            "dry_run": True,
            "current_provider": current,
            "target_provider": target_provider,
            "action": (
                "no-op (provider target sudah aktif secara fisik)"
                if current == target_provider else
                f"stop {current or '(tidak ada yang aktif)'} sepenuhnya -> "
                f"verifikasi port 38412/8805/2152 kosong -> start {target_provider}"
            ),
        }

    if current == target_provider:
        return {"status": "noop", "current_provider": current, "target_provider": target_provider}

    actions = {}

    # 1) stop provider lama (dan, sbg jaga2 idempotent, coba stop "other" juga
    #    kalau status physical sempat ambigu/unknown)
    other = "oai" if target_provider == "open5gs" else "open5gs"
    for prov in {p for p in (current, other) if p}:
        _stop_provider(host, user, password, port, key_path, prov, actions)

    # 2) verifikasi port benar2 kosong sebelum start yang baru
    ok, remaining = _ports_free(host, user, password, port, key_path, CORE_EXCLUSIVE_PORTS)
    if not ok:
        if current:
            _start_provider(host, user, password, port, key_path, current, actions)
        raise HTTPException(500, detail={
            "reason": "ports_not_free",
            "message": f"Port Core masih kepake setelah stop: {remaining}",
            "rollback": f"mencoba menyalakan ulang {current}" if current else "tidak ada provider lama utk rollback",
            "actions": actions,
        })

    # 3) start provider baru
    try:
        amf_listening = _start_provider(host, user, password, port, key_path, target_provider, actions)
    except Exception as e:
        if current:
            try:
                _start_provider(host, user, password, port, key_path, current, actions)
            except Exception:
                pass
        raise HTTPException(500, detail={
            "reason": "start_failed",
            "message": str(e)[:300],
            "rollback": f"mencoba menyalakan ulang {current}" if current else "tidak ada provider lama utk rollback",
            "actions": actions,
        })

    if not amf_listening:
        if current:
            try:
                _start_provider(host, user, password, port, key_path, current, actions)
            except Exception:
                pass
        raise HTTPException(500, detail={
            "reason": "amf_not_listening",
            "message": f"{target_provider} sudah di-start tapi AMF belum listen di :38412",
            "rollback": f"mencoba menyalakan ulang {current}" if current else "tidak ada provider lama utk rollback",
            "actions": actions,
        })

    return {
        "status": "connected",
        "previous_provider": current,
        "current_provider": target_provider,
        "amf_listening": amf_listening,
        "actions": actions,
    }
