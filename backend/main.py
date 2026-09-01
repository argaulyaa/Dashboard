import asyncio
import json
import os
import time

# load_dotenv() WAJIB dipanggil SEBELUM mengimpor adapters --
# adapters.py membaca env var saat modul di-import, jadi kalau .env
# belum di-load saat itu, env var tidak akan terbaca.
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ssh_proxy import run_ssh_bridge
from adapters import DOMAIN_PROVIDERS, DEFAULT_OAI_K8S_COMPONENT_MAP

# Map untuk open5gs: deployment prefix per component (helm chart open5gs-chart -> open5gs-amf)
# dipakai ws_logs untuk open5gs agar tidak salah pakai prefix oai-amf / ns 5g-core
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
    "mysql": "open5gs-mongodb",
}
import shlex
import threading
import queue as _queue
import reservations
from database import get_db_session
from models import AuditLogModel, UserModel, ActiveProviderModel
from auth import (
    authenticate, register_user, delete_user, list_registered_users,
    require_user, get_session_info, get_profile, update_full_name, change_password,
    get_user_role, require_operator, require_admin, init_auth_data,
    create_pending_registration, verify_registration_otp, resend_registration_otp,
    request_password_reset, resend_password_reset_otp,
    verify_password_reset_otp, confirm_password_reset,
)

# Initialize database tables & seed data
init_auth_data()

