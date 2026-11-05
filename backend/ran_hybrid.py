"""
Hybrid Core<->RAN connect (go live) — BARE-METAL 3 PC (core/ran/ric), bukan K8s.

Rewrite 3 Nov 2026 (lihat DOKUMENTASI-PROYEK-DASHBOARD-ORAN-KONTEKS-AGENT.md
§4.6): cluster K8s (nas-master, 10.91.2.156) sudah tidak ada. Testbed sekarang
murni 3 Mini PC — core (10.91.2.151, Open5GS systemd), ran (10.91.2.152,
srsRAN/OAI gNB systemd + 1x USRP B210), ric (10.91.2.153, FlexRIC). Modul ini
TIDAK memanggil kubectl/Helm/namespace/NodePort sama sekali.

POST /api/ran/connect     {core_provider, ran_provider, dry_run?}
GET  /api/ran/status      systemctl is-active (core+ran) + ss --sctp 38412

Guardrail yang dipegang (AGENTS.md / DOKUMENTASI-...-AGENT.md §11):
  - TIDAK pakai `sed -i` untuk ubah YAML/conf gNB -> pakai python re.sub via
    SSH (_rewrite_remote_file), sed -i pernah merusak YAML di testbed ini.
  - Hanya SATU gNB boleh hidup (1x USRP B210) -> selalu stop kedua unit RAN
    sebelum start yang dipilih, `pkill -9` cadangan kalau systemd stop macet.
  - Jangan "menyelesaikan" core_provider yang belum live (oai docker lama,
    10 container Exited) -> connect ke situ ditolak 400 dengan pesan jujur,
    bukan pura-pura berhasil.
"""
import os
import re
import time
import threading
import shlex
import paramiko
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# CORE_RAN_MAP — satu entri per provider Core yang MUNGKIN dipilih dari UI.
# Key HARUS sama persis dengan key provider di adapters.py::_build_core_providers
# (frontend memakai key ini untuk dropdown/activate). Hanya "open5gs" live=True
# (satu-satunya provider Core sekarang — Open5GS bare-metal systemd). "oai"
# tetap terdaftar supaya dropdown tidak error kalau ditambahkan lagi nanti,
# tapi connect() menolak dengan pesan jujur (PENDING, bentrok port dengan
# Open5GS) — bukan pura-pura berhasil.
# ---------------------------------------------------------------------------
CORE_RAN_MAP = {
    "open5gs": {
        "live": True,
        "kind": "systemd",
        "amf_ip": "10.91.2.151",
        "amf_port": 38412,
        "ssh_host_env": "OPEN5GS_SYSTEMD_SSH_HOST",
        "ssh_user_env": "OPEN5GS_SYSTEMD_SSH_USER",
        "ssh_password_env": "OPEN5GS_SYSTEMD_SSH_PASSWORD",
        "ssh_key_env": "OPEN5GS_SYSTEMD_SSH_KEY_PATH",
        "ssh_port_env": "OPEN5GS_SYSTEMD_SSH_PORT",
        # unit representatif untuk cek "core hidup" — AMF cukup mewakili NF lain
        "probe_unit": "open5gs-amfd",
    },
    "oai": {
        "live": False,
        "kind": "unsupported",
        "reason": "OAI 5G Core PENDING — Docker compose OAI ingin bind port host yang sama dengan Open5GS yang sedang live (AMF 10.91.2.151:38412/sctp, SMF :8805/udp, UPF :2152/udp). Menyalakannya akan bentrok port atau butuh ubah config Open5GS yang sedang jalan. Butuh strategi port/IP terpisah yang disetujui dulu.",
    },
}

