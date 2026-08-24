from __future__ import annotations

"""
Database-backed auth for the O-RAN Dashboard (PostgreSQL / SQLAlchemy).
- Users and sessions are persisted in database tables (UserModel, SessionModel).
- Auto-seeds admin account and migrates legacy registered_users.json accounts.
"""

import hashlib
import json
import os
import secrets
import time
from pathlib import Path

from fastapi import Header, HTTPException

from database import get_db_session, init_db
from models import UserModel, SessionModel, PendingRegistrationModel, PendingPasswordResetModel
from email_service import send_verification_email, send_password_reset_email

# username -> password fallback for initial admin
_DEFAULT_USERS = {"admin": "admin"}

_USERS_FILE = Path(__file__).parent / "registered_users.json"
_PBKDF2_ITERATIONS = 100_000

SESSION_TTL_SECONDS = 8 * 60 * 60  # 8 hours


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return salt.hex(), digest.hex()


def _verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    if not salt_hex or not hash_hex:
        return False
    salt = bytes.fromhex(salt_hex)
    _, computed_hash_hex = _hash_password(password, salt)
    return secrets.compare_digest(computed_hash_hex, hash_hex)


def _password_policy_error(password: str) -> str | None:
    if len(password) < 8:
        return "password_too_short"
    if not any(c.isupper() for c in password):
        return "password_needs_uppercase"
    if not any(c.isdigit() for c in password):
        return "password_needs_digit"
    return None


def cleanup_expired_sessions() -> int:
    """Removes expired session tokens from the database."""
    try:
        with get_db_session() as db:
            deleted_count = db.query(SessionModel).filter(SessionModel.expires_at < time.time()).delete()
            return deleted_count
    except Exception as e:
        print(f"[Session Cleanup Warning] Could not purge expired sessions: {e}")
        return 0


def init_auth_data():
    """Seeds default admin account and imports legacy registered_users.json accounts."""
    init_db()
    cleanup_expired_sessions()
    with get_db_session() as db:
        # Seed default admin if not exists
        admin = db.query(UserModel).filter(UserModel.username == "admin").first()
        if not admin:
            salt_hex, hash_hex = _hash_password("admin")
            admin = UserModel(
                username="admin",
                full_name="System Administrator",
                salt=salt_hex,
                hash=hash_hex,
                role="admin",
                created_at=time.time(),
            )
            db.add(admin)

        # Migrate legacy registered_users.json if present
        if _USERS_FILE.exists():
            try:
                legacy = json.loads(_USERS_FILE.read_text())
                for username, entry in legacy.items():
                    existing = db.query(UserModel).filter(UserModel.username == username).first()
                    if not existing:
                        db.add(
                            UserModel(
                                username=username,
                                full_name=entry.get("full_name", ""),
                                salt=entry.get("salt"),
                                hash=entry.get("hash"),
                                # RBAC 2-role: role legacy apa pun ('engineer',
                                # 'viewer', tak dikenal) dipetakan ke 'user'.
                                role=_normalize_role(entry.get("role")),
                                created_at=time.time(),
                            )
                        )
            except Exception as e:
                print(f"[Auth Migration Warning] Could not migrate legacy users: {e}")


def get_user_role(username: str) -> str:
    """Returns 'user' or 'admin' (RBAC 2-role).

    Lazy migration: nilai legacy ('engineer', 'viewer', null, atau string
    tak dikenal) dibaca sebagai 'user'. Hanya 'admin' yang diperlakukan
    istimewa."""
    with get_db_session() as db:
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if user and user.role:
            return _normalize_role(user.role)
    return "user"


def _normalize_role(role: str | None) -> str:
    """Map role apa pun ke salah satu dari {'user', 'admin'}.

    Konversi 3-role -> 2-role: engineer -> user; viewer -> user;
    unknown/None -> user. Hanya 'admin' yang tetap admin."""
    return "admin" if (role or "").strip().lower() == "admin" else "user"


def _validate_email(email: str) -> bool:
    """Basic email format validation."""
    import re
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))


OTP_TTL_SECONDS = 10 * 60  # 10 menit


