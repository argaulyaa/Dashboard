"""
Hybrid Core↔RAN connect (go live)
POST /api/ran/connect  {core_provider, ran_provider, dry_run?}
GET  /api/ran/status   kubectl get deploy + systemctl is-active + ss sctp
"""
import os, re, time, threading, shlex
import paramiko
from fastapi import HTTPException

CORE_RAN_MAP = {
    "oai": {
        "ns": "5g-core",
        "svc": "oai-amf-ngap",
        "nodeport": 30615,
        "cluster_ip": "10.111.186.249",
        "amf_ip": "10.111.186.249",
        "amf_port": 38412,
        "deployments": ["oai-amf","oai-smf","oai-upf","oai-nrf","oai-ausf","oai-udm","oai-udr"],
    },
    "open5gs-chart": {
        "ns": "open5gs-chart",
        "svc": "open5gs-amf-ngap",
        "nodeport": 32112,
        "cluster_ip": "10.107.241.79",
        "amf_ip": "10.107.241.79",
        "amf_port": 38412,
        "deployments": ["open5gs-amf","open5gs-ausf","open5gs-bsf","open5gs-nrf","open5gs-nssf","open5gs-pcf","open5gs-scp","open5gs-sepp","open5gs-smf","open5gs-udm","open5gs-udr","open5gs-upf"],
    },
    "open5gs": {
        "ns": "open5gs-v2",
        "svc": "open5gs-amf-ngap",
        "nodeport": 30412,
        "cluster_ip": "10.105.242.242",
        "lb_ip": "10.91.2.181",
        "amf_ip": "10.91.2.181",
        "amf_port": 38412,
        "deployments": ["open5gs-amf","open5gs-ausf","open5gs-nrf","open5gs-nssf","open5gs-pcf","open5gs-scp","open5gs-smf","open5gs-udm","open5gs-udr"],
    },
    "open5gs-v2": {
        "ns": "open5gs-v2",
        "svc": "open5gs-amf-ngap",
        "nodeport": 30412,
        "cluster_ip": "10.105.242.242",
        "lb_ip": "10.91.2.181",
        "amf_ip": "10.91.2.181",
        "amf_port": 38412,
        "deployments": ["open5gs-amf","open5gs-ausf","open5gs-nrf","open5gs-nssf","open5gs-pcf","open5gs-scp","open5gs-smf","open5gs-udm","open5gs-udr"],
    },
    "magma": {
        "ns": None,
        "svc": None,
        "nodeport": 0,
        "cluster_ip": "",
        "amf_ip": "",
        "amf_port": 0,
        "deployments": [],
    },
}

RAN_MAP = {
    "oai": {
        "unit": "oai-gnb.service",
        "configs": ["/home/ran/gnb-oai-e2-telmat.conf", "/home/ran/gnb-telmat-51prb-3489.conf", "/home/ran/gnb-oai-flexric-fase3-final.conf"],
        "primary_config": "/home/ran/gnb-oai-e2-telmat.conf",
    },
    "srsran": {
        "unit": "srsgnb.service",
        "config": "/home/ran/gnb_srsran.yml",
    },
}

_RAN_CONNECT_LOCK = threading.Lock()

def _ssh_exec(host, user, password, port, cmd, timeout=25, sudo_pw=None):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
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

