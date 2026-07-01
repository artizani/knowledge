"""Tests for the database engine/session helpers."""
from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool, StaticPool


def test_sqlite_memory_uses_static_pool():
    from app.database import create_db_engine

    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    assert isinstance(engine.pool, StaticPool)


def test_postgres_url_uses_null_pool():
    from app.database import create_db_engine

    engine = create_db_engine("postgresql+psycopg2://u:p@localhost:5432/db")
    assert isinstance(engine.pool, NullPool)


def test_get_session_yields_and_closes(session_factory, monkeypatch):
    from app import database

    monkeypatch.setattr(database, "get_session_factory", lambda: session_factory)

    gen = database.get_session()
    session = next(gen)
    assert isinstance(session, Session)
    # Exhausting the generator closes the session (finally block).
    for _ in gen:
        pass


def test_reset_engine_clears_globals(monkeypatch):
    from app import database

    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    from app import config

    config.get_settings.cache_clear()

    database.reset_engine()
    engine1 = database.get_engine()
    assert engine1 is database.get_engine()  # cached

    database.reset_engine()
    engine2 = database.get_engine()
    assert engine2 is not engine1  # rebuilt after reset
    database.reset_engine()
    config.get_settings.cache_clear()


def test_create_all_creates_tables():
    from sqlalchemy import create_engine, inspect

    from app.database import create_all

    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_all(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"knowledge", "documents"} <= tables
    engine.dispose()