def create_pending_registration(
    username: str, password: str, email: str, full_name: str = "", role: str = "user"
) -> str:
    """
    Buat pending registration (belum aktif sampai OTP diverifikasi).
    Kirim OTP ke email via SMTP, lalu return otp_code.
    Raise ValueError jika username/email sudah dipakai atau input tidak valid.
    Raise RuntimeError('email_service_unavailable') jika SMTP tidak
    dikonfigurasi atau pengiriman gagal (FAIL-CLOSED — OTP tidak pernah
    dicetak ke log). Pending registration tetap tersimpan sehingga user bisa
    retry via resend-otp setelah SMTP diperbaiki.

    Security: self-register SELALU menghasilkan role 'user' — parameter
    `role` sengaja DIABAIKAN agar client tidak bisa memilih role sendiri.
    Role hanya bisa diubah oleh admin via PUT /api/auth/users/{username}/role.
    """
    import random

    username = username.strip()
    email = email.strip().lower()

    if not username:
        raise ValueError("username_required")
    if not email or not _validate_email(email):
        raise ValueError("invalid_email")

    policy_error = _password_policy_error(password)
    if policy_error:
        raise ValueError(policy_error)

    # Security: role dari client diabaikan — self-register selalu 'user'.
    role = "user"

    salt_hex, hash_hex = _hash_password(password)
    otp_code = f"{random.randint(0, 999999):06d}"
    otp_expires_at = time.time() + OTP_TTL_SECONDS

    with get_db_session() as db:
        # Cek username dan email tidak duplikat di users table
        if db.query(UserModel).filter(UserModel.username == username).first():
            raise ValueError("username_taken")
        if db.query(UserModel).filter(UserModel.email == email).first():
            raise ValueError("email_taken")

        # Hapus pending lama untuk username/email yang sama (retry register)
        db.query(PendingRegistrationModel).filter(
            (PendingRegistrationModel.username == username) |
            (PendingRegistrationModel.email == email)
        ).delete(synchronize_session=False)

        pending = PendingRegistrationModel(
            username=username,
            email=email,
            full_name=full_name.strip(),
            role=role,
            salt=salt_hex,
            hash=hash_hex,
            otp_code=otp_code,
            otp_expires_at=otp_expires_at,
            created_at=time.time(),
        )
        db.add(pending)

    # Kirim OTP via SMTP. FAIL-CLOSED: kalau SMTP tidak siap, RuntimeError
    # diteruskan ke endpoint -> HTTP 503 (OTP tidak pernah dicetak ke log).
    send_verification_email(email, otp_code, username)
    return otp_code


def verify_registration_otp(username: str, otp_code: str) -> dict:
    """
    Validasi OTP untuk pending registration.
    Jika benar dan belum expired → buat akun di users table → hapus pending row.
    Return dict user info jika sukses.
    Raise ValueError jika OTP salah/expired atau username tidak ditemukan.
    """
    with get_db_session() as db:
        pending = db.query(PendingRegistrationModel).filter(
            PendingRegistrationModel.username == username
        ).first()

        if not pending:
            raise ValueError("pending_not_found")
        if time.time() > pending.otp_expires_at:
            db.delete(pending)
            raise ValueError("otp_expired")
        if not secrets.compare_digest(pending.otp_code, otp_code.strip()):
            raise ValueError("otp_invalid")

        # OTP valid — buat akun
        # Cek sekali lagi kalau-kalau username/email sudah ada (race condition)
        if db.query(UserModel).filter(UserModel.username == pending.username).first():
            db.delete(pending)
            raise ValueError("username_taken")

        user = UserModel(
            username=pending.username,
            full_name=pending.full_name,
            email=pending.email,
            salt=pending.salt,
            hash=pending.hash,
            role=pending.role,
            created_at=time.time(),
        )
        db.add(user)
        db.delete(pending)

    return {"username": username, "email": pending.email, "role": pending.role}


