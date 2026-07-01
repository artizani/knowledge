"""Tests for the AWS Secrets Manager loader."""
from __future__ import annotations

import json


class FakeSecretsClient:
    def __init__(self, secret_string: str | None):
        self._secret_string = secret_string
        self.requested: list[str] = []

    def get_secret_value(self, SecretId: str):  # noqa: N803 (boto3 signature)
        self.requested.append(SecretId)
        return {"SecretString": self._secret_string}


def test_load_secrets_populates_environ():
    from app.secrets import load_secrets_into_env

    client = FakeSecretsClient(
        json.dumps({"database_url": "postgresql://x", "api_token": "tok"})
    )
    env: dict[str, str] = {}
    loaded = load_secrets_into_env(secret_arn="arn:secret", client=client, environ=env)

    assert loaded is True
    assert env["DATABASE_URL"] == "postgresql://x"
    assert env["API_TOKEN"] == "tok"
    assert client.requested == ["arn:secret"]


def test_load_secrets_does_not_override_existing_env():
    from app.secrets import load_secrets_into_env

    client = FakeSecretsClient(json.dumps({"api_token": "from-secret"}))
    env = {"API_TOKEN": "already-set"}
    load_secrets_into_env(secret_arn="arn:secret", client=client, environ=env)
    assert env["API_TOKEN"] == "already-set"


def test_load_secrets_noop_without_arn():
    from app.secrets import load_secrets_into_env

    env: dict[str, str] = {}
    assert load_secrets_into_env(secret_arn=None, client=None, environ=env) is False
    assert env == {}


def test_load_secrets_reads_arn_from_environ():
    from app.secrets import load_secrets_into_env

    client = FakeSecretsClient(json.dumps({"database_url": "postgresql://y"}))
    env = {"SECRET_ARN": "arn:from-env"}
    loaded = load_secrets_into_env(client=client, environ=env)
    assert loaded is True
    assert env["DATABASE_URL"] == "postgresql://y"
    assert client.requested == ["arn:from-env"]


def test_load_secrets_handles_empty_secret_string():
    from app.secrets import load_secrets_into_env

    client = FakeSecretsClient(None)
    env: dict[str, str] = {}
    assert load_secrets_into_env(secret_arn="arn", client=client, environ=env) is False