def core_status_snapshot():
    master_host = os.environ.get("OAI_K8S_SSH_HOST", "10.91.2.156")
    master_user = os.environ.get("OAI_K8S_SSH_USER", "telmat")
    master_pw = os.environ.get("OAI_K8S_SSH_PASSWORD", os.environ.get("K8S_SUDO_PASSWORD","123"))
    master_port = int(os.environ.get("OAI_K8S_SSH_PORT", "22"))
    sudo_pw = os.environ.get("K8S_SUDO_PASSWORD", master_pw)
    kube = os.environ.get("OAI_K8S_ADMIN_CONF", "/etc/kubernetes/admin.conf")
    res = {}
    for key, info in CORE_RAN_MAP.items():
        ns = info.get("ns")
        if not ns:
            res[key] = {"ns": None, "replicas": 0, "desired": 0, "svc": None, "status": "inactive"}
            continue
        try:
            cmd = f"kubectl --kubeconfig={kube} -n {ns} get deploy -o custom-columns=NAME:.metadata.name,READY:.status.readyReplicas,REPLICAS:.spec.replicas --no-headers 2>&1"
            out, err, code = _ssh_exec(master_host, master_user, master_pw, master_port, cmd, sudo_pw=sudo_pw)
            amf = info["deployments"][0] if info["deployments"] else None
            replicas = 0; ready = 0
            for ln in (out+err).splitlines():
                if amf and amf in ln:
                    parts = ln.split()
                    if len(parts) >= 3:
                        try:
                            ready = int(parts[1]) if parts[1] not in ("<none>","") else 0
                            replicas = int(parts[2]) if parts[2] not in ("<none>","") else 0
                        except:
                            pass
                    break
            res[key] = {"ns": ns, "svc": info.get("svc"), "nodeport": info.get("nodeport"), "cluster_ip": info.get("cluster_ip"), "replicas": replicas, "ready": ready, "status": "active" if replicas>0 else "inactive"}
        except Exception as e:
            res[key] = {"ns": ns, "error": str(e)[:200], "status": "unknown"}
    return res

def ran_status_snapshot():
    ran_host = os.environ.get("OAI_SSH_RAN_HOST", "10.91.2.152")
    ran_user = os.environ.get("OAI_SSH_RAN_USER", "ran")
    ran_pw = os.environ.get("OAI_SSH_RAN_PASSWORD", "telmat123")
    ran_port = int(os.environ.get("OAI_SSH_RAN_PORT", "22"))
    try:
        cmd = (
            "systemctl is-active srsgnb.service 2>&1; echo __S1__; "
            "systemctl is-active oai-gnb.service 2>&1; echo __S2__; "
            "ps -eo args 2>/dev/null | grep -E 'gnb|nr-softmodem' | grep -v grep | head -5; echo __S3__; "
            "sudo ss -Sn 2>/dev/null | grep -E ':38412|:32112|:30615|:30412' | head -20; echo __S4__; "
            "grep -E 'addr:.*10\\.' /home/ran/gnb_srsran.yml 2>/dev/null | head -5; echo __S5__; "
            "grep -E 'amf_ip_address' /home/ran/gnb-oai-e2-telmat.conf 2>/dev/null | head -3; "
            "grep -E 'amf_ip_address' /home/ran/gnb-telmat-51prb-3489.conf 2>/dev/null | head -3; echo __END__"
        )
        out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, cmd, timeout=20)
        def split_marker(txt, m):
            if m in txt:
                a,b = txt.split(m,1)
                return a,b
            return txt,""
        rem = out
        a, rem = split_marker(rem, "__S1__")
        parts = {}
        parts["srs_active"] = a.strip()
        a, rem = split_marker(rem, "__S2__")
        parts["oai_active"] = a.strip()
        a, rem = split_marker(rem, "__S3__")
        parts["ps_raw"] = a.strip()
        a, rem = split_marker(rem, "__S4__")
        parts["sctp_raw"] = a.strip()
        a, rem = split_marker(rem, "__S5__")
        parts["srs_amf_raw"] = a.strip()
        parts["oai_amf_raw"] = rem.split("__END__")[0].strip() if "__END__" in rem else rem.strip()
        sctp_estab = parts["sctp_raw"].count("ESTAB") if parts["sctp_raw"] else 0
        sctp_lines = [l.strip() for l in parts["sctp_raw"].splitlines() if l.strip()]
        return {
            "srsgnb_active": parts["srs_active"].strip(),
            "oai_gnb_active": parts["oai_active"].strip(),
            "ps": parts["ps_raw"][:2000],
            "sctp_estab": sctp_estab,
            "sctp_lines": sctp_lines,
            "srs_amf_raw": parts["srs_amf_raw"],
            "oai_amf_raw": parts["oai_amf_raw"],
            "raw": out[:4000],
        }
    except Exception as e:
        return {"error": str(e)[:500], "sctp_estab": 0, "sctp_lines": []}
