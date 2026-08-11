from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

DEFAULT_PG_URL = "postgresql+pg8000://postgres:postgres@localhost:5432/oran_dashboard"
SQLITE_URL = "sqlite:///./oran_dashboard.db"


def _create_db_engine():
    db_url = os.environ.get("DATABASE_URL", "").strip() or DEFAULT_PG_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
    
    if db_url.startswith("postgresql"):
        try:
            # Quick check if PostgreSQL server is reachable
            test_engine = create_engine(db_url, connect_args={"timeout": 3})
            with test_engine.connect():
                pass
            print(f"[Database] Connected successfully to PostgreSQL ({db_url.split('@')[-1]}).")
            return test_engine
        except Exception as e:
            print(f"[Database Warning] PostgreSQL connection check: {e}")
            print(f"[Database] Falling back to SQLite local database ({SQLITE_URL}).")
            db_url = SQLITE_URL

    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    return create_engine(db_url, connect_args=connect_args)


engine = _create_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db_session() -> Generator:
    """Context manager for SQLAlchemy DB sessions."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db():
    """FastAPI dependency for DB sessions."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Initializes database schema tables."""
    from models import UserModel, ReservationModel, SessionModel, AuditLogModel  # noqa
    Base.metadata.create_all(bind=engine)
