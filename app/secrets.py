"""Load secrets from AWS Secrets Manager into the process environment.

Called once at Lambda cold start (see :mod:`handler`). The secret is a JSON
object whose keys become environment variables (upper-cased), e.g.::

    {"database_url": "...", "api_token": "...", "jwt_secret": "..."}

Existing environment variables are never overwritten, so local development and
tests can override any value.
"""
from __future__ import annotations

import json
import os
from typing import Any, MutableMapping


def _default_client(region: str | None):  # pragma: no cover - thin boto3 wrapper
    import boto3

    return boto3.client("secretsmanager", region_name=region)


def load_secrets_into_env(
    secret_arn: str | None = None,
    region: str | None = None,
    client: Any | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> bool:
    """Fetch the secret and merge it into ``environ``.

    Returns ``True`` when values were loaded, ``False`` when there is no secret
    to load (no ARN configured or an empty secret).
    """

    environ = os.environ if environ is None else environ
    secret_arn = secret_arn or environ.get("SECRET_ARN")
    if not secret_arn:
        return False

    if client is None:  # pragma: no cover - exercised only in AWS
        client = _default_client(region or environ.get("AWS_REGION"))

    response = client.get_secret_value(SecretId=secret_arn)
    raw = response.get("SecretString")
    if not raw:
        return False

    data = json.loads(raw)
    for key, value in data.items():
        environ.setdefault(key.upper(), str(value))
    return True
