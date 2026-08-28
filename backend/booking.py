from __future__ import annotations
"""
Booking reservation service for Core↔RAN exclusive sessions.
SESSION-ONLY mode: booking reserves time slot only (user + start_at/end_at).
Provider choice happens later during POST /api/ran/connect within active session.
Single global resource: any overlapping booking (pending/active) is rejected -> 409 Slot taken.
Persistent in oran_dashboard.db via BookingModel (table booking_reservations).
"""
import time
import uuid

from database import get_db_session
from models import BookingModel


VALID_STATUSES = {"pending", "active", "done", "cancelled", "rejected"}

def _overlap_exists(start_at: float, end_at: float, exclude_id: str | None = None) -> dict | None:
    now = time.time()
    with get_db_session() as db:
        q = db.query(BookingModel).filter(
            BookingModel.status.in_(["pending", "active"]),
            BookingModel.start_at < end_at,
            BookingModel.end_at > start_at,
        )
        if exclude_id:
            q = q.filter(BookingModel.id != exclude_id)
        row = q.first()
        if row:
            return row.to_dict(now)
        return None

def book(user: str, start_at: float, end_at: float, core_provider: str | None = None, ran_provider: str | None = None) -> dict:
    """Create booking for time slot only. core_provider/ran_provider ignored if provided (kept for backwards compat, stored as empty)."""
    now = time.time()
    if not user or not user.strip():
        return {"ok": False, "reason": "user_required", "message": "user required"}
    try:
        start_at = float(start_at)
        end_at = float(end_at)
    except Exception:
        return {"ok": False, "reason": "invalid_time", "message": "start_at/end_at must be timestamps"}
    if start_at >= end_at:
        return {"ok": False, "reason": "invalid_range", "message": "start_at must be before end_at"}
    if end_at <= now:
        return {"ok": False, "reason": "past_slot", "message": "end_at must be in the future"}
    if start_at < now - 60:
        # allow slight past start (clock skew) but not too far
        pass

    clash = _overlap_exists(start_at, end_at)
    if clash:
        return {
            "ok": False,
            "reason": "slot_taken",
            "message": f"Slot taken by @{clash['user']} ({time.strftime('%H:%M', time.localtime(clash['start_at']))} - {time.strftime('%H:%M', time.localtime(clash['end_at']))})",
            "conflict": clash,
        }

    bid = f"bk-{uuid.uuid4().hex[:8]}"
    with get_db_session() as db:
        row = BookingModel(
            id=bid,
            user=user.strip(),
            core_provider="",  # session-only: provider chosen later at connect time
            ran_provider="",
            start_at=float(start_at),
            end_at=float(end_at),
            status="pending",
            created_at=now,
        )
        db.add(row)
        data = row.to_dict(now)
    return {"ok": True, "booking": data}


def list_my(user: str) -> list[dict]:
    now = time.time()
    with get_db_session() as db:
        rows = db.query(BookingModel).filter(BookingModel.user == user).order_by(BookingModel.start_at.asc()).all()
        return [r.to_dict(now) for r in rows]


def list_all() -> list[dict]:
    now = time.time()
    with get_db_session() as db:
        rows = db.query(BookingModel).order_by(BookingModel.start_at.asc()).all()
        return [r.to_dict(now) for r in rows]


def list_my_active(user: str) -> dict | None:
    """Helper get_my_active_reservation: return active booking for user at now, else None."""
    now = time.time()
    with get_db_session() as db:
        row = db.query(BookingModel).filter(
            BookingModel.user == user,
            BookingModel.status == "active",
            BookingModel.start_at <= now,
            BookingModel.end_at > now,
        ).first()
        if row:
            return row.to_dict(now)
        return None


def get_my_active_reservation(user: str) -> dict | None:
    return list_my_active(user)

def approve(booking_id: str) -> dict:
    now = time.time()
    with get_db_session() as db:
        row = db.query(BookingModel).filter(BookingModel.id == booking_id).first()
        if not row:
            return {"ok": False, "reason": "not_found", "message": "booking not found"}
        if row.status not in ("pending",):
            return {"ok": False, "reason": "invalid_status", "message": f"cannot approve booking with status {row.status}"}
        # re-check overlap against other active/pending bookings (excluding self)
        clash = None
        q = db.query(BookingModel).filter(
            BookingModel.id != booking_id,
            BookingModel.status.in_(["pending", "active"]),
            BookingModel.start_at < row.end_at,
            BookingModel.end_at > row.start_at,
        ).first()
        if q:
            clash = q.to_dict(now)
            return {"ok": False, "reason": "slot_taken", "message": "would clash with another booking", "conflict": clash}
        row.status = "active"
        data = row.to_dict(now)
    return {"ok": True, "booking": data}

def reject(booking_id: str) -> dict:
    with get_db_session() as db:
        row = db.query(BookingModel).filter(BookingModel.id == booking_id).first()
        if not row:
            return {"ok": False, "reason": "not_found", "message": "booking not found"}
        if row.status not in ("pending", "active"):
            return {"ok": False, "reason": "invalid_status", "message": f"cannot reject booking with status {row.status}"}
        row.status = "cancelled"
        data = row.to_dict(time.time())
    return {"ok": True, "booking": data}

def cancel(booking_id: str, requesting_user: str, is_admin: bool = False) -> dict:
    with get_db_session() as db:
        row = db.query(BookingModel).filter(BookingModel.id == booking_id).first()
        if not row:
            return {"ok": False, "reason": "not_found", "message": "booking not found"}
        if not is_admin and row.user != requesting_user:
            return {"ok": False, "reason": "not_owner", "message": "only owner or admin can cancel"}
        if row.status in ("done", "cancelled", "rejected"):
            return {"ok": False, "reason": "invalid_status", "message": f"already {row.status}"}
        row.status = "cancelled"
        data = row.to_dict(time.time())
    return {"ok": True, "booking": data}

def auto_mark_done() -> int:
    """Opportunistic: mark expired active bookings as done. Returns count changed."""
    now = time.time()
    changed = 0
    with get_db_session() as db:
        rows = db.query(BookingModel).filter(BookingModel.status == "active", BookingModel.end_at <= now).all()
        for r in rows:
            r.status = "done"
            changed += 1
    return changed
