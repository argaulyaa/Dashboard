import asyncio
import json
import time

# load_dotenv() WAJIB dipanggil SEBELUM mengimpor adapters --
# adapters.py membaca env var saat modul di-import, jadi kalau .env
# belum di-load saat itu, env var tidak akan terbaca.
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ssh_proxy import run_ssh_bridge
from adapters import DOMAIN_PROVIDERS
import reservations
from database import get_db_session
from models import AuditLogModel, UserModel
from auth import (
    authenticate, register_user, delete_user, list_registered_users,
    require_user, get_session_info, get_profile, update_full_name, change_password,
    get_user_role, require_engineer, init_auth_data,
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
    # NOTE: no `role` field — self-register is ALWAYS 'viewer' (server-enforced).


class UpdateRoleRequest(BaseModel):
    """Admin-only payload: role baru user ('engineer' | 'viewer')."""
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


@app.post("/api/auth/login")
def login(body: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else ""
    token = authenticate(body.username, body.password, ip=client_ip)
    if not token:
        raise HTTPException(401, "invalid_credentials")
    # Lookup real username (case: user logged in with email)
    from auth import _session_for
    session = _session_for(token)
    real_username = session["user"] if session else body.username
    log_audit(real_username, "LOGIN", ip=client_ip)
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
    log_audit(body.username, "REGISTER_PENDING", detail=f"Email: {body.email}; Role: viewer", ip=client_ip)
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
        detail=f"Email: {user_info['email']}; Role: {user_info.get('role', 'viewer')}",
        ip=client_ip,
    )
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
    """Admin-only: change a user's role between 'engineer' and 'viewer'.

    Pola sama dengan DELETE /api/auth/users/{username}: hanya user 'admin'
    (username atau role admin) yang boleh memanggil. Role akun 'admin'
    sendiri tidak boleh diubah."""
    if current_user != "admin" and get_user_role(current_user) != "admin":
        raise HTTPException(403, "Only admin can change user roles.")
    new_role = body.role.lower().strip()
    if new_role not in ("engineer", "viewer"):
        raise HTTPException(400, "invalid_role: must be 'engineer' or 'viewer'")
    if username == "admin":
        raise HTTPException(403, "cannot_change_admin_role")
    with get_db_session() as db:
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if not user:
            raise HTTPException(404, "user_not_found")
        old_role = user.role or "engineer"
        user.role = new_role
    log_audit(current_user, "ROLE_CHANGE", detail=f"@{username}: {old_role} -> {new_role}")
    return {"ok": True, "username": username, "role": new_role}


@app.get("/api/audit-logs")
def get_audit_logs(current_user: str = Depends(require_user)):
    if current_user != "admin" and get_user_role(current_user) != "admin":
        raise HTTPException(403, "Only admin can view audit logs.")
    with get_db_session() as db:
        logs = db.query(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).limit(100).all()
        return [l.to_dict() for l in logs]


@app.get("/api/auth/session")
def session_info(session: dict = Depends(get_session_info)):
    return {
        "user": session["user"],
        "login_time": session["login_time"] * 1000,
        "ip": session.get("ip", ""),
        "remaining_seconds": max(0, int(session["expires_at"] - time.time())),
    }


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
    if get_user_role(current_user) not in ["engineer", "admin"]:
        raise HTTPException(
            403,
            detail="Viewer role is not allowed to restart components."
        )
    adapter = _get_adapter(domain, provider)
    result = await adapter.restart(comp_id)
    if result is None:
        raise HTTPException(404, f"Unknown component '{comp_id}' in domain '{domain}'")
    log_audit(current_user, "RESTART_COMPONENT", domain=domain, component_id=comp_id)
    return _with_reservation(domain, result)


@app.get("/api/{domain}/components/{comp_id}/logs")
def get_component_logs(domain: str, comp_id: str, provider: str = None, tail: int = 100):
    adapter = _get_adapter(domain, provider)
    if hasattr(adapter, "get_logs"):
        logs = adapter.get_logs(comp_id, tail=tail)
    else:
        logs = f"Logs feature not supported by provider adapter for component '{comp_id}'."
    return {"domain": domain, "component_id": comp_id, "tail": tail, "logs": logs}


# ---- Reservation endpoints (scheduled time-slots) ----

@app.get("/api/reservations/my")
def get_my_reservations(user: str):
    return reservations.my_reservations(user)


@app.get("/api/reservations/all")
def get_all_reservations():
    return reservations.all_reservations()


@app.get("/api/{domain}/components/{comp_id}/reservation")
def get_reservation(domain: str, comp_id: str):
    _get_adapter(domain)  # validates domain, raises 404 if unknown
    return reservations.status(domain, comp_id)


@app.post("/api/{domain}/components/{comp_id}/reservation")
def create_reservation(domain: str, comp_id: str, body: ReserveRequest):
    _get_adapter(domain)
    if get_user_role(body.user) not in ["engineer", "admin"]:
        raise HTTPException(
            403,
            detail={
                "ok": False,
                "reason": "viewer_permission_denied",
                "message": "Viewer role is not allowed to create reservations.",
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
    Pushes a full snapshot of Core/RAN/RIC state every 3s, including
    each component's current reservation status.
    Swap the sleep+jitter loop for a real subscription (e.g. T-Tracer
    stream, E2 indication messages) when you wire this to a live testbed.
    """
    await ws.accept()
    try:
        while True:
            # Live telemetry cuma untuk provider default (pertama terdaftar)
            # di tiap domain -- provider lain diambil manual lewat REST saat
            # tab-nya dipilih di frontend.
            default_adapters = {
                domain: next(iter(providers.values()))["adapter"]
                for domain, providers in DOMAINS.items()
            }
            for adapter in default_adapters.values():
                if random_tick():
                    adapter.jitter_health()

            snapshot = {
                domain: [_with_reservation(domain, c) for c in adapter.list()]
                for domain, adapter in default_adapters.items()
            }
            await ws.send_text(json.dumps(snapshot))
            await asyncio.sleep(3)
    except (WebSocketDisconnect, RuntimeError, ConnectionResetError, Exception):
        pass


def random_tick(p: float = 0.3) -> bool:
    import random
    return random.random() < p


# Run with: uvicorn main:app --reload --port 8000
