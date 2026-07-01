"""Unit tests for authentication (static bearer token and JWT)."""
from __future__ import annotations

import time

import jwt
import pytest
from starlette.requests import Request

from app.config import Settings
from app.errors import AuthError


def make_request(headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": "http", "method": "POST", "path": "/capture", "headers": raw}
    return Request(scope)


# -- extract_bearer --------------------------------------------------------- #
def test_extract_bearer_valid():
    from app.auth import extract_bearer

    assert extract_bearer(make_request({"Authorization": "Bearer abc123"})) == "abc123"


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "abc"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}],
)
def test_extract_bearer_invalid(headers):
    from app.auth import extract_bearer

    assert extract_bearer(make_request(headers)) is None


# -- verify_token: static bearer ------------------------------------------- #
def test_verify_static_token_ok():
    from app.auth import verify_token

    settings = Settings(api_token="s3cr3t", jwt_secret=None)
    principal = verify_token("s3cr3t", settings)
    assert principal["method"] == "bearer"


def test_verify_static_token_wrong():
    from app.auth import verify_token

    settings = Settings(api_token="s3cr3t", jwt_secret=None)
    with pytest.raises(AuthError):
        verify_token("nope", settings)


def test_verify_no_credentials_configured_rejects():
    from app.auth import verify_token

    settings = Settings(api_token=None, jwt_secret=None)
    with pytest.raises(AuthError):
        verify_token("anything", settings)


# -- verify_token: JWT ------------------------------------------------------ #
def test_verify_jwt_ok():
    from app.auth import verify_token

    settings = Settings(jwt_secret="topsecret", api_token=None)
    token = jwt.encode({"sub": "user-1"}, "topsecret", algorithm="HS256")
    principal = verify_token(token, settings)
    assert principal["method"] == "jwt"
    assert principal["sub"] == "user-1"


def test_verify_jwt_wrong_secret():
    from app.auth import verify_token

    settings = Settings(jwt_secret="topsecret", api_token=None)
    token = jwt.encode({"sub": "user-1"}, "different", algorithm="HS256")
    with pytest.raises(AuthError):
        verify_token(token, settings)


def test_verify_jwt_expired():
    from app.auth import verify_token

    settings = Settings(jwt_secret="topsecret", api_token=None)
    token = jwt.encode(
        {"sub": "u", "exp": int(time.time()) - 10}, "topsecret", algorithm="HS256"
    )
    with pytest.raises(AuthError):
        verify_token(token, settings)


def test_verify_jwt_audience_enforced():
    from app.auth import verify_token

    settings = Settings(jwt_secret="s", api_token=None, jwt_audience="knowledge-api")
    good = jwt.encode({"sub": "u", "aud": "knowledge-api"}, "s", algorithm="HS256")
    assert verify_token(good, settings)["sub"] == "u"

    bad = jwt.encode({"sub": "u", "aud": "other"}, "s", algorithm="HS256")
    with pytest.raises(AuthError):
        verify_token(bad, settings)


def test_static_token_and_jwt_both_accepted():
    from app.auth import verify_token

    settings = Settings(api_token="static", jwt_secret="jwtsec")
    assert verify_token("static", settings)["method"] == "bearer"
    token = jwt.encode({"sub": "u"}, "jwtsec", algorithm="HS256")
    assert verify_token(token, settings)["method"] == "jwt"


# -- dependencies ----------------------------------------------------------- #
def _with_env(monkeypatch, **env):
    from app import config

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    config.get_settings.cache_clear()


def test_require_write_auth_disabled_allows(monkeypatch):
    from app import auth, config

    _with_env(monkeypatch, AUTH_REQUIRED="false")
    try:
        principal = auth.require_write_auth(make_request({}))
        assert principal["method"] == "disabled"
    finally:
        config.get_settings.cache_clear()


def test_require_write_auth_missing_token_raises(monkeypatch):
    from app import auth, config

    _with_env(monkeypatch, AUTH_REQUIRED="true", API_TOKEN="tok")
    try:
        with pytest.raises(AuthError):
            auth.require_write_auth(make_request({}))
    finally:
        config.get_settings.cache_clear()


def test_require_write_auth_valid_token(monkeypatch):
    from app import auth, config

    _with_env(monkeypatch, AUTH_REQUIRED="true", API_TOKEN="tok")
    try:
        principal = auth.require_write_auth(make_request({"Authorization": "Bearer tok"}))
        assert principal["method"] == "bearer"
    finally:
        config.get_settings.cache_clear()


def test_require_read_auth_open_by_default(monkeypatch):
    from app import auth, config

    _with_env(monkeypatch, API_TOKEN="tok")
    try:
        principal = auth.require_read_auth(make_request({}))
        assert principal["method"] == "open"
    finally:
        config.get_settings.cache_clear()


def test_require_read_auth_enforced_when_configured(monkeypatch):
    from app import auth, config

    _with_env(monkeypatch, REQUIRE_AUTH_FOR_READS="true", API_TOKEN="tok")
    try:
        with pytest.raises(AuthError):
            auth.require_read_auth(make_request({}))
    finally:
        config.get_settings.cache_clear()