app = FastAPI(title="O-RAN Control Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

DOMAINS = DOMAIN_PROVIDERS  # {"core": {"oai": {...}, ...}, "ran": {...}, "ric": {...}}


def log_audit(username: str, action: str, domain: str = None, component_id: str = None, detail: str = "", ip: str = ""):
    """Helper to log security and system audit events to database."""
    try:
        with get_db_session() as db:
            audit = AuditLogModel(
                username=username,
                action=action,
                domain=domain,
                component_id=component_id,
                detail=detail,
                ip_address=ip,
                timestamp=time.time(),
            )
            db.add(audit)
    except Exception as e:
        print(f"[Audit Log Warning] Could not record audit log: {e}")


def log_activity(user: str, action: str, detail: str = ""):
    """Helper for Recent Activity feed (spec activity_log). Persistent helper.

    Spec requires: log_activity(user, action, detail) -> activity_log table
    (id, user, action, detail, timestamp) in oran_dashboard.db.
    Best-effort: never raises.
    """
    try:
        from models import ActivityLogModel2
        with get_db_session() as db:
            row = ActivityLogModel2(
                user=(user or "").strip()[:64],
                action=(action or "").strip()[:64],
                detail=(detail or "").strip()[:500],
                timestamp=time.time(),
            )
            db.add(row)
    except Exception as e:
        print(f"[Activity Log Warning] {e}")


class ReserveRequest(BaseModel):
    user: str
    start_at: float
    end_at: float
    note: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    full_name: str = ""
    username: str
    email: str
    password: str
    # NOTE: no `role` field — self-register is ALWAYS 'user' (server-enforced).


class UpdateRoleRequest(BaseModel):
    """Admin-only payload: role baru user ('user' | 'admin')."""
    role: str


class VerifyOtpRequest(BaseModel):
    username: str
    otp_code: str


class ResendOtpRequest(BaseModel):
    username: str


class ReleaseRequest(BaseModel):
    user: str


class UpdateProfileRequest(BaseModel):
    full_name: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    # Boleh username ATAU email (sama seperti login)
    username: str


class VerifyResetOtpRequest(BaseModel):
    username: str
    otp_code: str


class ResendResetOtpRequest(BaseModel):
    username: str


class ConfirmPasswordResetRequest(BaseModel):
    reset_token: str
    new_password: str
    confirm_password: str


class ActivateProviderRequest(BaseModel):
    """Payload aktivasi provider untuk satu domain (mis. domain='core')."""
    provider: str


def _get_adapter(domain: str, provider: str = None):
    providers = DOMAINS.get(domain)
    if not providers:
        raise HTTPException(404, f"Unknown domain '{domain}'")
    key = provider or next(iter(providers))  # default: provider pertama yang terdaftar
    entry = providers.get(key)
    if not entry:
        raise HTTPException(404, f"Unknown provider '{key}' for domain '{domain}'")
    return entry["adapter"]


def _with_reservation(domain: str, component: dict) -> dict:
    component = dict(component)
    component["reservation"] = reservations.status(domain, component["id"])
    return component


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/{domain}/providers")
def list_providers(domain: str):
    providers = DOMAINS.get(domain)
    if not providers:
        raise HTTPException(404, f"Unknown domain '{domain}'")
    return [
        {"key": key, "label": e["label"], "icon": e["icon"], "desc": e["desc"]}
        for key, e in providers.items()
    ]


# ---- Provider activation (satu provider aktif eksklusif per domain) ----

@app.get("/api/{domain}/active-provider")
def get_active_provider(domain: str, current_user: str = Depends(require_user)):
    """Provider yang sedang aktif untuk domain ini (atau null jika tidak ada)."""
    if domain not in DOMAINS:
        raise HTTPException(404, f"Unknown domain '{domain}'")
    with get_db_session() as db:
        row = db.query(ActiveProviderModel).filter(ActiveProviderModel.domain == domain).first()
        # Baca atribut DI DALAM sesi — akses setelah close -> DetachedInstanceError
        data = row.to_dict() if row else None
    if not data:
        return {"provider": None, "username": None, "activated_at": None}
    return {
        "provider": data["provider"],
        "username": data["username"],
        "activated_at": data["activated_at"],
    }


@app.post("/api/{domain}/activate-provider")
def activate_provider(
    domain: str, body: ActivateProviderRequest, current_user: str = Depends(require_operator)
):
    """Aktifkan satu provider untuk domain ini. User/admin only.

    Eksklusifitas ditégakkan SERVER-SIDE (B1 plan exclusive-core-ran, Fase 1):
    kalau sudah ada provider lain yang aktif di domain yang sama -> HTTP 409
    `provider_active`. Client HARUS deactivate dulu sebelum activate provider
    baru. Re-activate provider yang sama tetap idempotent (200).

    Catatan Fase 1: aktivasi masih bookkeeping DB — tidak menyentuh testbed
    (tidak ada actuation core/RAN; itu Fase 2/3 via B2-B5 dengan env
    ALLOW_DB_ONLY_ACTIVATION sebagai kill-switch semantik akting)."""
    providers = DOMAINS.get(domain)
    if not providers:
        raise HTTPException(404, f"Unknown domain '{domain}'")
    if body.provider not in providers:
        raise HTTPException(400, f"Unknown provider '{body.provider}' for domain '{domain}'")
    # Gate: requires active booking (admin bypass) — frontend also disables button
    is_admin_user = (current_user == "admin" or get_user_role(current_user) == "admin")
    if not is_admin_user:
        import booking as _booking_svc
        if not _booking_svc.get_my_active_reservation(current_user):
            raise HTTPException(403, detail={"reason": "not_in_reservation", "message": "Requires active booking — book a session at /reservations"})
    with get_db_session() as db:
        row = db.query(ActiveProviderModel).filter(ActiveProviderModel.domain == domain).first()
        active_provider = row.provider if row else None
        # B1 — eksklusif server-side: tolak kalau provider LAIN sedang aktif.
        if active_provider and active_provider != body.provider:
            raise HTTPException(
                409,
                detail={
                    "reason": "provider_active",
                    "active": active_provider,
                    "domain": domain,
                    "message": (
                        f"Provider '{active_provider}' masih aktif di domain "
                        f"'{domain}'. Matikan dulu sebelum mengaktifkan "
                        f"'{body.provider}'."),
                },
            )
        now = time.time()
        if row:
            row.provider = body.provider
            row.username = current_user
            row.activated_at = now
        else:
            row = ActiveProviderModel(
                domain=domain,
                provider=body.provider,
                username=current_user,
                activated_at=now,
            )
            db.add(row)
    log_audit(current_user, "PROVIDER_ACTIVATE", domain=domain, detail=body.provider)
    return {
        "ok": True,
        "domain": domain,
        "provider": body.provider,
        "username": current_user,
        "activated_at": time.time(),
    }


@app.post("/api/{domain}/deactivate-provider")
def deactivate_provider(domain: str, current_user: str = Depends(require_operator)):
    """Nonaktifkan provider yang sedang aktif untuk domain ini. User/admin only."""
    if domain not in DOMAINS:
        raise HTTPException(404, f"Unknown domain '{domain}'")
    with get_db_session() as db:
        deleted = (
            db.query(ActiveProviderModel)
            .filter(ActiveProviderModel.domain == domain)
            .delete()
        )
    if not deleted:
        raise HTTPException(404, "no_active_provider")
    log_audit(current_user, "PROVIDER_DEACTIVATE", domain=domain)
    return {"ok": True, "domain": domain}


@app.post("/api/auth/login")
def login(body: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else ""
    token = authenticate(body.username, body.password, ip=client_ip)
    if not token:
        log_activity(body.username, "login_failed", "invalid credentials")
        raise HTTPException(401, "invalid_credentials")
    # Lookup real username (case: user logged in with email)
    from auth import _session_for
    session = _session_for(token)
    real_username = session["user"] if session else body.username
    log_audit(real_username, "LOGIN", ip=client_ip)
    log_activity(real_username, "login", f"{real_username} logged in")
    return {"token": token, "user": real_username, "role": get_user_role(real_username)}


@app.post("/api/auth/register")
def register(body: RegisterRequest, request: Request):
    """Buat pending registration dan kirim OTP ke email. Akun belum aktif sampai OTP diverifikasi."""
    client_ip = request.client.host if request.client else ""
    try:
        create_pending_registration(
            username=body.username,
            password=body.password,
            email=body.email,
            full_name=body.full_name,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        if str(e) == 'email_service_unavailable':
            raise HTTPException(
                503,
                detail={
                    'ok': False,
                    'reason': 'email_service_unavailable',
                    'message': 'Gagal mengirim email verifikasi. Coba lagi nanti.',
                },
            )
        raise
    log_audit(body.username, "REGISTER_PENDING", detail=f"Email: {body.email}; Role: user", ip=client_ip)
    log_activity(body.username, "register", f"{body.username} requested registration")
    return {"ok": True, "username": body.username, "message": "OTP sent to email. Please verify."}


@app.post("/api/auth/verify-email")
def verify_email(body: VerifyOtpRequest, request: Request):
    """Verifikasi OTP. Jika benar, akun dibuat dan token login dikembalikan."""
    client_ip = request.client.host if request.client else ""
    try:
        user_info = verify_registration_otp(body.username, body.otp_code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Login langsung setelah verifikasi berhasil
    from auth import get_db_session
    from models import UserModel, SessionModel
    import secrets as _secrets, time as _time
    from auth import SESSION_TTL_SECONDS
    with get_db_session() as db:
        token = _secrets.token_urlsafe(32)
        db.add(SessionModel(
            token=token,
            username=user_info["username"],
            ip=client_ip,
            login_time=_time.time(),
            expires_at=_time.time() + SESSION_TTL_SECONDS,
        ))
    log_audit(
        body.username,
        "REGISTER_VERIFIED",
        detail=f"Email: {user_info['email']}; Role: {user_info.get('role', 'user')}",
        ip=client_ip,
    )
    log_activity(body.username, "register", f"{body.username} verified email — account created")
    return {"ok": True, "token": token, "user": user_info["username"], "role": user_info["role"]}


@app.post("/api/auth/resend-otp")
def resend_otp(body: ResendOtpRequest, request: Request):
    """Kirim ulang OTP verifikasi."""
    try:
        ok = resend_registration_otp(body.username)
    except RuntimeError as e:
        if str(e) == 'email_service_unavailable':
            raise HTTPException(
                503,
                detail={
                    'ok': False,
                    'reason': 'email_service_unavailable',
                    'message': 'Gagal mengirim email verifikasi. Coba lagi nanti.',
                },
            )
        raise
    if not ok:
        raise HTTPException(404, "pending_not_found")
    return {"ok": True, "message": "OTP resent."}


@app.get("/api/auth/users")
def get_users(current_user: str = Depends(require_user)):
    return list_registered_users()


@app.delete("/api/auth/users/{username}")
def remove_user(username: str, current_user: str = Depends(require_user)):
    if current_user != "admin" and get_user_role(current_user) != "admin":
        raise HTTPException(403, "Only admin can delete user accounts.")
    try:
        delete_user(username)
        log_audit(current_user, "DELETE_USER", detail=f"Deleted user @{username}")
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"deleted": username}


@app.put("/api/auth/users/{username}/role")
def update_user_role(username: str, body: UpdateRoleRequest, current_user: str = Depends(require_user)):
    """Admin-only: change a user's role between 'user' and 'admin'.

    Pola sama dengan DELETE /api/auth/users/{username}: hanya user 'admin'
    (username atau role admin) yang boleh memanggil. Role akun 'admin'
    sendiri tidak boleh diubah."""
    if current_user != "admin" and get_user_role(current_user) != "admin":
        raise HTTPException(403, "Only admin can change user roles.")
    new_role = body.role.lower().strip()
    if new_role not in ("user", "admin"):
        raise HTTPException(400, "invalid_role: must be 'user' or 'admin'")
    if username == "admin":
        raise HTTPException(403, "cannot_change_admin_role")
    with get_db_session() as db:
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if not user:
            raise HTTPException(404, "user_not_found")
        old_role = get_user_role(username)
        user.role = new_role
    log_audit(current_user, "ROLE_CHANGE", detail=f"@{username}: {old_role} -> {new_role}")
    return {"ok": True, "username": username, "role": new_role}


@app.get("/api/audit-logs")
def get_audit_logs(current_user: str = Depends(require_admin)):
    """RBAC 2-role: audit log HANYA bisa dibaca admin (owner decision)."""
    with get_db_session() as db:
        logs = db.query(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).limit(100).all()
        return [l.to_dict() for l in logs]


@app.get("/api/activity/recent")
def get_recent_activity(limit: int = Query(default=5, ge=1, le=20), current_user: str = Depends(require_user)):
    """Recent Activity feed — mixed real events. Spec: GET /api/activity/recent?limit=5 returns last 5-10.

    RBAC: visible to ALL authenticated users (role 'user' & 'admin').
    Jangan ubah ke require_admin — audit-logs (/api/audit-logs) yang admin-only, Recent Activity beda.
    """
    lim = max(1, min(int(limit or 5), 20))
    try:
        from models import ActivityLogModel2
        with get_db_session() as db:
            rows = db.query(ActivityLogModel2).order_by(ActivityLogModel2.timestamp.desc()).limit(lim).all()
            return [r.to_dict() for r in rows]
    except Exception as e:
        print(f"[Activity recent warning] {e}")
        return []


@app.get("/api/auth/session")
def session_info(session: dict = Depends(get_session_info)):
    return {
        "user": session["user"],
        "login_time": session["login_time"] * 1000,
        "ip": session.get("ip", ""),
        "remaining_seconds": max(0, int(session["expires_at"] - time.time())),
    }


@app.get("/api/auth/me")
def me(current_user: str = Depends(require_user)):
    """Current user identity — returns full_name for Overview welcome.
    Fallback logic is frontend-side: full_name if non-empty else username.
    Never returns email as display name."""
    return get_profile(current_user)

@app.get("/api/auth/profile")
def profile(current_user: str = Depends(require_user)):
    return get_profile(current_user)


@app.patch("/api/auth/profile")
def update_profile(body: UpdateProfileRequest, current_user: str = Depends(require_user)):
    try:
        return update_full_name(current_user, body.full_name)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/auth/change-password")
def change_password_endpoint(body: ChangePasswordRequest, current_user: str = Depends(require_user)):
    try:
        change_password(current_user, body.current_password, body.new_password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"changed": True}


@app.post("/api/auth/forgot-password")
def forgot_password(body: ForgotPasswordRequest, request: Request):
    """Langkah 1: user minta reset -> OTP dikirim ke email terdaftar.

    Selalu balas generik (anti user-enumeration): sukses maupun akun tidak
    ditemukan sama-sama dapat pesan yang sama. SMTP bermasalah -> 503
    (fail-closed, OTP tidak pernah dicetak ke log)."""
    client_ip = request.client.host if request.client else ""
    try:
        request_password_reset(body.username)
    except ValueError:
        # Akun tidak ada / tanpa email — tetap jawab generik.
        pass
    except RuntimeError as e:
        if str(e) == 'email_service_unavailable':
            raise HTTPException(
                503,
                detail={
                    'ok': False,
                    'reason': 'email_service_unavailable',
                    'message': 'Gagal mengirim email verifikasi. Coba lagi nanti.',
                },
            )
        raise
    log_audit(body.username.strip(), "FORGOT_PASSWORD_REQUEST", ip=client_ip)
    return {"ok": True, "message": "If the account exists, a reset code has been sent to its email."}


@app.post("/api/auth/forgot-password/resend-otp")
def forgot_password_resend(body: ResendResetOtpRequest, request: Request):
    """Kirim ulang OTP reset password untuk permintaan yang masih pending."""
    try:
        ok = resend_password_reset_otp(body.username)
    except RuntimeError as e:
        if str(e) == 'email_service_unavailable':
            raise HTTPException(
                503,
                detail={
                    'ok': False,
                    'reason': 'email_service_unavailable',
                    'message': 'Gagal mengirim email verifikasi. Coba lagi nanti.',
                },
            )
        raise
    # 404 hanya jika memang tidak ada permintaan pending — bukan sinyal enumerasi.
    if not ok:
        raise HTTPException(404, "pending_not_found")
    return {"ok": True, "message": "OTP resent."}


@app.post("/api/auth/forgot-password/verify-otp")
def forgot_password_verify(body: VerifyResetOtpRequest, request: Request):
    """Langkah 2: verifikasi OTP -> issue reset_token sekali pakai."""
    client_ip = request.client.host if request.client else ""
    try:
        result = verify_password_reset_otp(body.username, body.otp_code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    log_audit(result["username"], "PASSWORD_RESET_OTP_VERIFIED", ip=client_ip)
    return {"ok": True, "reset_token": result["reset_token"], "username": result["username"]}


@app.post("/api/auth/forgot-password/confirm")
def forgot_password_confirm(body: ConfirmPasswordResetRequest, request: Request):
    """Langkah 3: simpan password baru pakai reset_token sekali pakai.

    Form punya 2 field (new + confirm) — dicocokkan di sini juga supaya
    aman walau validasi client dilewati. Semua sesi aktif si user dicabut."""
    client_ip = request.client.host if request.client else ""
    if body.new_password != body.confirm_password:
        raise HTTPException(400, "passwords_do_not_match")
    try:
        result = confirm_password_reset(body.reset_token, body.new_password)
    except ValueError as e:
        status = 400
        raise HTTPException(status, str(e))
    log_audit(
        result["username"], "PASSWORD_RESET_COMPLETED",
        detail="via email OTP self-service", ip=client_ip,
    )
    return {"ok": True, "username": result["username"], "redirect": "/login"}


@app.get("/api/{domain}/components")
def list_components(domain: str, provider: str = None):
    adapter = _get_adapter(domain, provider)
    return [_with_reservation(domain, c) for c in adapter.list()]


@app.post("/api/{domain}/components/{comp_id}/restart")
async def restart_component(
    domain: str, comp_id: str, provider: str = None, authorization: str = Header(default="")
):
    current_user = require_user(authorization)
    if get_user_role(current_user) != "admin" and get_user_role(current_user) != "user":
        raise HTTPException(
            403,
            detail="This action requires an operator role (user/admin)."
        )
    adapter = _get_adapter(domain, provider)
    result = await adapter.restart(comp_id)
    if result is None:
        log_activity(current_user, "restart_failed", f"restart {domain}/{comp_id} not found")
        raise HTTPException(404, f"Unknown component '{comp_id}' in domain '{domain}'")
    log_audit(current_user, "RESTART_COMPONENT", domain=domain, component_id=comp_id)
    log_activity(current_user, "restart", f"{current_user} restarted {domain}/{comp_id}")
    return _with_reservation(domain, result)


@app.get("/api/{domain}/components/{comp_id}/logs")
def get_component_logs(domain: str, comp_id: str, provider: str = None, tail: int = 100):
    adapter = _get_adapter(domain, provider)
    if hasattr(adapter, "get_logs"):
        logs = adapter.get_logs(comp_id, tail=tail)
    else:
        logs = f"Logs feature not supported by provider adapter for component '{comp_id}'."
    return {"domain": domain, "component_id": comp_id, "tail": tail, "logs": logs}


# ---------------------------------------------------------------------------
# LIVE logs streaming via WebSocket (per provider)
# GET /ws/logs/{domain}/{provider}/{compId}?tail=100
# Reuses ssh_proxy pattern but exec kubectl/docker logs -f via SSH to master/core.
# Keeps existing REST for fallback.
# ---------------------------------------------------------------------------
def _sh_quote(s: str) -> str:
    try:
        return shlex.quote(str(s))
    except Exception:
        return "'" + str(s).replace("'", "'\\''") + "'"


@app.websocket("/ws/logs/{domain}/{provider}/{compId}")
async def ws_logs(ws: WebSocket, domain: str, provider: str, compId: str):
    await ws.accept()
    # tail from query
    tail_raw = ws.query_params.get("tail", "100")
    try:
        tail = int(tail_raw)
    except Exception:
        tail = 100
    tail = max(10, min(tail, 2000))

    if domain not in DOMAINS:
        await ws.send_text(f"[error] unknown domain '{domain}'\n")
        await ws.close()
        return
    if provider not in DOMAINS[domain]:
        await ws.send_text(f"[error] unknown provider '{provider}' for domain '{domain}'\n")
        await ws.close()
        return
    try:
        adapter = _get_adapter(domain, provider)
    except HTTPException as e:
        await ws.send_text(f"[error] {e.detail}\n")
        await ws.close()
        return

    # Validate compId exists (soft — still allow streaming attempt for debugging)
    comp = None
    try:
        if hasattr(adapter, "get"):
            comp = adapter.get(compId)
    except Exception:
        comp = None
    if comp is None and hasattr(adapter, "_map"):
        m = getattr(adapter, "_map", {})
        # For k8s adapter _map values may be dict, for docker str
        if isinstance(m, dict) and compId not in m:
            # Check DEFAULT fallback mapping for core oai/open5gs — provider-aware
            _is_known = False
            if domain == "core":
                if provider == "open5gs":
                    _is_known = compId in DEFAULT_OPEN5GS_K8S_COMPONENT_MAP or compId in ("mysql", "ext-dn")
                elif provider == "oai":
                    _is_known = compId in DEFAULT_OAI_K8S_COMPONENT_MAP or compId in ("mysql", "ext-dn")
                else:
                    _is_known = (compId in DEFAULT_OAI_K8S_COMPONENT_MAP or compId in DEFAULT_OPEN5GS_K8S_COMPONENT_MAP or compId in ("mysql", "ext-dn"))
            if domain == "core" and not _is_known:
                await ws.send_text(f"[warn] component '{compId}' not in map, trying anyway...\n")

    # ---- Determine SSH target + log command ----
    ssh_host = ssh_port = ssh_user = ssh_password = sudo_password = None
    kubeconfig = "/etc/kubernetes/admin.conf"
    namespace = "5g-core"
    inner_cmd = None
    mode = None

    if domain == "core" and provider in ("oai", "open5gs", "k8s"):
        # Prefer K8s via master (master holds admin.conf) — provider-aware ns/prefix
        k8s_host = os.environ.get("OAI_K8S_SSH_HOST", "") or os.environ.get("K8S_SSH_HOST", "")
        if not k8s_host:
            k8s_host = "10.91.2.156"
        # Resolve prefix / deploy name per provider
        if provider == "open5gs":
            # open5gs: use dedicated map, never oai-amf
            prefix = DEFAULT_OPEN5GS_K8S_COMPONENT_MAP.get(compId, f"open5gs-{compId}")
            try:
                if hasattr(adapter, "_map") and compId in getattr(adapter, "_map", {}):
                    v = adapter._map[compId]
                    if isinstance(v, dict):
                        prefix = v.get("deploy") or v.get("prefix") or prefix
                    elif isinstance(v, str):
                        # docker container name fallback still maps to k8s deploy if it looks like open5gs-*
                        if v.startswith("open5gs-") or v.startswith("oai-"):
                            # prefer mapped prefix already computed for open5gs
                            pass
                        else:
                            prefix = v
                # open5gs never inherits OAI namespace — use OPEN5GS namespace env
                # priority: OPEN5GS_K8S_NAMESPACE > OPEN5GS_NAMESPACE > open5gs-chart (helm release)
                # do not use OAI_K8S_NAMESPACE for open5gs (bug root)
                if hasattr(adapter, "_namespace"):
                    # only use adapter namespace if it looks like open5gs-*
                    _ns = getattr(adapter, "_namespace")
                    if _ns and "open5gs" in _ns:
                        namespace = _ns
                if hasattr(adapter, "_ns"):
                    _ns2 = getattr(adapter, "_ns")
                    if _ns2 and "open5gs" in _ns2:
                        namespace = _ns2
                # Env overrides — OPEN5GS specific first
                _open5gs_ns = os.environ.get("OPEN5GS_K8S_NAMESPACE", "") or os.environ.get("OPEN5GS_NAMESPACE", "")
                if _open5gs_ns:
                    namespace = _open5gs_ns
                else:
                    # default helm release namespace; distinguish chart vs v2 at runtime in inner_cmd
                    namespace = "open5gs-chart"
                # kubeconfig for open5gs may share admin.conf
                kubeconfig = os.environ.get("OPEN5GS_K8S_ADMIN_CONF", "") or os.environ.get("OAI_K8S_ADMIN_CONF", kubeconfig)
                if hasattr(adapter, "_kubeconfig") and "open5gs" in namespace:
                    kubeconfig = getattr(adapter, "_kubeconfig") or kubeconfig
            except Exception:
                pass
        elif provider == "oai":
            prefix = DEFAULT_OAI_K8S_COMPONENT_MAP.get(compId, compId)
            try:
                if hasattr(adapter, "_map") and compId in getattr(adapter, "_map", {}):
                    v = adapter._map[compId]
                    if isinstance(v, dict):
                        prefix = v.get("deploy") or v.get("prefix") or prefix
                    elif isinstance(v, str):
                        prefix = v
                if hasattr(adapter, "_namespace"):
                    namespace = getattr(adapter, "_namespace") or namespace
                if hasattr(adapter, "_ns"):
                    namespace = getattr(adapter, "_ns") or namespace
                if hasattr(adapter, "_kubeconfig"):
                    kubeconfig = getattr(adapter, "_kubeconfig") or kubeconfig
                namespace = os.environ.get("OAI_K8S_NAMESPACE", namespace)
                kubeconfig = os.environ.get("OAI_K8S_ADMIN_CONF", kubeconfig)
            except Exception:
                pass
        else:  # provider == "k8s"
            prefix = DEFAULT_OAI_K8S_COMPONENT_MAP.get(compId, compId)
            try:
                if hasattr(adapter, "_map") and compId in getattr(adapter, "_map", {}):
                    v = adapter._map[compId]
                    if isinstance(v, dict):
                        prefix = v.get("deploy") or v.get("prefix") or prefix
                    elif isinstance(v, str):
                        prefix = v
                if hasattr(adapter, "_namespace"):
                    namespace = getattr(adapter, "_namespace") or namespace
                if hasattr(adapter, "_ns"):
                    namespace = getattr(adapter, "_ns") or namespace
                if hasattr(adapter, "_kubeconfig"):
                    kubeconfig = getattr(adapter, "_kubeconfig") or kubeconfig
                namespace = os.environ.get("OAI_K8S_NAMESPACE", namespace)
                kubeconfig = os.environ.get("OAI_K8S_ADMIN_CONF", kubeconfig)
                namespace = os.environ.get("K8S_CORE_NAMESPACE", namespace)
                kubeconfig = os.environ.get("K8S_KUBECONFIG", kubeconfig)
            except Exception:
                pass

        ssh_host = k8s_host
        ssh_port = int(os.environ.get("OAI_K8S_SSH_PORT", os.environ.get("K8S_SSH_PORT", "22")) or 22)
        ssh_user = os.environ.get("OAI_K8S_SSH_USER", os.environ.get("K8S_SSH_USER", "telmat")) or "telmat"
        ssh_password = os.environ.get("OAI_K8S_SSH_PASSWORD", os.environ.get("K8S_SSH_PASSWORD", "")) or os.environ.get("K8S_SUDO_PASSWORD", "123")
        sudo_password = os.environ.get("K8S_SUDO_PASSWORD", "") or ssh_password or "123"

        kctl = f"kubectl --kubeconfig={kubeconfig}"
        if provider == "k8s":
            inner_cmd = f"{kctl} -n {namespace} logs -f --tail={tail} --timestamps deployment/{prefix} 2>&1"
        elif provider == "open5gs":
            # open5gs helm chart uses label app.kubernetes.io/name=<compId> (e.g. amf) and deploy open5gs-amf
            # open5gs-v2 legacy uses label app=open5gs-amf
            # need to distinguish ns open5gs-chart vs open5gs-v2 at runtime
            inner_cmd = (
                f"NS={_sh_quote(namespace)}; DEP={_sh_quote(prefix)}; LBL={_sh_quote(compId)}; "
                f"if ! {kctl} -n $NS get deploy $DEP >/dev/null 2>&1; then "
                f"  if {kctl} -n open5gs-v2 get deploy $DEP >/dev/null 2>&1; then NS=open5gs-v2; "
                f"  elif {kctl} -n open5gs get deploy $DEP >/dev/null 2>&1; then NS=open5gs; "
                f"  fi; "
                f"fi; "
                f"pod=$({kctl} -n $NS get pods -l app.kubernetes.io/name=$LBL -o jsonpath='{{{{.items[0].metadata.name}}}}' 2>/dev/null); "
                f"if [ -z \"$pod\" ]; then pod=$({kctl} -n $NS get pods -l app=$DEP -o jsonpath='{{{{.items[0].metadata.name}}}}' 2>/dev/null); fi; "
                f"if [ -z \"$pod\" ]; then pod=$({kctl} -n $NS get pods -l app.kubernetes.io/name=$LBL,app.kubernetes.io/instance=open5gs-chart -o jsonpath='{{{{.items[0].metadata.name}}}}' 2>/dev/null); fi; "
                f"if [ -z \"$pod\" ]; then "
                f"  echo \"[logs] pod not found for app.kubernetes.io/name=$LBL (deploy $DEP) in ns $NS — listing pods:\"; "
                f"  {kctl} -n $NS get pods -o wide --no-headers 2>&1 | head -20; "
                f"  echo \"[hint] trying deployment logs fallback (ns $NS deploy $DEP)...\"; "
                f"  {kctl} -n $NS logs -f --tail={tail} --timestamps deployment/$DEP 2>&1; "
                f"  exit 0; "
                f"fi; "
                f"{kctl} -n $NS logs -f --tail={tail} --timestamps $pod 2>&1"
            )
        else:
            # oai: label app=oai-amf in ns 5g-core
            inner_cmd = (
                f"pod=$({kctl} -n {namespace} get pods -l app={_sh_quote(prefix)} -o jsonpath='{{{{.items[0].metadata.name}}}}' 2>/dev/null); "
                f"if [ -z \"$pod\" ]; then "
                f"  echo \"[logs] pod not found for app={prefix} in ns {namespace} — listing pods:\"; "
                f"  {kctl} -n {namespace} get pods -o wide --no-headers 2>&1 | head -20; "
                f"  echo \"[hint] trying deployment logs fallback...\"; "
                f"  {kctl} -n {namespace} logs -f --tail={tail} --timestamps deployment/{prefix} 2>&1; "
                f"  exit 0; "
                f"fi; "
                f"{kctl} -n {namespace} logs -f --tail={tail} --timestamps $pod 2>&1"
            )
        mode = "k8s"
    elif domain == "core":
        # Legacy docker via SSH to core node
        ssh_host = os.environ.get("OAI_SSH_HOST", "10.91.2.151")
        ssh_port = int(os.environ.get("OAI_SSH_PORT", "22") or 22)
        ssh_user = os.environ.get("OAI_SSH_USER", "core") or "core"
        ssh_password = os.environ.get("OAI_SSH_PASSWORD", "telmat123") or "telmat123"
        sudo_password = ""
        container = compId
        try:
            if hasattr(adapter, "_map") and compId in adapter._map:
                v = adapter._map[compId]
                container = v if isinstance(v, str) else v.get("deploy", compId)
            else:
                raw = os.environ.get("OAI_CORE_CONTAINERS", "")
                if raw:
                    import json as _j
                    m = _j.loads(raw)
                    container = m.get(compId, compId)
        except Exception:
            pass
        inner_cmd = f"docker logs -f --tail {tail} --timestamps {_sh_quote(container)} 2>&1"
        mode = "docker"
    elif domain == "ran":
        ssh_host = os.environ.get("OAI_SSH_RAN_HOST", os.environ.get("SRSRAN_SSH_HOST", "10.91.2.152"))
        ssh_port = int(os.environ.get("OAI_SSH_RAN_PORT", os.environ.get("SRSRAN_SSH_PORT", "22")) or 22)
        ssh_user = os.environ.get("OAI_SSH_RAN_USER", os.environ.get("SRSRAN_SSH_USER", "ran")) or "ran"
        ssh_password = os.environ.get("OAI_SSH_RAN_PASSWORD", os.environ.get("SRSRAN_SSH_PASSWORD", "telmat123")) or "telmat123"
        sudo_password = ""
        log_path = "/home/ran/srsgnb.log"
        try:
            if hasattr(adapter, "_cfg") and isinstance(getattr(adapter, "_cfg"), dict):
                log_path = adapter._cfg.get("log", log_path)
        except Exception:
            pass
        inner_cmd = f"tail -n {tail} -F {_sh_quote(log_path)} 2>&1 || tail -n {tail} -F /home/ran/gnb.log 2>&1 || tail -n {tail} -F /home/ran/*.log 2>&1"
        mode = "ran"
    else:
        # RIC / mock — no live backend, fallback to snapshot via REST (send once and close)
        try:
            if hasattr(adapter, "get_logs"):
                txt = adapter.get_logs(compId, tail=tail)
                await ws.send_text(txt)
        except Exception as e:
            await ws.send_text(f"[error] {e}\n")
        await ws.close()
        return

    # Wrap K8s inner with sudo (admin.conf root-only 600)
    if mode == "k8s" and sudo_password:
        full_cmd = f"echo {_sh_quote(sudo_password)} | sudo -S -p '' bash -c {_sh_quote(inner_cmd)}"
    else:
        full_cmd = inner_cmd

    # ---- SSH connect + stream to WS ----
    client = None
    channel = None
    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # Run connect in thread to avoid blocking event loop
        loop = asyncio.get_running_loop()
        def _connect():
            client.connect(
                hostname=ssh_host,
                port=ssh_port,
                username=ssh_user,
                password=ssh_password,
                timeout=10,
                banner_timeout=10,
                auth_timeout=10,
                allow_agent=False,
                look_for_keys=False,
            )
        await loop.run_in_executor(None, _connect)
        await ws.send_text(f"[connected] streaming {mode} logs for {domain}/{provider}/{compId} tail={tail} via {ssh_host}...\n")
        # Exec command — get channel for streaming
        transport = client.get_transport()
        if transport is None:
            raise RuntimeError("SSH transport not available")
        channel = transport.open_session()
        channel.exec_command(full_cmd)
        # Streaming pump: read from channel and forward to WS
        q: _queue.Queue = _queue.Queue()

        stop_evt = threading.Event()

        def _reader():
            try:
                while not stop_evt.is_set():
                    if channel.exit_status_ready():
                        # drain remaining
                        while channel.recv_ready():
                            data = channel.recv(4096)
                            if data:
                                q.put(data)
                        while channel.recv_stderr_ready():
                            data = channel.recv_stderr(4096)
                            if data:
                                q.put(data)
                        break
                    if channel.recv_ready():
                        data = channel.recv(4096)
                        if data:
                            q.put(data)
                    elif channel.recv_stderr_ready():
                        data = channel.recv_stderr(4096)
                        if data:
                            q.put(data)
                    else:
                        # Avoid busy loop
                        stop_evt.wait(0.05)
                # Signal EOF
                q.put(None)
            except Exception as e:
                q.put(f"\n[reader error] {e}\n".encode())
                q.put(None)

        th = threading.Thread(target=_reader, daemon=True)
        th.start()

        async def _pump():
            last_send = time.time()
            while True:
                try:
                    # Block up to 5s for new log data — on timeout send heartbeat so modal looks alive when NF idle
                    data = await loop.run_in_executor(None, lambda: q.get(timeout=5))
                except _queue.Empty:
                    # No log data in last 5s — heartbeat (only if 5s since last real send)
                    if time.time() - last_send >= 5:
                        try:
                            hb = time.strftime("%H:%M:%S")
                            await ws.send_text(f"· heartbeat {hb} — waiting for new logs...\n")
                            last_send = time.time()
                        except Exception:
                            break
                    continue
                if data is None:
                    break
                try:
                    await ws.send_text(data.decode(errors="replace"))
                    last_send = time.time()
                except Exception:
                    break

        pump_task = asyncio.create_task(_pump())

        # Also handle client close — wait for ws receive or pump done
        try:
            while True:
                # If pump done, break
                if pump_task.done():
                    break
                # Wait for WS message with timeout to detect disconnect
                try:
                    # Use wait_for to periodically check pump
                    msg = await asyncio.wait_for(ws.receive_text(), timeout=0.5)
                    # Client may send ping/close — ignore, but if "close" break
                    if msg.strip().lower() in ("close", "exit", "quit"):
                        break
                except asyncio.TimeoutError:
                    continue
                except (WebSocketDisconnect, RuntimeError):
                    break
        finally:
            stop_evt.set()
            pump_task.cancel()
            try:
                await pump_task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        try:
            await ws.send_text(f"[SSH error] {e}\n")
        except Exception:
            pass
    finally:
        try:
            if channel is not None:
                try:
                    channel.close()
                except Exception:
                    pass
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass


# ---- Booking Reservation endpoints (Core↔RAN exclusive sessions) ----
# New booking system to prevent concurrent gNB/Core chaos. Overlap -> 409 Slot taken.
# Persistent in booking_reservations table (BookingModel).
import booking as booking_svc
from datetime import datetime


class BookRequest(BaseModel):
    start_at: float | str
    end_at: float | str
    # legacy: accepted but ignored (session-only mode, provider chosen at connect time)
    core_provider: str | None = None
    ran_provider: str | None = None


def _parse_ts(v: float | str) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    # try float string
    try:
        return float(s)
    except:
        pass
    # try ISO datetime (from datetime-local)
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.timestamp()
        except:
            continue
    # try fromisoformat
    try:
        dt = datetime.fromisoformat(s)
        return dt.timestamp()
    except:
        raise ValueError(f"invalid time format: {s}")


@app.post("/api/reservations/book")
def book_reservation(body: BookRequest, current_user: str = Depends(require_user)):
    try:
        start_ts = _parse_ts(body.start_at)
        end_ts = _parse_ts(body.end_at)
    except ValueError as e:
        raise HTTPException(400, str(e))
    result = booking_svc.book(current_user, start_ts, end_ts)
    if not result["ok"]:
        log_activity(current_user, "booking_failed", f"book failed: {result.get('reason','unknown')}")
        if result.get("reason") == "slot_taken":
            raise HTTPException(409, detail=result)
        raise HTTPException(400, detail=result)
    log_audit(current_user, "BOOK_RESERVATION", detail=f"{start_ts}->{end_ts}")
    log_activity(current_user, "booking", f"{current_user} booked session {result['booking']['id']}")
    return result["booking"]


@app.get("/api/reservations/my")
def get_my_bookings(current_user: str = Depends(require_user), user: str | None = Query(default=None)):
    # support legacy query ?user= for backwards compat; prefer current_user
    target = user or current_user
    # non-admin can only see own; admin can query any via ?user=
    if target != current_user and get_user_role(current_user) != "admin" and current_user != "admin":
        raise HTTPException(403, "can only view own bookings")
    return booking_svc.list_my(target)


@app.get("/api/reservations/all")
def get_all_bookings(current_user: str = Depends(require_admin)):
    return booking_svc.list_all()


@app.get("/api/reservations/active")
def get_active_booking(current_user: str = Depends(require_user)):
    b = booking_svc.get_my_active_reservation(current_user)
    return {"active": b}


@app.post("/api/reservations/{booking_id}/approve")
def approve_booking(booking_id: str, current_user: str = Depends(require_admin)):
    result = booking_svc.approve(booking_id)
    if not result["ok"]:
        log_activity(current_user, "booking_failed", f"approve {booking_id} failed: {result.get('reason','unknown')}")
        if result.get("reason") == "not_found":
            raise HTTPException(404, detail=result)
        if result.get("reason") == "slot_taken":
            raise HTTPException(409, detail=result)
        raise HTTPException(400, detail=result)
    log_audit(current_user, "APPROVE_BOOKING", detail=f"booking {booking_id}")
    log_activity(current_user, "booking_approved", f"{current_user} approved {booking_id}")
    return result["booking"]


@app.post("/api/reservations/{booking_id}/reject")
def reject_booking(booking_id: str, current_user: str = Depends(require_admin)):
    result = booking_svc.reject(booking_id)
    if not result["ok"]:
        log_activity(current_user, "booking_failed", f"reject {booking_id} failed: {result.get('reason','unknown')}")
        if result.get("reason") == "not_found":
            raise HTTPException(404, detail=result)
        raise HTTPException(400, detail=result)
    log_audit(current_user, "REJECT_BOOKING", detail=f"booking {booking_id}")
    log_activity(current_user, "booking_rejected", f"{current_user} rejected {booking_id}")
    return result["booking"]


@app.post("/api/reservations/{booking_id}/cancel")
def cancel_booking(booking_id: str, current_user: str = Depends(require_user)):
    is_admin = (current_user == "admin" or get_user_role(current_user) == "admin")
    result = booking_svc.cancel(booking_id, current_user, is_admin=is_admin)
    if not result["ok"]:
        log_activity(current_user, "booking_failed", f"cancel {booking_id} failed: {result.get('reason','unknown')}")
        if result.get("reason") == "not_found":
            raise HTTPException(404, detail=result)
        if result.get("reason") == "not_owner":
            raise HTTPException(403, detail=result)
        raise HTTPException(400, detail=result)
    log_audit(current_user, "CANCEL_BOOKING", detail=f"booking {booking_id}")
    log_activity(current_user, "booking_cancelled", f"{current_user} cancelled {booking_id}")
    return result["booking"]


# Legacy component reservation endpoints kept under same /api/reservations/my?user= fallback above
# For direct component queries, use /api/{domain}/components/... endpoints below.
@app.get("/api/reservations/my-legacy")
def get_my_reservations_legacy(user: str):
    return reservations.my_reservations(user)


@app.get("/api/reservations/all-legacy")
def get_all_reservations_legacy():
    return reservations.all_reservations()


@app.get("/api/{domain}/components/{comp_id}/reservation")
def get_reservation(domain: str, comp_id: str):
    _get_adapter(domain)  # validates domain, raises 404 if unknown
    return reservations.status(domain, comp_id)


@app.post("/api/{domain}/components/{comp_id}/reservation")
def create_reservation(domain: str, comp_id: str, body: ReserveRequest):
    _get_adapter(domain)
    if get_user_role(body.user) not in ["user", "admin"]:
        raise HTTPException(
            403,
            detail={
                "ok": False,
                "reason": "permission_denied",
                "message": "This action requires an operator role (user/admin).",
            },
        )
    result = reservations.reserve(
        domain, comp_id, body.user, body.start_at, body.end_at, body.note
    )
    if not result["ok"]:
        raise HTTPException(409, detail=result)
    log_audit(body.user, "CREATE_RESERVATION", domain=domain, component_id=comp_id, detail=f"Note: {body.note}")
    return result["reservation"]


@app.delete("/api/{domain}/components/{comp_id}/reservation/{reservation_id}")
def cancel_reservation(domain: str, comp_id: str, reservation_id: str, user: str):
    _get_adapter(domain)
    result = reservations.cancel(domain, comp_id, user, reservation_id)
    if not result["ok"]:
        raise HTTPException(400, detail=result)
    log_audit(user, "CANCEL_RESERVATION", domain=domain, component_id=comp_id, detail=f"Res ID: {reservation_id}")
    return {"cancelled": True}


# ---------------------------------------------------------------------------
# Hybrid Core↔RAN connect (go live) — Core ns scale + RAN gNB AMF retarget
# ---------------------------------------------------------------------------
from ran_hybrid import CORE_RAN_MAP, RAN_MAP, core_status_snapshot, ran_status_snapshot, _ssh_exec, _RAN_CONNECT_LOCK
import shlex as _shlex

class RanConnectRequest(BaseModel):
    core_provider: str
    ran_provider: str
    dry_run: bool = False

@app.get("/api/ran/status")
def ran_status(current_user: str = Depends(require_user)):
    """GET /api/ran/status -> kubectl get deploy + systemctl is-active + ss sctp."""
    try:
        core = core_status_snapshot()
    except Exception as e:
        raise HTTPException(500, f"core_status_failed: {e}")
    try:
        ran = ran_status_snapshot()
    except Exception as e:
        raise HTTPException(500, f"ran_status_failed: {e}")
    estab = ran.get("sctp_estab", 0) > 0
    # Derive active core provider/ns for UI (selected vs active check)
    active_core_provider = None
    active_ns = None
    try:
        for k, v in core.items():
            if isinstance(v, dict) and (v.get("replicas", 0) > 0 or v.get("status") == "active"):
                active_core_provider = k
                active_ns = v.get("ns") or CORE_RAN_MAP.get(k, {}).get("ns")
                break
    except Exception:
        pass
    return {
        "core": core,
        "ran": ran,
        "sctp_estab": estab,
        "sctp_count": ran.get("sctp_estab", 0),
        "active_core_provider": active_core_provider,
        "active_ns": active_ns,
    }

@app.post("/api/ran/connect")
def ran_connect(body: RanConnectRequest, request: Request, current_user: str = Depends(require_operator)):
    """Hybrid Core<->RAN connect: scale core deploys + retarget RAN gNB AMF + restart unit.
    Gate: only user with active booking session can connect (admin bypass).
    """
    # --- Booking gate ---
    is_admin = (current_user == "admin" or get_user_role(current_user) == "admin")
    if not is_admin:
        active = booking_svc.get_my_active_reservation(current_user)
        if not active:
            raise HTTPException(403, detail={"reason": "not_in_reservation", "message": "Not in reservation session - book a session first"})
    core_provider = (body.core_provider or "").strip()
    ran_provider = (body.ran_provider or "").strip()
    dry_run = bool(body.dry_run)
    if not core_provider or not ran_provider:
        raise HTTPException(400, "core_provider and ran_provider required")
    if core_provider not in CORE_RAN_MAP:
        raise HTTPException(400, f"Unknown core_provider '{core_provider}'. Valid: {list(CORE_RAN_MAP.keys())}")
    if ran_provider not in RAN_MAP:
        raise HTTPException(400, f"Unknown ran_provider '{ran_provider}'. Valid: {list(RAN_MAP.keys())}")
    if not dry_run and not _RAN_CONNECT_LOCK.acquire(blocking=False):
        raise HTTPException(409, "another_connect_in_progress")
    try:
        core_info = CORE_RAN_MAP[core_provider]
        ran_info = RAN_MAP[ran_provider]
        target_amf_ip = core_info.get("amf_ip", "")
        target_amf_port = core_info.get("amf_port", 38412)
        if dry_run:
            return {
                "status": "dry_run",
                "dry_run": True,
                "core": {
                    "requested_provider": core_provider,
                    "active_ns": core_info.get("ns"),
                    "svc": core_info.get("svc"),
                    "nodeport": core_info.get("nodeport"),
                    "cluster_ip": core_info.get("cluster_ip"),
                    "action": f"scale deploys in ns {core_info.get('ns')} to 1, others to 0" if core_info.get("ns") else "scale all cores to 0 (magma)",
                },
                "ran": {
                    "requested_provider": ran_provider,
                    "unit": ran_info.get("unit"),
                    "config_path": ran_info.get("config") or ran_info.get("primary_config"),
                    "configs": ran_info.get("configs") or [ran_info.get("config")],
                    "amf_addr_set": f"{target_amf_ip}:{target_amf_port}" if target_amf_ip else "none (magma)",
                    "action": f"stop both units, sed AMF to {target_amf_ip}:{target_amf_port}, start {ran_info.get('unit')}" if target_amf_ip else f"stop both units (magma, no AMF)",
                },
                "sctp_estab": False,
            }
        master_host = os.environ.get("OAI_K8S_SSH_HOST", "10.91.2.156")
        master_user = os.environ.get("OAI_K8S_SSH_USER", "telmat")
        master_pw = os.environ.get("OAI_K8S_SSH_PASSWORD", os.environ.get("K8S_SUDO_PASSWORD","123"))
        master_port = int(os.environ.get("OAI_K8S_SSH_PORT", "22"))
        sudo_pw = os.environ.get("K8S_SUDO_PASSWORD", master_pw)
        kube = os.environ.get("OAI_K8S_ADMIN_CONF", "/etc/kubernetes/admin.conf")
        scale_results = {}
        for key, info in CORE_RAN_MAP.items():
            ns = info.get("ns")
            if not ns:
                continue
            desired = 1 if key == core_provider else 0
            if core_provider == "magma":
                desired = 0
            deploys = info.get("deployments", [])
            for dep in deploys:
                try:
                    cmd = f"kubectl --kubeconfig={kube} -n {ns} scale deploy {dep} --replicas={desired} 2>&1"
                    out, err, code = _ssh_exec(master_host, master_user, master_pw, master_port, cmd, sudo_pw=sudo_pw)
                    scale_results[f"{ns}/{dep}"] = {"desired": desired, "out": (out+err)[:300], "code": code}
                except Exception as e:
                    scale_results[f"{ns}/{dep}"] = {"desired": desired, "error": str(e)[:300]}
        time.sleep(2)
        ran_host = os.environ.get("OAI_SSH_RAN_HOST", "10.91.2.152")
        ran_user = os.environ.get("OAI_SSH_RAN_USER", "ran")
        ran_pw = os.environ.get("OAI_SSH_RAN_PASSWORD", "telmat123")
        ran_port = int(os.environ.get("OAI_SSH_RAN_PORT", "22"))
        ran_actions = {}
        try:
            for unit in ["srsgnb.service", "oai-gnb.service"]:
                try:
                    full = f"echo {_shlex.quote(ran_pw)} | sudo -S -p '' systemctl stop {unit} 2>&1; echo __CODE__$?"
                    out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, full, timeout=30)
                    ran_actions[f"stop_{unit}"] = (out+err)[:400]
                except Exception as e:
                    ran_actions[f"stop_{unit}"] = str(e)[:400]
            try:
                out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, "pkill -9 -x gnb 2>&1; pkill -9 nr-softmodem 2>&1; sleep 2; echo done", timeout=15)
                ran_actions["pkill"] = (out+err)[:400]
            except Exception as e:
                ran_actions["pkill"] = str(e)[:400]
            amf_set = ""
            if target_amf_ip:
                if ran_provider == "srsran":
                    cfg = ran_info["config"]
                    py = f"python3 -c \"import re, pathlib; p='{cfg}'; t=pathlib.Path(p).read_text(); t=re.sub(r'(amf:\\\\s*\\\\n\\\\s*addr:\\\\s*)[0-9.]+', r'\\\\g<1>{target_amf_ip}', t); t=re.sub(r'(amf:\\\\s*\\\\n\\\\s*addr:[^\\\\n]*\\\\n\\\\s*port:\\\\s*)[0-9]+', r'\\\\g<1>{target_amf_port}', t); pathlib.Path(p).write_text(t); print('srs_ok:'+open(p).read().split('addr:')[1][:60])\" 2>&1"
                    try:
                        out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, py, timeout=15)
                        ran_actions["sed_srsran"] = (out+err)[:600]
                        amf_set = f"{target_amf_ip}:{target_amf_port}"
                    except Exception as e:
                        ran_actions["sed_srsran"] = str(e)[:600]
                        raise HTTPException(500, f"srsran_sed_failed: {e}")
                else:
                    configs = ran_info.get("configs", [ran_info.get("primary_config")])
                    for cfg in configs:
                        sed_cmd = f"sed -i 's/amf_ip_address = ({{ ipv4 = \\\"[^\\\"]*\\\"/amf_ip_address = ({{ ipv4 = \\\"{target_amf_ip}\\\" /' {cfg} 2>&1; echo {cfg}:$?"
                        try:
                            out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, sed_cmd, timeout=15)
                            ran_actions[f"sed_{cfg}"] = (out+err)[:400]
                        except Exception as e:
                            ran_actions[f"sed_{cfg}"] = str(e)[:400]
                    amf_set = target_amf_ip
            else:
                amf_set = "none (magma)"
            sctp_estab = False
            sctp_lines = []
            if target_amf_ip:
                unit = ran_info["unit"]
                try:
                    full = f"echo {_shlex.quote(ran_pw)} | sudo -S -p '' systemctl start {unit} 2>&1; echo __START__$?; sleep 4; sudo ss -Sn 2>/dev/null | grep -E ':38412|:32112|:30615|:30412' | head -20"
                    out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, full, timeout=35)
                    ran_actions[f"start_{unit}"] = (out+err)[:900]
                    if "ESTAB" in out:
                        sctp_estab = True
                        sctp_lines = [l for l in out.splitlines() if "ESTAB" in l]
                except Exception as e:
                    ran_actions[f"start_{unit}"] = str(e)[:600]
                    raise HTTPException(500, f"start_failed: {e}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"ran_connect_failed: {e}")
        try:
            out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, "sudo ss -Sn 2>/dev/null | grep -E ':38412|:32112|:30615|:30412' | head -20", timeout=10)
            sctp_estab = "ESTAB" in out
            sctp_lines = [l.strip() for l in out.splitlines() if l.strip()]
        except:
            pass
        active_ns = core_info.get("ns")
        svc = core_info.get("svc")
        cluster_ip = core_info.get("cluster_ip")
        nodeport = core_info.get("nodeport")
        try:
            with get_db_session() as db:
                row = db.query(ActiveProviderModel).filter(ActiveProviderModel.domain=="core").first()
                if row:
                    row.provider = core_provider if core_provider != "magma" else row.provider
                    row.username = current_user
                    row.activated_at = time.time()
                else:
                    if core_provider != "magma":
                        db.add(ActiveProviderModel(domain="core", provider=core_provider, username=current_user, activated_at=time.time()))
            # also set ran active provider
            with get_db_session() as db:
                row2 = db.query(ActiveProviderModel).filter(ActiveProviderModel.domain=="ran").first()
                if row2:
                    row2.provider = ran_provider
                    row2.username = current_user
                    row2.activated_at = time.time()
                else:
                    db.add(ActiveProviderModel(domain="ran", provider=ran_provider, username=current_user, activated_at=time.time()))
        except Exception:
            pass
        try:
            log_audit(current_user, "RAN_CONNECT", domain="ran", detail=f"core={core_provider} ran={ran_provider} amf={amf_set}")
        except:
            pass
        try:
            log_activity(current_user, "connect", f"{current_user} connected {core_provider} ↔ {ran_provider} ({amf_set})")
        except:
            pass
        return {
            "status": "connected" if sctp_estab else "started",
            "core": {
                "active_ns": active_ns,
                "svc": svc,
                "cluster_ip": cluster_ip,
                "nodeport": nodeport,
                "scale_results": scale_results,
            },
            "ran": {
                "unit": ran_info.get("unit"),
                "config_path": ran_info.get("config") or ran_info.get("primary_config"),
                "amf_addr_set": amf_set,
                "sctp_estab": sctp_estab,
                "sctp_lines": sctp_lines,
                "actions": ran_actions,
            },
            "sctp_estab": sctp_estab,
        }
    finally:
        if not dry_run:
            try:
                _RAN_CONNECT_LOCK.release()
            except:
                pass

