"""CLI helper to generate and rotate API tokens stored in AWS Secrets Manager.

Usage examples:

    # Generate one new token and add it to the existing list (default)
    python scripts/rotate_api_token.py

    # Generate a new token and replace all existing tokens (dangerous)
    python scripts/rotate_api_token.py --replace

    # Generate N tokens
    python scripts/rotate_api_token.py --count 3

    # Preview without writing anything
    python scripts/rotate_api_token.py --dry-run

The script updates ``API_TOKENS`` in the secret as a JSON list and prints the
new token(s) to stdout. It keeps ``API_TOKEN`` in sync with the first entry for
backward compatibility.
"""
from __future__ import annotations

import argparse
import json
import secrets
import string

import boto3

SECRET_NAME = "knowledge-api/config"
REGION = "eu-west-1"
ALPHABET = string.ascii_letters + string.digits + "-_"
TOKEN_LENGTH = 48


def generate_token(length: int = TOKEN_LENGTH) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def load_secret(client, secret_name: str) -> dict:
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])


def save_secret(client, secret_name: str, secret: dict) -> None:
    client.put_secret_value(
        SecretId=secret_name,
        SecretString=json.dumps(secret, indent=2),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate/rotate API tokens")
    parser.add_argument("--replace", action="store_true", help="Replace all existing tokens")
    parser.add_argument("--count", type=int, default=1, help="Number of new tokens to generate")
    parser.add_argument("--dry-run", action="store_true", help="Print new tokens but do not update the secret")
    parser.add_argument("--secret-name", default=SECRET_NAME, help="Secrets Manager secret name")
    parser.add_argument("--profile", default="dangote-dev", help="AWS profile")
    parser.add_argument("--region", default=REGION, help="AWS region")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    client = session.client("secretsmanager")
    secret = load_secret(client, args.secret_name)

    new_tokens = [generate_token() for _ in range(args.count)]

    existing = secret.get("API_TOKENS", [])
    if isinstance(existing, str):
        existing = [existing] if existing else []

    if args.replace:
        final_tokens = new_tokens
    else:
        final_tokens = existing + new_tokens

    secret["API_TOKENS"] = final_tokens
    secret["API_TOKEN"] = final_tokens[0]

    if args.dry_run:
        print("[dry-run] secret would be updated to:")
        print(json.dumps({k: "***" if k in ("API_TOKEN", "API_TOKENS") else v for k, v in secret.items()}, indent=2))
    else:
        save_secret(client, args.secret_name, secret)
        print(f"Updated secret {args.secret_name}")

    for token in new_tokens:
        print(token)


if __name__ == "__main__":
    main()