# ---------------------------------------------------------------------------
# RAN_MAP — unit systemd & config NYATA di node ran (10.91.2.152), dicek
# langsung via SSH per 3 Nov 2026 (bukan diasumsikan dari dokumen lama).
# Hanya satu boleh aktif sekaligus (1x USRP B210, ExecStartPre pkill).
# ---------------------------------------------------------------------------
RAN_MAP = {
    "srsran": {
        "unit": "srsran-gnb.service",
        # Config dipilih via /etc/default/srsran-gnb (var GNB_CONFIG), BUKAN
        # hardcoded di ExecStart — komentar di unit file: "the dashboard
        # rewrites it to switch band". n40 = 40MHz (default), n78 tersedia.
        "config_env_file": "/etc/default/srsran-gnb",
        "config_env_var": "GNB_CONFIG",
        "default_config": "/home/ran/srsran-configs/n40_RICbare.yaml",
        "amf_path": ["cu_cp", "amf", "addr"],  # lokasi field AMF addr di YAML
    },
    "oai": {
        # Diupdate 5 Nov 2026: production OAI sekarang unit "oai-gnb-n40.service"
        # (bukan "oai-gnb.service" lama yg pakai config band 78) + binary build
        # develop-Nov2026 (fix PUCCH resource-selection + SSB offset — lihat
        # skill openran-dashboard-testbed §Critical Context). Config band n40,
        # 51 PRB/20MHz, terverifikasi 12.74 Mbps dgn Oppo Reno 8. E2 agent
        # sengaja nonaktif (incompatible dgn FlexRIC RIC versi lama, PENDING).
        "unit": "oai-gnb-n40.service",
        "config": "/home/ran/gnb-proven-441s-lowgain-v2.conf",
        "amf_field": "amf_ip_address",  # format: amf_ip_address = ({ ipv4 = "X"; });
    },
}

_RAN_CONNECT_LOCK = threading.Lock()


