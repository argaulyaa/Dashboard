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
from models import UserModel, SessionModel

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
                role="engineer",
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
                                role=entry.get("role", "engineer"),
                                created_at=time.time(),
                            )
                        )
            except Exception as e:
                print(f"[Auth Migration Warning] Could not migrate legacy users: {e}")


def get_user_role(username: str) -> str:
    """Returns 'engineer' or 'viewer'."""
    with get_db_session() as db:
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if user and user.role:
            return user.role
    return "engineer"


def register_user(username: str, password: str, full_name: str = "", role: str = "engineer") -> dict:
    """Creates a new user account in database."""
    username = username.strip()
    if not username:
        raise ValueError("username_required")
    policy_error = _password_policy_error(password)
    if policy_error:
        raise ValueError(policy_error)

    role = role.lower().strip()
    if role not in ["engineer", "viewer"]:
        role = "engineer"

    salt_hex, hash_hex = _hash_password(password)

    with get_db_session() as db:
        existing = db.query(UserModel).filter(UserModel.username == username).first()
        if existing:
            raise ValueError("username_taken")

        user = UserModel(
            username=username,
            full_name=full_name.strip(),
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
                "role": user.role or "engineer",
                "editable": True,
            }
    return {
        "username": username,
        "full_name": "",
        "role": "engineer",
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


def list_registered_users() -> list[dict]:
    """Returns registered user list."""
    with get_db_session() as db:
        users = db.query(UserModel).all()
        return [
            {
                "username": u.username,
                "full_name": u.full_name or "",
                "role": u.role or "engineer",
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
    """Authenticates user credentials and returns session token."""
    with get_db_session() as db:
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if user and _verify_password(password, user.salt, user.hash):
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


def require_engineer(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: validates token AND checks engineer role."""
    username = require_user(authorization)
    role = get_user_role(username)
    if role not in ["engineer", "admin"]:
        raise HTTPException(
            403,
            detail={
                "ok": False,
                "reason": "viewer_permission_denied",
                "message": "Viewer role is not allowed to perform action.",
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