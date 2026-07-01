"""AWS Lambda entrypoint for the Knowledge API.

API Gateway (HTTP API) -> Lambda -> Mangum -> FastAPI. Secrets are loaded from
AWS Secrets Manager into the environment at cold start, before settings and the
app are constructed. The module-level ``app``/``handler`` are reused across warm
invocations.
"""
from __future__ import annotations

from mangum import Mangum

from app.config import get_settings
from app.main import create_app
from app.secrets import load_secrets_into_env

# Cold start: populate env from Secrets Manager, then (re)read settings.
load_secrets_into_env()
get_settings.cache_clear()

app = create_app()

# ``lifespan="off"`` because Lambda has no long-running server lifecycle.
handler = Mangum(app, lifespan="off")
