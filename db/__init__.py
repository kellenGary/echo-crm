"""
Echo CRM — Database engine, session factory, and declarative base.

Usage:
    from db import Base, get_engine, get_session

    # FastAPI dependency
    def get_db():
        session = get_session()
        try:
            yield session
        finally:
            session.close()
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


# ---------------------------------------------------------------------------
# Lazy engine / session — only created when actually needed, so importing
# the `db` package (and its models) never requires a live database driver.
# ---------------------------------------------------------------------------

_engine = None
_SessionLocal = None


def get_engine():
    """Return (and cache) the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine
        import config

        _engine = create_engine(
            config.DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            echo=False,
        )
    return _engine


def get_session():
    """Return a new session from the cached session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        from sqlalchemy.orm import sessionmaker
        _SessionLocal = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal()


def init_db() -> None:
    """Create all tables from ORM metadata (dev convenience).

    For production, prefer running ``init_schema.sql`` directly via psql.
    """
    from db import models  # noqa: F401 — ensure models are registered
    Base.metadata.create_all(bind=get_engine())
