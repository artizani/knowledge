"""Shared pytest fixtures."""
from __future__ import annotations

import pytest

from app.config import get_settings
from app.service import KnowledgeService
from tests.fake_repository import FakeKnowledgeRepository

TEST_TOKEN = "test-token"
TEST_JWT_SECRET = "jwt-test-secret"


@pytest.fixture(autouse=True)
def configured_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-service-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "fake-anon-key")
    monkeypatch.setenv("API_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def repository():
    return FakeKnowledgeRepository()


@pytest.fixture
def app(repository):
    from app.main import create_app, get_repository

    application = create_app()

    def override_get_repository():
        return repository

    application.dependency_overrides[get_repository] = override_get_repository
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
