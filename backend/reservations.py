from __future__ import annotations

"""
Database-backed Scheduled Reservation Manager (PostgreSQL / SQLAlchemy).
- Supports universal overlap check (including self).
- Slots persist permanently across server restarts.
"""

import time
import uuid

from database import get_db_session
from models import ReservationModel


def _check_overlap(domain: str, comp_id: str, start_at: float, end_at: float) -> dict | None:
    """Returns overlapping reservation dict if any exists, else None."""
    now = time.time()
    with get_db_session() as db:
        # Check if any existing reservation overlaps with [start_at, end_at]
        # Overlap condition: (existing.start_at < end_at) AND (existing.end_at > start_at)
        overlapping = (
            db.query(ReservationModel)
            .filter(
                ReservationModel.domain == domain,
                ReservationModel.component_id == comp_id,
                ReservationModel.start_at < end_at,
                ReservationModel.end_at > start_at,
            )
            .first()
        )
        if overlapping:
            return overlapping.to_dict(now)
        return None


def reserve(
    domain: str,
    comp_id: str,
    user: str,
    start_at: float,
    end_at: float,
    note: str = "",
) -> dict:
    """Creates a new scheduled time-slot reservation."""
    now = time.time()
    if start_at >= end_at:
        return {"ok": False, "reason": "invalid_timestamps", "message": "Start time must be before end time."}
    if end_at <= now:
        return {"ok": False, "reason": "past_slot", "message": "End time must be in the future."}

    overlap = _check_overlap(domain, comp_id, start_at, end_at)
    if overlap:
        return {
            "ok": False,
            "reason": "slot_conflict",
            "message": f"Time slot conflicts with an existing reservation by '{overlap['user']}' ({time.strftime('%H:%M', time.localtime(overlap['start_at']))} - {time.strftime('%H:%M', time.localtime(overlap['end_at']))}).",
            "conflict": overlap,
        }

    res_id = f"res-{uuid.uuid4().hex[:8]}"

    with get_db_session() as db:
        record = ReservationModel(
            id=res_id,
            domain=domain,
            component_id=comp_id,
            username=user,
            start_at=start_at,
            end_at=end_at,
            note=note or "",
            created_at=now,
        )
        db.add(record)
        res_dict = record.to_dict(now)

    return {"ok": True, "reservation": res_dict}


def cancel(domain: str, comp_id: str, user: str, reservation_id: str) -> dict:
    """Cancels an existing reservation."""
    with get_db_session() as db:
        res = (
            db.query(ReservationModel)
            .filter(
                ReservationModel.id == reservation_id,
                ReservationModel.domain == domain,
                ReservationModel.component_id == comp_id,
            )
            .first()
        )
        if not res:
            return {"ok": False, "reason": "not_found", "message": "Reservation slot not found."}
        if res.username != user and user != "admin":
            return {"ok": False, "reason": "not_owner", "message": "You can only cancel your own reservation."}

        db.delete(res)

    return {"ok": True, "cancelled": reservation_id}


def get_active_reservation(domain: str, comp_id: str, user: str | None = None) -> dict | None:
    """Returns active reservation if currently active, else None."""
    now = time.time()
    with get_db_session() as db:
        query = db.query(ReservationModel).filter(
            ReservationModel.domain == domain,
            ReservationModel.component_id == comp_id,
            ReservationModel.start_at <= now,
            ReservationModel.end_at > now,
        )
        if user:
            query = query.filter(ReservationModel.username == user)

        active = query.first()
        if active:
            return active.to_dict(now)

    return None


def next_available(domain: str, comp_id: str) -> float:
    """Returns the timestamp when the component will next be completely free."""
    now = time.time()
    with get_db_session() as db:
        upcoming = (
            db.query(ReservationModel)
            .filter(
                ReservationModel.domain == domain,
                ReservationModel.component_id == comp_id,
                ReservationModel.end_at > now,
            )
            .order_by(ReservationModel.end_at.desc())
            .first()
        )
        if upcoming:
            return upcoming.end_at
    return now


def my_reservations(user: str) -> list[dict]:
    """Returns active and upcoming reservations for a user."""
    now = time.time()
    with get_db_session() as db:
        rows = (
            db.query(ReservationModel)
            .filter(
                ReservationModel.username == user,
                ReservationModel.end_at > now,
            )
            .order_by(ReservationModel.start_at.asc())
            .all()
        )
        return [r.to_dict(now) for r in rows]


def all_reservations() -> list[dict]:
    """Returns all active and upcoming reservations in system."""
    now = time.time()
    with get_db_session() as db:
        rows = (
            db.query(ReservationModel)
            .filter(ReservationModel.end_at > now)
            .order_by(ReservationModel.start_at.asc())
            .all()
        )
        return [r.to_dict(now) for r in rows]


def status(domain: str, comp_id: str) -> dict:
    """Returns detailed reservation status for a component."""
    now = time.time()
    with get_db_session() as db:
        rows = (
            db.query(ReservationModel)
            .filter(
                ReservationModel.domain == domain,
                ReservationModel.component_id == comp_id,
                ReservationModel.end_at > now,
            )
            .order_by(ReservationModel.start_at.asc())
            .all()
        )

        all_slots = [r.to_dict(now) for r in rows]
        active = next((s for s in all_slots if s["is_active"]), None)
        upcoming = [s for s in all_slots if s["is_upcoming"]]
        next_free = max([r.end_at for r in rows] + [now])

        return {
            "domain": domain,
            "component_id": comp_id,
            "active": active,
            "upcoming": upcoming,
            "next_available": next_free,
        }