@app.post("/api/ran/disconnect")
def ran_disconnect(body: RanConnectRequest, request: Request, current_user: str = Depends(require_operator)):
    """Hybrid Core<->RAN disconnect: scale target Core to 0 + stop RAN unit.
    Gate: only user with active booking session can disconnect (admin bypass).
    """
    is_admin = (current_user == "admin" or get_user_role(current_user) == "admin")
    if not is_admin:
        active = booking_svc.get_my_active_reservation(current_user)
        if not active:
            raise HTTPException(403, detail={"reason": "not_in_reservation", "message": "Not in reservation session"})
    core_provider = (body.core_provider or "").strip()
    ran_provider = (body.ran_provider or "").strip()
    if not core_provider or not ran_provider:
        raise HTTPException(400, "core_provider and ran_provider required")
    if core_provider not in CORE_RAN_MAP:
        raise HTTPException(400, f"Unknown core_provider '{core_provider}'. Valid: {list(CORE_RAN_MAP.keys())}")
    if ran_provider not in RAN_MAP:
        raise HTTPException(400, f"Unknown ran_provider '{ran_provider}'. Valid: {list(RAN_MAP.keys())}")
    if not _RAN_CONNECT_LOCK.acquire(blocking=False):
        raise HTTPException(409, "another_connect_in_progress")
    try:
        core_info = CORE_RAN_MAP[core_provider]
        ran_info = RAN_MAP[ran_provider]
        master_host = os.environ.get("OAI_K8S_SSH_HOST", "10.91.2.156")
        master_user = os.environ.get("OAI_K8S_SSH_USER", "telmat")
        master_pw = os.environ.get("OAI_K8S_SSH_PASSWORD", os.environ.get("K8S_SUDO_PASSWORD","123"))
        master_port = int(os.environ.get("OAI_K8S_SSH_PORT", "22"))
        sudo_pw = os.environ.get("K8S_SUDO_PASSWORD", master_pw)
        kube = os.environ.get("OAI_K8S_ADMIN_CONF", "/etc/kubernetes/admin.conf")
        scale_results = {}
        ns = core_info.get("ns")
        if ns:
            for dep in core_info.get("deployments", []):
                try:
                    cmd = f"kubectl --kubeconfig={kube} -n {ns} scale deploy {dep} --replicas=0 2>&1"
                    out, err, code = _ssh_exec(master_host, master_user, master_pw, master_port, cmd, sudo_pw=sudo_pw)
                    scale_results[f"{ns}/{dep}"] = {"desired": 0, "out": (out+err)[:300], "code": code}
                except Exception as e:
                    scale_results[f"{ns}/{dep}"] = {"desired": 0, "error": str(e)[:300]}
            time.sleep(1)
        ran_host = os.environ.get("OAI_SSH_RAN_HOST", "10.91.2.152")
        ran_user = os.environ.get("OAI_SSH_RAN_USER", "ran")
        ran_pw = os.environ.get("OAI_SSH_RAN_PASSWORD", "telmat123")
        ran_port = int(os.environ.get("OAI_SSH_RAN_PORT", "22"))
        ran_actions = {}
        unit = ran_info.get("unit")
        try:
            full = f"echo {_shlex.quote(ran_pw)} | sudo -S -p '' systemctl stop {unit} 2>&1; echo __CODE__$?"
            out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, full, timeout=30)
            ran_actions[f"stop_{unit}"] = (out+err)[:600]
        except Exception as e:
            ran_actions[f"stop_{unit}"] = str(e)[:600]
        try:
            out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, "pkill -9 -x gnb 2>&1; pkill -9 nr-softmodem 2>&1; sleep 1; echo done", timeout=15)
            ran_actions["pkill"] = (out+err)[:400]
        except Exception as e:
            ran_actions["pkill"] = str(e)[:400]
        try:
            out, err, code = _ssh_exec(ran_host, ran_user, ran_pw, ran_port, "sudo ss -Sn 2>/dev/null | grep -E ':38412|:32112|:30615|:30412' | head -20", timeout=10)
            sctp_lines = [l.strip() for l in out.splitlines() if l.strip()]
            sctp_estab = "ESTAB" in out
        except:
            sctp_lines = []
            sctp_estab = False
        active_ns = core_info.get("ns")
        svc = core_info.get("svc")
        cluster_ip = core_info.get("cluster_ip")
        nodeport = core_info.get("nodeport")
        try:
            log_audit(current_user, "RAN_DISCONNECT", domain="ran", detail=f"core={core_provider} ran={ran_provider} unit={unit}")
        except:
            pass
        try:
            log_activity(current_user, "connect", f"{current_user} disconnected {core_provider} ↔ {ran_provider}")
        except:
            pass
        return {
            "status": "disconnected",
            "core": {
                "active_ns": active_ns,
                "svc": svc,
                "cluster_ip": cluster_ip,
                "nodeport": nodeport,
                "scale_results": scale_results,
            },
            "ran": {
                "unit": unit,
                "sctp_estab": sctp_estab,
                "sctp_lines": sctp_lines,
                "actions": ran_actions,
            },
            "sctp_estab": sctp_estab,
        }
    finally:
        try:
            _RAN_CONNECT_LOCK.release()
        except:
            pass

