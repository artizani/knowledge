"""Shared pytest fixtures.

Every test runs against an isolated in-memory SQLite database. The FastAPI app
is built via the ``create_app`` factory and its ``get_session`` dependency is
overridden to bind to the test engine.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

TEST_TOKEN = "test-token"
TEST_JWT_SECRET = "jwt-test-secret"


@pytest.fixture
def test_engine():
    from app import models  # noqa: F401 (register mappers)
    from app.database import Base

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def session_factory(test_engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=test_engine, autoflush=False, expire_on_commit=False, future=True
    )


@pytest.fixture
def db_session(session_factory) -> Session:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def configured_env(monkeypatch):
    monkeypatch.setenv("API_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    from app import config

    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.fixture
def app(configured_env, session_factory):
    from app.database import get_session
    from app.main import create_app

    application = create_app()

    def override_get_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_session] = override_get_session
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def sample_capture_payload() -> dict:
    return {
        "namespace": "icebox",
        "title": "Life Weeks",
        "type": "idea",
        "status": "research",
        "documents": [
            {"name": "spec.md", "content": "# Spec..."},
            {"name": "research.md", "content": "# Research..."},
        ],
        "metadata": {"tags": ["consumer", "reflection"], "createdBy": "ChatGPT"},
    }
