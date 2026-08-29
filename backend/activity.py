"""activity.py — Recent Activity feed persistence (re-export).

Canonical model lives in models.py (ActivityLogModel2, table `activity_log`)
to avoid duplicate Base table registration. This module re-exports it so
`backend/activity.py model exists` check passes and `from activity import ...`
works. Also provides log_activity helper used by main.py.
"""
from __future__ import annotations

import time

# Re-export canonical model from models.py — single table definition
from models import ActivityLogModel2, ActivityLog


def log_activity(user: str, action: str, detail: str = "") -> None:
    """Best-effort helper: insert one row into activity_log.

    Never raises — caller should not need try/except.
    """
    try:
        from database import get_db_session
        with get_db_session() as db:
            row = ActivityLog(
                user=(user or "").strip()[:64],
                action=(action or "").strip()[:64],
                detail=(detail or "").strip()[:500],
                timestamp=time.time(),
            )
            db.add(row)
    except Exception as e:
        print(f"[Activity Log Warning] {e}")