@app.websocket("/ws/ssh/{domain}/{comp_id}")
async def ssh_ws(ws: WebSocket, domain: str, comp_id: str):
    await ws.accept()

    if domain not in DOMAINS:
        await ws.send_text(f"\r\n[unknown domain '{domain}']\r\n")
        await ws.close()
        return

    try:
        adapter = _get_adapter(domain)  # default provider
    except HTTPException:
        await ws.send_text(f"\r\n[domain '{domain}' has no adapter]\r\n")
        await ws.close()
        return

    component = adapter.get(comp_id)
    if not component or not component.get("host"):
        await ws.send_text("\r\n[component has no SSH host configured]\r\n")
        await ws.close()
        return

    try:
        init_raw = await ws.receive_text()
        init = json.loads(init_raw)
    except Exception:
        await ws.send_text("\r\n[invalid initial payload]\r\n")
        await ws.close()
        return

    dashboard_user = init.get("user", "")
    active_reservation = reservations.get_active_reservation(domain, comp_id, dashboard_user)
    if not active_reservation:
        await ws.send_text(
            "\r\n[access denied: no active reservation found for your user during the current time slot.]\r\n"
        )
        await ws.close()
        return

    await run_ssh_bridge(
        ws,
        host=component["host"],
        port=int(init.get("port", 22)),
        username=init.get("ssh_username", ""),
        password=init.get("ssh_password", ""),
    )