def _ssh_exec(host, user, password, port, cmd, timeout=25, sudo_pw=None, key_path=None):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if key_path:
        pkey = paramiko.Ed25519Key.from_private_key_file(key_path)
        c.connect(hostname=host, port=int(port), username=user, pkey=pkey, timeout=8, banner_timeout=10)
    else:
        c.connect(hostname=host, port=int(port), username=user, password=password, timeout=8, banner_timeout=10)
    try:
        if sudo_pw is not None:
            full = f"echo {shlex.quote(sudo_pw)} | sudo -S -p '' {cmd}"
        else:
            full = cmd
        _, stdout, stderr = c.exec_command(full, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return out, err, code
    finally:
        c.close()


def _core_ssh_creds(provider: str):
    """Ambil kredensial SSH node Core untuk provider live. Dukung publickey
    (Core bare-metal 10.91.2.151 hanya menerima publickey, password dimatikan)."""
    info = CORE_RAN_MAP[provider]
    host = os.environ.get(info["ssh_host_env"], "10.91.2.151")
    user = os.environ.get(info["ssh_user_env"], "core")
    password = os.environ.get(info["ssh_password_env"], "")
    key_path = os.environ.get(info["ssh_key_env"], "") or None
    port = int(os.environ.get(info["ssh_port_env"], "22"))
    return host, user, password, port, key_path


def _ran_ssh_creds():
    ran_host = os.environ.get("OAI_SSH_RAN_HOST", "10.91.2.152")
    ran_user = os.environ.get("OAI_SSH_RAN_USER", "ran")
    ran_pw = os.environ.get("OAI_SSH_RAN_PASSWORD", "")
    ran_port = int(os.environ.get("OAI_SSH_RAN_PORT", "22"))
    return ran_host, ran_user, ran_pw, ran_port


def core_status_snapshot():
    """Status tiap provider Core — bare-metal: systemctl is-active + SCTP
    listen di :38412 (ganti total dari `kubectl get deploy` versi lama)."""
    res = {}
    for key, info in CORE_RAN_MAP.items():
        if not info.get("live"):
            res[key] = {"status": "unsupported", "reason": info.get("reason", ""), "replicas": 0}
            continue
        try:
            host, user, password, port, key_path = _core_ssh_creds(key)
            unit = info["probe_unit"]
            cmd = (
                f"systemctl is-active {unit} 2>&1; echo __S1__; "
                f"ss --sctp -an 2>/dev/null | grep -c ':{info['amf_port']} '"
            )
            out, err, code = _ssh_exec(host, user, password, port, cmd, key_path=key_path, timeout=15)
            active_part, _, listen_part = out.partition("__S1__")
            is_active = active_part.strip() == "active"
            listen_count = 0
            try:
                listen_count = int(listen_part.strip() or 0)
            except Exception:
                listen_count = 0
            res[key] = {
                "status": "active" if is_active else "inactive",
                "replicas": 1 if is_active else 0,
                "amf_ip": info["amf_ip"],
                "amf_port": info["amf_port"],
                "amf_listening": listen_count > 0,
                "host": host,
            }
        except Exception as e:
            res[key] = {"status": "unknown", "error": str(e)[:200]}
    return res


def ran_status_snapshot():
    ran_host, ran_user, ran_pw, ran_port = _ran_ssh_creds()
    try:
        cmd = (
            "systemctl is-active srsran-gnb.service 2>&1; echo __S1__; "
            "systemctl is-active oai-gnb-n40.service 2>&1; echo __S2__; "
            "ps -eo args 2>/dev/null | grep -E 'apps/gnb/gnb|nr-softmodem' | grep -v grep | head -5; echo __S3__; "
            "ss --sctp -an 2>/dev/null | grep ':38412' | head -20; echo __S4__; "
            "cat /etc/default/srsran-gnb 2>/dev/null; echo __S5__; "
            "grep -A2 'amf:' /home/ran/srsran-configs/*.yaml 2>/dev/null | grep addr | head -5; "
            "grep -E 'amf_ip_address' /home/ran/gnb-proven-441s-lowgain-v2.conf 2>/dev/null | head -3; echo __END__"
        )
        out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, cmd, timeout=20)

        def split_marker(txt, m):
            if m in txt:
                a, b = txt.split(m, 1)
                return a, b
            return txt, ""

        rem = out
        a, rem = split_marker(rem, "__S1__")
        srs_active = a.strip()
        a, rem = split_marker(rem, "__S2__")
        oai_active = a.strip()
        a, rem = split_marker(rem, "__S3__")
        ps_raw = a.strip()
        a, rem = split_marker(rem, "__S4__")
        sctp_raw = a.strip()
        a, rem = split_marker(rem, "__S5__")
        active_config_file = a.strip()
        rest = rem.split("__END__")[0].strip() if "__END__" in rem else rem.strip()

        estab_raw = [l for l in sctp_raw.splitlines() if "ESTAB" in l] if sctp_raw else []

        def _norm(l):
            n = re.sub(r"%\w+", "", l)
            n = re.sub(r"\s+", " ", n).strip()
            return n

        seen = {}
        for ln in estab_raw:
            n = _norm(ln)
            if n not in seen:
                seen[n] = ln.strip()
        sctp_estab = len(seen)
        sctp_lines = list(seen.values())

        return {
            "srsgnb_active": srs_active,
            "oai_gnb_active": oai_active,
            "ps": ps_raw[:2000],
            "sctp_estab": sctp_estab,
            "sctp_lines": sctp_lines,
            "active_config_file": active_config_file,
            "amf_addr_raw": rest,
            "raw": out[:4000],
        }
    except Exception as e:
        return {"error": str(e)[:500], "sctp_estab": 0, "sctp_lines": []}


# ---------------------------------------------------------------------------
# Retarget AMF di config RAN — python re.sub via SSH, BUKAN sed -i (guardrail
# AGENTS.md: sed -i pernah merusak YAML -> UPF crash / AMF PLMN reject).
# ---------------------------------------------------------------------------

