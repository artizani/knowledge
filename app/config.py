"""Application configuration/settings."""
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

    # Supabase ---------------------------------------------------------------
    supabase_url: str | None = Field(default=None)
    supabase_service_role_key: str | None = Field(default=None)
    supabase_anon_key: str | None = Field(default=None)
    supabase_schema: str = Field(default="knowledge")

    # Fallback: direct PostgreSQL (deprecated but kept for local scripts/init).
    database_url: str | None = Field(default=None)

    # Authentication ---------------------------------------------------------
    api_token: str | None = Field(default=None)
    jwt_secret: str | None = Field(default=None)
    jwt_algorithms: list[str] = Field(default_factory=lambda: ["HS256"])
    jwt_audience: str | None = Field(default=None)
    jwt_issuer: str | None = Field(default=None)

    auth_required: bool = Field(default=True)
    require_auth_for_reads: bool = Field(default=False)

    # Observability ----------------------------------------------------------
    log_level: str = Field(default="INFO")

    # AWS --------------------------------------------------------------------
    secret_arn: str | None = Field(default=None)
    aws_region: str | None = Field(default=None)

    # Query defaults ---------------------------------------------------------
    default_list_limit: int = Field(default=50)
    max_list_limit: int = Field(default=200)

    @property
    def rest_base_url(self) -> str | None:
        """Return the Supabase PostgREST base URL, or None if not configured."""

        if not self.supabase_url:
            return None
        return f"{self.supabase_url.rstrip('/')}/rest/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
