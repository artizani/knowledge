"""Database engine and session management.

Uses SQLAlchemy 2.0. The engine is created lazily from :mod:`app.config` so
that tests can override ``DATABASE_URL`` before the first connection.

In AWS Lambda the module-level engine is reused across warm invocations. For
serverless PostgreSQL (Supabase pooler) we disable SQLAlchemy's own pooling
(``NullPool``) and let the external pooler manage connections, while
``pool_pre_ping`` guards against dropped connections.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def create_db_engine(url: str, **kwargs) -> Engine:
    """Create an :class:`~sqlalchemy.Engine` tuned for the target dialect."""

    connect_args: dict = {}
    engine_kwargs: dict = {"future": True, "pool_pre_ping": True}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # An in-memory SQLite DB must share a single connection to persist
        # across sessions within a test.
        if ":memory:" in url or "mode=memory" in url:
            engine_kwargs["poolclass"] = StaticPool
    else:
        # Serverless: rely on the external (pgbouncer/Supavisor) pooler.
        engine_kwargs["poolclass"] = NullPool

    engine_kwargs.update(kwargs)
    return create_engine(url, connect_args=connect_args, **engine_kwargs)


# Lazily-initialised module globals (reused across warm Lambda invocations).
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_db_engine(get_settings().database_url)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False, future=True
        )
    return _SessionLocal


def reset_engine() -> None:
    """Dispose and clear the cached engine/session factory (used by tests)."""

    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a transactional session."""

    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def create_all(engine: Engine | None = None) -> None:
    """Create all tables (idempotent). Used for first-time schema setup.

    Imports the models module so every table is registered on ``Base.metadata``
    before the DDL is emitted.
    """

    import app.models  # noqa: F401 (register mappers/tables)

    Base.metadata.create_all(engine or get_engine())
