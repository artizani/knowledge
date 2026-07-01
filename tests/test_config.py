"""Tests for application configuration/settings."""
from __future__ import annotations

import pytest

from app import config


@pytest.fixture(autouse=True)
def _clear_cache():
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_settings_defaults(monkeypatch):
    for var in ["DATABASE_URL", "API_TOKEN", "JWT_SECRET", "AUTH_REQUIRED"]:
        monkeypatch.delenv(var, raising=False)

    settings = config.Settings()

    assert settings.database_url.startswith("sqlite")
    assert settings.auth_required is True
    assert settings.require_auth_for_reads is False
    assert settings.jwt_algorithms == ["HS256"]
    assert settings.log_level == "INFO"


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@host:5432/db")
    monkeypatch.setenv("API_TOKEN", "secret-token")
    monkeypatch.setenv("JWT_SECRET", "jwt-secret")
    monkeypatch.setenv("AUTH_REQUIRED", "false")

    settings = config.Settings()

    assert settings.database_url == "postgresql+psycopg2://u:p@host:5432/db"
    assert settings.api_token == "secret-token"
    assert settings.jwt_secret == "jwt-secret"
    assert settings.auth_required is False


def test_get_settings_is_cached():
    first = config.get_settings()
    second = config.get_settings()
    assert first is second


def test_get_settings_cache_clear_picks_up_new_env(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "one")
    config.get_settings.cache_clear()
    assert config.get_settings().api_token == "one"

    monkeypatch.setenv("API_TOKEN", "two")
    config.get_settings.cache_clear()
    assert config.get_settings().api_token == "two"