def resend_registration_otp(username: str) -> bool:
    """
    Kirim ulang OTP untuk pending registration.
    Return True jika berhasil, False jika pending tidak ditemukan.
    Raise RuntimeError('email_service_unavailable') jika SMTP tidak
    dikonfigurasi atau pengiriman gagal (FAIL-CLOSED — OTP baru tetap
    tersimpan, user bisa retry).
    """
    import random

    with get_db_session() as db:
        pending = db.query(PendingRegistrationModel).filter(
            PendingRegistrationModel.username == username
        ).first()
        if not pending:
            return False

        # Generate OTP baru
        otp_code = f"{random.randint(0, 999999):06d}"
        pending.otp_code = otp_code
        pending.otp_expires_at = time.time() + OTP_TTL_SECONDS
        pending_email = pending.email  # simpan SEBELUM session ditutup

    # Kirim OTP via SMTP (fail-closed — RuntimeError diteruskan ke endpoint).
    send_verification_email(pending_email, otp_code, username)
    return True


def register_user(username: str, password: str, full_name: str = "", role: str = "user", email: str = "") -> dict:
    """Creates a new user account in database (tanpa email verification — dipakai oleh admin).

    Security: parameter `role` DIABAIKAN (hardcoded 'user') — akun yang
    dibuat lewat jalur ini tidak pernah bisa dapat role 'admin' dari
    client. Role hanya bisa diubah oleh admin via
    PUT /api/auth/users/{username}/role."""
    username = username.strip()
    if not username:
        raise ValueError("username_required")
    policy_error = _password_policy_error(password)
    if policy_error:
        raise ValueError(policy_error)

    # Security: role dari client diabaikan — akun baru selalu 'user'.
    role = "user"

    salt_hex, hash_hex = _hash_password(password)

    with get_db_session() as db:
        existing = db.query(UserModel).filter(UserModel.username == username).first()
        if existing:
            raise ValueError("username_taken")

        user = UserModel(
            username=username,
            full_name=full_name.strip(),
            email=email.strip().lower() if email else None,
            salt=salt_hex,
            hash=hash_hex,
            role=role,
            created_at=time.time(),
        )
        db.add(user)

    return {"username": username, "full_name": full_name, "role": role}


def get_profile(username: str) -> dict:
    """Returns user profile information."""
    with get_db_session() as db:
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if user:
            return {
                "username": user.username,
                "full_name": user.full_name or "",
                "role": _normalize_role(user.role),
                "editable": True,
            }
    return {
        "username": username,
        "full_name": "",
        "role": "user",
        "editable": False,
    }


def update_full_name(username: str, full_name: str) -> dict:
    """Updates display name of user."""
    with get_db_session() as db:
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if not user:
            raise ValueError("user_not_found")
        user.full_name = full_name.strip()
    return get_profile(username)


def change_password(username: str, current_password: str, new_password: str) -> None:
    """Changes user password and invalidates active sessions."""
    policy_error = _password_policy_error(new_password)
    if policy_error:
        raise ValueError(policy_error)

    with get_db_session() as db:
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if not user:
            raise ValueError("user_not_found")
        if not _verify_password(current_password, user.salt, user.hash):
            raise ValueError("current_password_incorrect")

        salt_hex, hash_hex = _hash_password(new_password)
        user.salt = salt_hex
        user.hash = hash_hex

        # Invalidate all active sessions for this user
        db.query(SessionModel).filter(SessionModel.username == username).delete()


# ---- Forgot credentials: password reset via email OTP ----

RESET_TOKEN_TTL_SECONDS = 10 * 60  # reset_token sekali pakai, umur pendek