# ---- Telemetry ----

@app.websocket("/ws/telemetry")
async def telemetry_ws(ws: WebSocket):
    """
    Pushes a full snapshot of Core/RAN/RIC state every 3s (payload v2):

        {
          "meta": {
            "ts": <epoch>,
            "active":   {"core": "oai"|null, "ran": null, "ric": null},
            "bindings": {}          # diisi Fase 3 (B4 ran_core_bindings)
          },
          "domains": {"core": [...], "ran": [...], "ric": [...]}
        }

    B6 (plan exclusive-core-ran, Fase 1): domain yang di-stream adalah
    provider AKTIF per domain (tabel active_providers), bukan selalu
    provider pertama. Kalau domain belum punya provider aktif -> fallback
    provider default (pertama terdaftar). Frontend menormalkan payload
    lama {domain: [...]} DAN v2 via api.js::normalizeSnapshot.
    Reservation overlay & random jitter (efektif hanya di adapter mock)
    perilakunya tidak berubah. ALLOW_DB_ONLY_ACTIVATION semantics:
    endpoint ini murni READ — tidak pernah mengaktifkan apa pun.
    """
    await ws.accept()
    try:
        while True:
            # Provider aktif per-domain dari DB (query murah, sekali per tick)
            active_map = {}
            try:
                with get_db_session() as db:
                    rows = db.query(ActiveProviderModel).all()
                    active_map = {r.domain: r.provider for r in rows}
            except Exception:
                active_map = {}  # DB bermasalah -> fallback default providers

            streamed = {}
            for domain, providers in DOMAINS.items():
                key = active_map.get(domain)
                entry = providers.get(key) if key else None
                if entry is None:
                    entry = next(iter(providers.values()))
                adapter = entry["adapter"]
                if random_tick():
                    adapter.jitter_health()  # no-op untuk adapter nyata
                streamed[domain] = adapter

            snapshot = {
                "meta": {
                    "ts": time.time(),
                    "active": {d: active_map.get(d) for d in DOMAINS},
                    "bindings": {},  # B4/Fase 3: isi dari ran_core_bindings
                },
                "domains": {
                    domain: [_with_reservation(domain, c) for c in adapter.list()]
                    for domain, adapter in streamed.items()
                },
            }
            await ws.send_text(json.dumps(snapshot))
            await asyncio.sleep(3)
    except (WebSocketDisconnect, RuntimeError, ConnectionResetError, Exception):
        pass


def random_tick(p: float = 0.3) -> bool:
    import random
    return random.random() < p


# Run with: uvicorn main:app --reload --port 8000