def _rewrite_srsran_amf(ran_host, ran_user, ran_pw, ran_port, config_path, amf_ip, amf_port):
    """Ganti field cu_cp.amf.addr/port di file YAML srsRAN via python re.sub
    dijalankan remote (tidak ada state lokal, file tetap di node ran)."""
    script = (
        "import re\n"
        f"p = {config_path!r}\n"
        "t = open(p, encoding='utf-8').read()\n"
        "t2 = re.sub(r'(cu_cp:\\s*\\n\\s*amf:\\s*\\n\\s*addr:\\s*)[0-9.]+', "
        f"r'\\\\g<1>{amf_ip}', t, count=1)\n"
        "t3 = re.sub(r'(cu_cp:\\s*\\n\\s*amf:\\s*\\n\\s*addr:[^\\n]*\\n\\s*port:\\s*)[0-9]+', "
        f"r'\\\\g<1>{amf_port}', t2, count=1)\n"
        "changed = (t3 != t)\n"
        "open(p, 'w', encoding='utf-8').write(t3)\n"
        "print('OK' if changed else 'NOCHANGE')\n"
    )
    remote_cmd = f"python3 -c {shlex.quote(script)}"
    out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, remote_cmd, timeout=15)
    return (out + err).strip(), code


def _rewrite_oai_amf(ran_host, ran_user, ran_pw, ran_port, config_path, amf_ip):
    """Ganti amf_ip_address di config OAI (.conf, format libconfig) via
    python re.sub remote — pola sama, tanpa sed -i."""
    script = (
        "import re\n"
        f"p = {config_path!r}\n"
        "t = open(p, encoding='utf-8').read()\n"
        "t2 = re.sub(r'(amf_ip_address\\s*=\\s*\\(\\{\\s*ipv4\\s*=\\s*\")[^\"]*(\")', "
        f"r'\\\\g<1>{amf_ip}\\\\g<2>', t, count=1)\n"
        "changed = (t2 != t)\n"
        "open(p, 'w', encoding='utf-8').write(t2)\n"
        "print('OK' if changed else 'NOCHANGE')\n"
    )
    remote_cmd = f"python3 -c {shlex.quote(script)}"
    out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, remote_cmd, timeout=15)
    return (out + err).strip(), code


def _set_srsran_config_file(ran_host, ran_user, ran_pw, ran_port, config_path, sudo_pw):
    """Ganti GNB_CONFIG di /etc/default/srsran-gnb (env file root-only) via
    python re.sub + sudo tee, bukan sed -i langsung ke file root."""
    script = (
        "import re\n"
        "p = '/etc/default/srsran-gnb'\n"
        "t = open(p, encoding='utf-8').read() if __import__('os').path.exists(p) else 'GNB_CONFIG=\\n'\n"
        f"t2 = re.sub(r'GNB_CONFIG=.*', 'GNB_CONFIG={config_path}', t) if 'GNB_CONFIG=' in t else t + 'GNB_CONFIG={config_path}\\n'\n"
        "open('/tmp/.srsran-gnb.new', 'w', encoding='utf-8').write(t2)\n"
        "print('WROTE_TMP')\n"
    )
    out1, err1, code1 = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, f"python3 -c {shlex.quote(script)}", timeout=10)
    out2, err2, code2 = _ssh_exec(
        ran_host, ran_user, ran_pw, ran_port,
        "cp /tmp/.srsran-gnb.new /etc/default/srsran-gnb && rm -f /tmp/.srsran-gnb.new && cat /etc/default/srsran-gnb",
        sudo_pw=sudo_pw, timeout=10,
    )
    return (out1 + err1 + out2 + err2).strip(), code2