def request_password_reset(username_or_email: str) -> str:
    """Mulai alur forgot-password: kirim OTP ke email terdaftar.

    Return 'sent' jika OTP dikirim. Raise ValueError('user_not_found') jika
    akun tidak ada ATAU tidak punya email (tidak bisa reset mandiri).
    Raise RuntimeError('email_service_unavailable') jika SMTP gagal/tidak
    dikonfigurasi (fail-closed — OTP tidak pernah dicetak ke log). Row pending
    tetap dibuat sebelum pengiriman sehingga retry/resend bisa dilakukan.

    Anti-enumeration di level HTTP: endpoint memetakan ValueError ini ke
    respons generik, jadi penebak tidak bisa membedakan akun ada/tidak.
    """
    import random

    key = username_or_email.strip()
    if not key:
        raise ValueError("user_not_found")

    with get_db_session() as db:
        # Lookup by username atau email (login juga menerima dua-duanya)
        user = db.query(UserModel).filter(UserModel.username == key).first()
        if not user and "@" in key:
            user = db.query(UserModel).filter(UserModel.email == key.lower()).first()

        if not user or not (user.email or "").strip():
            raise ValueError("user_not_found")

        email = (user.email or "").strip().lower()
        username = user.username

        # Satu permintaan aktif per user; permintaan baru menggantikan yang lama.
        db.query(PendingPasswordResetModel).filter(
            PendingPasswordResetModel.username == username
        ).delete(synchronize_session=False)

        otp_code = f"{random.randint(0, 999999):06d}"
        db.add(PendingPasswordResetModel(
            username=username,
            email=email,
            otp_code=otp_code,
            otp_expires_at=time.time() + OTP_TTL_SECONDS,
            created_at=time.time(),
        ))

    send_password_reset_email(email, otp_code, username)
    return "sent"


def resend_password_reset_otp(username_or_email: str) -> bool:
    """Kirim ulang OTP untuk permintaan reset yang masih pending.
    Return True jika terkirim, False jika tidak ada permintaan pending.
    Fail-closed sama seperti request_password_reset."""
    with get_db_session() as db:
        key = username_or_email.strip()
        row = db.query(PendingPasswordResetModel).filter(
            (PendingPasswordResetModel.username == key)
            | (PendingPasswordResetModel.email == key.lower())
        ).first()
        if not row:
            return False

        import random
        otp_code = f"{random.randint(0, 999999):06d}"
        row.otp_code = otp_code
        row.otp_expires_at = time.time() + OTP_TTL_SECONDS
        row.reset_token = None
        row.reset_token_expires_at = None
        row_email = row.email       # simpan SEBELUM session ditutup
        row_username = row.username  # (hindari DetachedInstanceError)

    send_password_reset_email(row_email, otp_code, row_username)
    return True


def verify_password_reset_otp(username_or_email: str, otp_code: str) -> dict:
    """Validasi OTP reset password. Jika benar & belum expired, issue
    reset_token sekali pakai dan hapus OTP (anti replay).
    Return {'username': ..., 'reset_token': ...}.
    Raise ValueError('pending_not_found'|'otp_expired'|'otp_invalid')."""
    with get_db_session() as db:
        key = username_or_email.strip()
        row = db.query(PendingPasswordResetModel).filter(
            (PendingPasswordResetModel.username == key)
            | (PendingPasswordResetModel.email == key.lower())
        ).first()
        if not row:
            raise ValueError("pending_not_found")
        if time.time() > row.otp_expires_at:
            db.delete(row)
            raise ValueError("otp_expired")
        if not secrets.compare_digest(str(row.otp_code), otp_code.strip()):
            raise ValueError("otp_invalid")

        token = secrets.token_urlsafe(32)
        row.otp_code = ""
        row.reset_token = token
        row.reset_token_expires_at = time.time() + RESET_TOKEN_TTL_SECONDS
        row_username = row.username  # simpan sebelum session ditutup

    return {"username": row_username, "reset_token": token}


def confirm_password_reset(reset_token: str, new_password: str) -> dict:
    """Terapkan password baru menggunakan reset_token sekali pakai.
    Password policy divalidasi, semua sesi aktif user dicabut, dan row pending
    dihapus (token hangus setelah dipakai).
    Return {'username': ...}. Raise ValueError('invalid_reset_token'|policy)."""
    policy_error = _password_policy_error(new_password)
    if policy_error:
        raise ValueError(policy_error)

    with get_db_session() as db:
        row = db.query(PendingPasswordResetModel).filter(
            PendingPasswordResetModel.reset_token == reset_token.strip()
        ).first()
        if (
            not row
            or not row.reset_token
            or time.time() > row.reset_token_expires_at
        ):
            raise ValueError("invalid_reset_token")

        user = db.query(UserModel).filter(UserModel.username == row.username).first()
        if not user:
            db.delete(row)
            raise ValueError("invalid_reset_token")

        salt_hex, hash_hex = _hash_password(new_password)
        user.salt = salt_hex
        user.hash = hash_hex

        # Reset password sukses -> cabut semua sesi aktif si user
        db.query(SessionModel).filter(SessionModel.username == row.username).delete()
        row_username = row.username  # simpan sebelum session ditutup
        db.delete(row)

    return {"username": row_username}


