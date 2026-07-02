"""Authentication.

Two token styles are supported, per the spec:

* a static bearer token for internal use (``API_TOKEN``), and
* Auth.js-issued JWTs (``JWT_SECRET`` + ``JWT_ALGORITHMS``).

Either is accepted when both are configured. Mutating endpoints
(``require_write_auth``) are protected whenever ``AUTH_REQUIRED`` is true; read
endpoints are open unless ``REQUIRE_AUTH_FOR_READS`` is set. Failures raise
:class:`app.errors.AuthError`, which the app maps to HTTP 401.
"""
from __future__ import annotations

import hmac

import jwt
from starlette.requests import Request

from app.config import Settings, get_settings
from app.errors import AuthError

Principal = dict


def extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = credentials.strip()
    return token or None


def _verify_jwt(token: str, settings: Settings) -> Principal:
    options: dict = {}
    kwargs: dict = {"algorithms": settings.jwt_algorithms}
    if settings.jwt_audience:
        kwargs["audience"] = settings.jwt_audience
    else:
        options["verify_aud"] = False
    if settings.jwt_issuer:
        kwargs["issuer"] = settings.jwt_issuer
    try:
        claims = jwt.decode(token, settings.jwt_secret, options=options, **kwargs)
    except jwt.PyJWTError as exc:  # expired, bad signature, wrong aud/iss, etc.
        raise AuthError(f"invalid jwt: {exc}") from exc
    return {"sub": claims.get("sub"), "method": "jwt", "claims": claims}


def verify_token(token: str, settings: Settings) -> Principal:
    """Return a principal for ``token`` or raise :class:`AuthError`."""

    for valid in settings.api_tokens:
        if valid and hmac.compare_digest(token, valid):
            return {"sub": "internal", "method": "bearer"}
    if settings.jwt_secret:
        return _verify_jwt(token, settings)
    raise AuthError("invalid token")


def _authenticate(request: Request, settings: Settings) -> Principal:
    token = extract_bearer(request)
    if token is None:
        raise AuthError("missing bearer token")
    return verify_token(token, settings)


def require_write_auth(request: Request) -> Principal:
    """FastAPI dependency protecting mutating endpoints."""

    settings = get_settings()
    if not settings.auth_required:
        return {"sub": "anonymous", "method": "disabled"}
    return _authenticate(request, settings)


def require_read_auth(request: Request) -> Principal:
    """FastAPI dependency for read endpoints (open unless configured)."""

    settings = get_settings()
    if not settings.require_auth_for_reads:
        return {"sub": "anonymous", "method": "open"}
    return _authenticate(request, settings)