def connect_ran_to_core(core_provider: str, ran_provider: str, requested_by: str, dry_run: bool = False):
    """Logika inti hybrid connect bare-metal. Dipanggil dari main.py endpoint
    POST /api/ran/connect. Mengembalikan dict hasil (atau raise HTTPException).

    Alur (sesuai §4.6 DOKUMENTASI-PROYEK-DASHBOARD-ORAN-KONTEKS-AGENT.md):
      1. Validasi core_provider live (hanya open5gs saat ini).
      2. Stop KEDUA unit gNB (srsran-gnb + oai-gnb) — hanya 1 boleh hidup,
         1x USRP B210 dipakai bergiliran.
      3. Retarget AMF addr di config RAN terpilih via python re.sub (bukan
         sed -i) — kalau srsRAN, juga ganti GNB_CONFIG di /etc/default dulu.
      4. Start unit RAN terpilih, tunggu beberapa detik, cek SCTP ESTAB.
    """
    if core_provider not in CORE_RAN_MAP:
        raise HTTPException(400, f"Unknown core_provider '{core_provider}'. Valid: {list(CORE_RAN_MAP.keys())}")
    if ran_provider not in RAN_MAP:
        raise HTTPException(400, f"Unknown ran_provider '{ran_provider}'. Valid: {list(RAN_MAP.keys())}")

    core_info = CORE_RAN_MAP[core_provider]
    ran_info = RAN_MAP[ran_provider]

    if not core_info.get("live"):
        raise HTTPException(400, detail={
            "reason": "core_not_live",
            "message": core_info.get("reason", f"Core provider '{core_provider}' tidak aktif di testbed bare-metal ini."),
        })

    target_amf_ip = core_info["amf_ip"]
    target_amf_port = core_info["amf_port"]

    if dry_run:
        config_path = ran_info.get("default_config") or ran_info.get("config")
        return {
            "status": "dry_run",
            "dry_run": True,
            "core": {
                "requested_provider": core_provider,
                "amf_ip": target_amf_ip,
                "amf_port": target_amf_port,
                "action": "none — Open5GS bare-metal always-on systemd, tidak ada scale",
            },
            "ran": {
                "requested_provider": ran_provider,
                "unit": ran_info["unit"],
                "config_path": config_path,
                "amf_addr_set": f"{target_amf_ip}:{target_amf_port}",
                "action": f"stop kedua unit RAN (1x USRP B210) -> retarget AMF di {config_path} via python re.sub -> start {ran_info['unit']}",
            },
            "sctp_estab": False,
        }

    ran_host, ran_user, ran_pw, ran_port = _ran_ssh_creds()
    sudo_pw = ran_pw
    ran_actions = {}

    # 1) stop kedua unit (hanya 1 boleh hidup — 1x USRP B210)
    for unit in ("srsran-gnb.service", "oai-gnb-n40.service"):
        try:
            full = f"systemctl stop {unit} 2>&1; echo __CODE__$?"
            out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, full, sudo_pw=sudo_pw, timeout=30)
            ran_actions[f"stop_{unit}"] = (out + err)[:400]
        except Exception as e:
            ran_actions[f"stop_{unit}"] = str(e)[:400]
    try:
        out, err, code = _ssh_exec(
            ran_host, ran_user, ran_pw, ran_port,
            "pkill -9 -f 'apps/gnb/gnb' 2>&1; pkill -9 -x nr-softmodem 2>&1; sleep 2; echo done",
            sudo_pw=sudo_pw, timeout=15,
        )
        ran_actions["pkill"] = (out + err)[:400]
    except Exception as e:
        ran_actions["pkill"] = str(e)[:400]

    # 2) retarget AMF di config yang akan dipakai
    amf_set = f"{target_amf_ip}:{target_amf_port}"
    try:
        if ran_provider == "srsran":
            config_path = ran_info["default_config"]
            out, code = _set_srsran_config_file(ran_host, ran_user, ran_pw, ran_port, config_path, sudo_pw)
            ran_actions["set_gnb_config_env"] = out[:400]
            out2, code2 = _rewrite_srsran_amf(ran_host, ran_user, ran_pw, ran_port, config_path, target_amf_ip, target_amf_port)
            ran_actions["rewrite_amf_srsran"] = out2[:400]
            if code2 != 0:
                raise HTTPException(500, f"srsran_amf_rewrite_failed: {out2}")
        else:  # oai
            config_path = ran_info["config"]
            out2, code2 = _rewrite_oai_amf(ran_host, ran_user, ran_pw, ran_port, config_path, target_amf_ip)
            ran_actions["rewrite_amf_oai"] = out2[:400]
            if code2 != 0:
                raise HTTPException(500, f"oai_amf_rewrite_failed: {out2}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"amf_retarget_failed: {e}")

    # 3) start unit terpilih, tunggu, cek SCTP ESTAB
    unit = ran_info["unit"]
    sctp_estab = False
    sctp_lines = []
    try:
        full = f"systemctl start {unit} 2>&1; echo __START__$?; sleep 5; ss --sctp -an 2>/dev/null | grep ':{target_amf_port}' | head -20"
        out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, full, sudo_pw=sudo_pw, timeout=40)
        ran_actions[f"start_{unit}"] = (out + err)[:900]
        if "ESTAB" in out:
            sctp_estab = True
            sctp_lines = [l.strip() for l in out.splitlines() if "ESTAB" in l]
    except Exception as e:
        ran_actions[f"start_{unit}"] = str(e)[:600]
        raise HTTPException(500, f"start_failed: {e}")

    return {
        "status": "connected" if sctp_estab else "started",
        "core": {"amf_ip": target_amf_ip, "amf_port": target_amf_port, "provider": core_provider},
        "ran": {
            "unit": unit,
            "config_path": config_path,
            "amf_addr_set": amf_set,
            "sctp_estab": sctp_estab,
            "sctp_lines": sctp_lines,
            "actions": ran_actions,
        },
        "sctp_estab": sctp_estab,
    }