def list_registered_users() -> list[dict]:
    """Returns registered user list."""
    with get_db_session() as db:
        users = db.query(UserModel).all()
        return [
            {
                "username": u.username,
                "full_name": u.full_name or "",
                "role": _normalize_role(u.role),
            }
            for u in users
            if u.username != "admin"
        ]


def delete_user(username: str) -> None:
    """Removes a user account."""
    if username == "admin":
        raise ValueError("cannot_delete_admin")

    with get_db_session() as db:
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if not user:
            raise ValueError("user_not_found")
        db.delete(user)
        db.query(SessionModel).filter(SessionModel.username == username).delete()


def authenticate(username: str, password: str, ip: str = "") -> str | None:
    """Authenticates user credentials and returns session token.
    `username` bisa berupa username atau email address.
    """
    with get_db_session() as db:
        # Coba lookup by username dulu, lalu by email kalau tidak ketemu
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if not user and "@" in username:
            user = db.query(UserModel).filter(UserModel.email == username.strip().lower()).first()
        if user and _verify_password(password, user.salt, user.hash):
            real_username = user.username
            token = secrets.token_urlsafe(32)
            session = SessionModel(
                token=token,
                username=real_username,
                ip=ip,
                login_time=time.time(),
                expires_at=time.time() + SESSION_TTL_SECONDS,
            )
            db.add(session)
            return token

        # Fallback for default admin if not in DB
        if username in _DEFAULT_USERS and secrets.compare_digest(_DEFAULT_USERS[username], password):
            token = secrets.token_urlsafe(32)
            session = SessionModel(
                token=token,
                username=username,
                ip=ip,
                login_time=time.time(),
                expires_at=time.time() + SESSION_TTL_SECONDS,
            )
            db.add(session)
            return token

    return None


def _session_for(token: str) -> dict | None:
    with get_db_session() as db:
        sess = db.query(SessionModel).filter(SessionModel.token == token).first()
        if not sess:
            return None
        if sess.expires_at < time.time():
            db.delete(sess)
            return None
        return sess.to_dict()


def require_user(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: validates Bearer token, returns username."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing_or_invalid_authorization_header")
    token = authorization[7:].strip()
    session = _session_for(token)
    if not session:
        raise HTTPException(401, "invalid_or_expired_token")
    return session["user"]


def require_operator(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: validates token AND checks operator role.

    RBAC 2-role: role 'user' dan 'admin' sama-sama boleh operasi penuh
    (reservasi, Console SSH, Activate/Deactivate provider, restart)."""
    username = require_user(authorization)
    if get_user_role(username) not in ("user", "admin"):
        raise HTTPException(
            403,
            detail={
                "ok": False,
                "reason": "permission_denied",
                "message": "This action requires an operator role (user/admin).",
            },
        )
    return username


def require_admin(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: token valid DAN role harus 'admin'.

    Satu-satunya gate untuk audit log & pengelolaan role akun lain."""
    username = require_user(authorization)
    if get_user_role(username) != "admin":
        raise HTTPException(
            403,
            detail={
                "ok": False,
                "reason": "admin_permission_denied",
                "message": "Only admin can perform this action.",
            },
        )
    return username


def get_session_info(authorization: str = Header(default="")) -> dict:
    """Returns full session dictionary for active profile."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing_or_invalid_authorization_header")
    token = authorization[7:].strip()
    session = _session_for(token)
    if not session:
        raise HTTPException(401, "invalid_or_expired_token")
    session["role"] = get_user_role(session["user"])
    return session