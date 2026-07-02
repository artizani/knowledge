"""Integration tests for the MCP Streamable HTTP endpoint.

These tests exercise the full ASGI route through the official MCP transport in
JSON-response mode, which is the Lambda-compatible variant.
"""
from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def mcp_headers(auth_headers) -> dict[str, str]:
    """Headers required by the Streamable HTTP transport in JSON mode."""

    return {
        **auth_headers,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _rpc(method: str, params: dict | None = None, rpc_id: str = "1") -> dict:
    msg = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def test_mcp_tools_list(client, mcp_headers):
    resp = client.post("/mcp", json=_rpc("tools/list"), headers=mcp_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "1"
    tools = {t["name"] for t in body["result"]["tools"]}
    assert tools == {"capture", "get", "list", "search", "update", "delete"}


def test_mcp_capture_and_get(client, mcp_headers):
    # capture
    resp = client.post(
        "/mcp",
        json=_rpc(
            "tools/call",
            {
                "name": "capture",
                "arguments": {
                    "namespace": "mcp-http",
                    "title": "Streamable HTTP capture",
                    "type": "note",
                    "status": "inbox",
                    "content": "captured via streamable http",
                },
            },
        ),
        headers=mcp_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("error") is None
    content = body["result"]["content"]
    assert len(content) == 1
    captured = content[0]["text"]
    assert '"status": "captured"' in captured
    kid = uuid.UUID(captured.split('"id": "')[1].split('"')[0])

    # get
    resp = client.post(
        "/mcp",
        json=_rpc(
            "tools/call",
            {"name": "get", "arguments": {"id": str(kid)}},
        ),
        headers=mcp_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("error") is None
    text = body["result"]["content"][0]["text"]
    assert "Streamable HTTP capture" in text


def test_mcp_capture_requires_auth(client):
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    resp = client.post(
        "/mcp",
        json=_rpc(
            "tools/call",
            {
                "name": "capture",
                "arguments": {
                    "namespace": "mcp-http",
                    "title": "No auth",
                    "type": "note",
                    "status": "inbox",
                    "content": "x",
                },
            },
        ),
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("error") is None
    assert "unauthorised" in body["result"]["content"][0]["text"]


def test_mcp_requires_accept_json(client, auth_headers):
    resp = client.post(
        "/mcp",
        json=_rpc("tools/list"),
        headers={**auth_headers, "Content-Type": "application/json"},
    )
    assert resp.status_code == 406


def test_mcp_requires_json_content_type(client, auth_headers):
    resp = client.post(
        "/mcp",
        content=b"{}",
        headers={**auth_headers, "Accept": "application/json", "Content-Type": "text/plain"},
    )
    assert resp.status_code == 400


def test_mcp_search(client, mcp_headers):
    client.post(
        "/mcp",
        json=_rpc(
            "tools/call",
            {
                "name": "capture",
                "arguments": {
                    "namespace": "mcp-search",
                    "title": "Find me",
                    "type": "note",
                    "status": "inbox",
                    "content": "streamable http search token",
                },
            },
        ),
        headers=mcp_headers,
    )

    resp = client.post(
        "/mcp",
        json=_rpc(
            "tools/call",
            {"name": "search", "arguments": {"query": "streamable http search token"}},
        ),
        headers=mcp_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("error") is None
    text = body["result"]["content"][0]["text"]
    assert "Find me" in text