def disconnect_ran(core_provider: str, ran_provider: str, requested_by: str):
    """Stop unit RAN terpilih. Core (Open5GS systemd) selalu tetap jalan —
    bare-metal single-core tidak perlu discale ke 0 seperti era K8s."""
    if core_provider not in CORE_RAN_MAP:
        raise HTTPException(400, f"Unknown core_provider '{core_provider}'. Valid: {list(CORE_RAN_MAP.keys())}")
    if ran_provider not in RAN_MAP:
        raise HTTPException(400, f"Unknown ran_provider '{ran_provider}'. Valid: {list(RAN_MAP.keys())}")

    ran_info = RAN_MAP[ran_provider]
    ran_host, ran_user, ran_pw, ran_port = _ran_ssh_creds()
    sudo_pw = ran_pw
    unit = ran_info["unit"]
    ran_actions = {}
    try:
        full = f"systemctl stop {unit} 2>&1; echo __CODE__$?"
        out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, full, sudo_pw=sudo_pw, timeout=30)
        ran_actions[f"stop_{unit}"] = (out + err)[:600]
    except Exception as e:
        ran_actions[f"stop_{unit}"] = str(e)[:600]
    try:
        out, err, code = _ssh_exec(
            ran_host, ran_user, ran_pw, ran_port,
            "pkill -9 -f 'apps/gnb/gnb' 2>&1; pkill -9 -x nr-softmodem 2>&1; sleep 1; echo done",
            sudo_pw=sudo_pw, timeout=15,
        )
        ran_actions["pkill"] = (out + err)[:400]
    except Exception as e:
        ran_actions["pkill"] = str(e)[:400]
    try:
        out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, "ss --sctp -an 2>/dev/null | grep ':38412' | head -20", timeout=10)
        sctp_lines = [l.strip() for l in out.splitlines() if l.strip()]
        sctp_estab = "ESTAB" in out
    except Exception:
        sctp_lines = []
        sctp_estab = False

    return {
        "status": "disconnected",
        "core": {"provider": core_provider, "action": "none — Core bare-metal tetap jalan"},
        "ran": {"unit": unit, "sctp_estab": sctp_estab, "sctp_lines": sctp_lines, "actions": ran_actions},
        "sctp_estab": sctp_estab,
    }
