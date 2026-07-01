"""Application configuration.

Settings are read from environment variables. In AWS the sensitive values
(``DATABASE_URL``, ``API_TOKEN``, ``JWT_SECRET``) are injected from AWS Secrets
Manager -- see :func:`app.secrets.load_secrets_into_env`, which runs at Lambda
cold start and populates the environment before settings are built.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Knowledge API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Database ---------------------------------------------------------------
    # A local SQLite default keeps the app runnable for development and tests.
    # Production points this at the Supabase PostgreSQL pooler.
    database_url: str = Field(default="sqlite+pysqlite:///./knowledge_local.db")

    # Authentication ---------------------------------------------------------
    # Either a static bearer token (internal use) or a JWT secret (Auth.js).
    api_token: str | None = Field(default=None)
    jwt_secret: str | None = Field(default=None)
    jwt_algorithms: list[str] = Field(default_factory=lambda: ["HS256"])
    jwt_audience: str | None = Field(default=None)
    jwt_issuer: str | None = Field(default=None)

    # Whether mutating endpoints require a valid token.
    auth_required: bool = Field(default=True)
    # Whether read endpoints also require a valid token. Spec only mandates
    # protecting writes, so reads are open by default.
    require_auth_for_reads: bool = Field(default=False)

    # Observability ----------------------------------------------------------
    log_level: str = Field(default="INFO")

    # AWS --------------------------------------------------------------------
    secret_arn: str | None = Field(default=None)
    aws_region: str | None = Field(default=None)

    # Query defaults ---------------------------------------------------------
    default_list_limit: int = Field(default=50)
    max_list_limit: int = Field(default=200)


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Call ``get_settings.cache_clear()`` after mutating the environment (mainly
    in tests) to force a rebuild.
    """

    return Settings()
