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
    # RBAC 2-role: 'user' | 'admin' (nilai legacy dibaca sebagai 'user')
    role = Column(String(32), default="user", nullable=False)
    created_at = Column(Float, default=time.time, nullable=False)

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "full_name": self.full_name or "",
            "email": self.email or "",
            "role": self.role or "user",
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
    # RBAC 2-role: self-register selalu 'user'
    role = Column(String(32), default="user", nullable=False)
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


class ActiveProviderModel(Base):
    """Provider yang sedang AKTIF untuk satu domain (mis. 'core').

    Satu row per domain (primary key = domain), jadi eksklusif: mengaktifkan
    provider lain cukup meng-upsert row ini. Row dihapus saat deactivate,
    sehingga tidak ada provider aktif.
    """
    __tablename__ = "active_providers"

    domain = Column(String(32), primary_key=True, index=True)
    provider = Column(String(64), nullable=False)
    username = Column(String(64), nullable=False)
    activated_at = Column(Float, default=time.time, nullable=False)

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "provider": self.provider,
            "username": self.username,
            "activated_at": self.activated_at,
        }


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


class BookingModel(Base):
    """Reservation booking for Core↔RAN exclusive session.
    One row per booked time slot; only one active booking at a time globally
    (overlap check prevents concurrent gNB/Core chaos).
    status: pending -> active (approved) -> done/cancelled
    """
    __tablename__ = "booking_reservations"

    id = Column(String(64), primary_key=True, index=True)
    user = Column(String(64), nullable=False, index=True)
    core_provider = Column(String(64), nullable=False)
    ran_provider = Column(String(64), nullable=False)
    start_at = Column(Float, nullable=False, index=True)
    end_at = Column(Float, nullable=False, index=True)
    status = Column(String(32), default="pending", nullable=False, index=True)  # pending/active/done/cancelled/rejected
    created_at = Column(Float, default=time.time, nullable=False)

    def to_dict(self, now: float | None = None) -> dict:
        now_ts = now if now is not None else time.time()
        is_active = self.status == "active" and self.start_at <= now_ts < self.end_at
        is_upcoming = self.start_at > now_ts and self.status in ("pending", "active")
        is_expired = now_ts >= self.end_at
        remaining = max(0, int(self.end_at - now_ts)) if is_active else 0
        effective_status = self.status
        if is_expired and effective_status in ("pending", "active"):
            effective_status = "done"
        return {
            "id": self.id,
            "user": self.user,
            "core_provider": self.core_provider,
            "ran_provider": self.ran_provider,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "status": self.status,
            "effective_status": effective_status,
            "created_at": self.created_at,
            "is_active": is_active,
            "is_upcoming": is_upcoming,
            "is_expired": is_expired,
            "remaining_seconds": remaining,
        }

# Backwards-compat alias: spec names this ReservationModel, we keep that name
# pointing to BookingModel for any external import that expects `ReservationModel`
# with booking fields. Component-level reservations remain as ReservationModel class above
# (we alias booking as ReservationBookingModel as well).
ReservationBookingModel = BookingModel
