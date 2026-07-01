#!/usr/bin/env python3
"""One-off database schema initialisation.

Creates the ``knowledge`` and ``documents`` tables in the database pointed to
by ``DATABASE_URL`` (or the secret referenced by ``SECRET_ARN``). Safe to run
repeatedly -- ``create_all`` is idempotent.

Usage::

    DATABASE_URL="postgresql+psycopg2://user:pass@host:5432/db" \
        python scripts/init_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a standalone script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.database import create_all, get_engine  # noqa: E402
from app.secrets import load_secrets_into_env  # noqa: E402


def main() -> int:
    load_secrets_into_env()
    get_settings.cache_clear()
    settings = get_settings()
    print(f"Initialising schema on: {settings.database_url.split('@')[-1]}")
    create_all(get_engine())
    print("Done. Tables ensured: knowledge, documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
