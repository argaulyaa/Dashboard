from __future__ import annotations

import time
from sqlalchemy import Column, String, Float, Integer, Text
from database import Base


class UserModel(Base):
    __tablename__ = "users"

    username = Column(String(64), primary_key=True, index=True)
    full_name = Column(String(128), default="", nullable=False)
    email = Column(String(256), nullable=True, index=True, unique=True)
    salt = Column(String(64), nullable=True)
    hash = Column(String(128), nullable=True)
    role = Column(String(32), default="engineer", nullable=False)
    created_at = Column(Float, default=time.time, nullable=False)

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "full_name": self.full_name or "",
            "email": self.email or "",
            "role": self.role or "engineer",
            "editable": True,
        }


class PendingRegistrationModel(Base):
    """Registrasi yang belum diverifikasi via OTP email.
    Row dihapus setelah OTP valid (akun dibuat) atau expired.
    """
    __tablename__ = "pending_registrations"

    username = Column(String(64), primary_key=True, index=True)
    email = Column(String(256), nullable=False, index=True)
    full_name = Column(String(128), default="", nullable=False)
    role = Column(String(32), default="engineer", nullable=False)
    salt = Column(String(64), nullable=False)
    hash = Column(String(128), nullable=False)
    otp_code = Column(String(8), nullable=False)
    otp_expires_at = Column(Float, nullable=False)
    created_at = Column(Float, default=time.time, nullable=False)



class PendingPasswordResetModel(Base):
    """Permintaan reset password (forgot credentials) yang belum diverifikasi
    via OTP email. Alur: user minta reset -> OTP dikirim ke email terdaftar ->
    OTP diverifikasi -> reset_token sekali pakai di-issue -> password baru
    disimpan -> row ini dihapus dan semua session user dicabut.
    """
    __tablename__ = "pending_password_resets"

    username = Column(String(64), primary_key=True, index=True)
    email = Column(String(256), nullable=False, index=True)
    otp_code = Column(String(8), nullable=False)
    otp_expires_at = Column(Float, nullable=False)
    # reset_token sekali pakai, diisi setelah OTP terverifikasi
    reset_token = Column(String(128), nullable=True)
    reset_token_expires_at = Column(Float, nullable=True)
    created_at = Column(Float, default=time.time, nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(String(64), primary_key=True, index=True)
    domain = Column(String(32), nullable=False, index=True)
    component_id = Column(String(64), nullable=False, index=True)
    username = Column(String(64), nullable=False, index=True)
    start_at = Column(Float, nullable=False, index=True)
    end_at = Column(Float, nullable=False, index=True)
    note = Column(Text, default="", nullable=False)
    created_at = Column(Float, default=time.time, nullable=False)

    def to_dict(self, now: float | None = None) -> dict:
        now_ts = now if now is not None else time.time()
        is_active = self.start_at <= now_ts < self.end_at
        is_upcoming = self.start_at > now_ts
        is_expired = now_ts >= self.end_at
        remaining = max(0, int(self.end_at - now_ts)) if is_active else 0

        return {
            "id": self.id,
            "domain": self.domain,
            "component_id": self.component_id,
            "user": self.username,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "note": self.note or "",
            "created_at": self.created_at,
            "is_active": is_active,
            "is_upcoming": is_upcoming,
            "is_expired": is_expired,
            "remaining_seconds": remaining,
        }


class SessionModel(Base):
    __tablename__ = "sessions"

    token = Column(String(128), primary_key=True, index=True)
    username = Column(String(64), nullable=False, index=True)
    ip = Column(String(64), default="", nullable=False)
    login_time = Column(Float, nullable=False)
    expires_at = Column(Float, nullable=False, index=True)

    def to_dict(self, now: float | None = None) -> dict:
        now_ts = now if now is not None else time.time()
        return {
            "token": self.token,
            "user": self.username,
            "ip": self.ip,
            "login_time": self.login_time,
            "expires_at": self.expires_at,
            "remaining_seconds": max(0, int(self.expires_at - now_ts)),
        }


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    domain = Column(String(32), nullable=True)
    component_id = Column(String(64), nullable=True)
    detail = Column(Text, default="")
    ip_address = Column(String(64), default="")
    timestamp = Column(Float, default=time.time, nullable=False, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "action": self.action,
            "domain": self.domain,
            "component_id": self.component_id,
            "detail": self.detail,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp,
        }
