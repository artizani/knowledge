"""Tests for the MCP tool layer.

These tests bypass the HTTP transport and call the tool handlers directly.
Because the handlers read the current Starlette request from the MCP request
context, we set a minimal context around each call.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from app import mcp_server
from app.config import get_settings
from app.service import KnowledgeService
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext


class _FakeRequest:
    """Minimal mock of a Starlette request for auth extraction."""

    def __init__(self, token: str | None = None):
        self.headers = {"authorization": f"Bearer {token}"} if token else {}


def _text(result) -> dict:
    assert len(result) == 1
    assert result[0].type == "text"
    return json.loads(result[0].text)


def _call_tool(name: str, arguments: dict, request: _FakeRequest):
    """Run an MCP tool handler with a faked request context."""

    token = request_ctx.set(
        RequestContext(
            request_id="1",
            meta=None,
            session=None,
            lifespan_context=None,
            request=request,
        )
    )
    try:
        return asyncio.run(mcp_server.call_tool(name, arguments))
    finally:
        request_ctx.reset(token)


@pytest.fixture(autouse=True)
def _inject_fake_repository(repository, monkeypatch):
    """Ensure direct imports of get_repository use the in-memory fake."""
    import app.main

    monkeypatch.setattr(app.main, "get_repository", lambda: repository)


@pytest.fixture
def read_request():
    return _FakeRequest()


@pytest.fixture
def write_request():
    return _FakeRequest(get_settings().api_token)


async def test_list_tools():
    tools = await mcp_server.list_tools()
    names = {t.name for t in tools}
    assert names == {"capture", "get", "list", "search", "update", "delete"}


def test_capture_success(write_request):
    result = _call_tool(
        "capture",
        {
            "namespace": "mcp",
            "title": "MCP capture",
            "type": "note",
            "status": "inbox",
            "content": "content via mcp",
        },
        write_request,
    )
    body = _text(result)
    assert body["status"] == "captured"
    uuid.UUID(body["id"])


def test_capture_requires_auth(read_request):
    result = _call_tool(
        "capture",
        {
            "namespace": "mcp",
            "title": "x",
            "type": "note",
            "status": "inbox",
            "content": "x",
        },
        read_request,
    )
    assert "unauthorised" in _text(result)["error"]


def test_get_after_capture(write_request):
    captured = _call_tool(
        "capture",
        {
            "namespace": "mcp",
            "title": "Get me",
            "type": "note",
            "status": "inbox",
            "content": "find me",
        },
        write_request,
    )
    kid = _text(captured)["id"]

    result = _call_tool("get", {"id": kid}, write_request)
    body = _text(result)
    assert body["title"] == "Get me"
    assert body["namespace"] == "mcp"


def test_get_not_found(write_request):
    result = _call_tool(
        "get", {"id": "00000000-0000-0000-0000-000000000000"}, write_request
    )
    assert "not_found" in _text(result)["error"]


def test_search(write_request):
    _call_tool(
        "capture",
        {
            "namespace": "search-ns",
            "title": "Searchable",
            "type": "note",
            "status": "inbox",
            "content": "unique mcp search token",
        },
        write_request,
    )

    result = _call_tool(
        "search", {"query": "unique mcp search token"}, write_request
    )
    body = _text(result)
    assert body["count"] == 1
    assert body["items"][0]["title"] == "Searchable"


def test_update_and_delete(write_request):
    captured = _call_tool(
        "capture",
        {
            "namespace": "mcp",
            "title": "Old title",
            "type": "note",
            "status": "inbox",
            "content": "old body",
        },
        write_request,
    )
    kid = _text(captured)["id"]

    updated = _call_tool(
        "update",
        {"id": kid, "title": "New title", "content": "new body"},
        write_request,
    )
    body = _text(updated)
    assert body["title"] == "New title"
    assert body["documents"][0]["content"] == "new body"

    deleted = _call_tool("delete", {"id": kid}, write_request)
    assert _text(deleted)["status"] == "deleted"

    gone = _call_tool("get", {"id": kid}, write_request)
    assert "not_found" in _text(gone)["error"]


def test_list(write_request):
    _call_tool(
        "capture",
        {
            "namespace": "list-ns",
            "title": "Listable",
            "type": "note",
            "status": "inbox",
            "content": "x",
        },
        write_request,
    )

    result = _call_tool("list", {"namespace": "list-ns"}, write_request)
    body = _text(result)
    assert body["count"] >= 1
    assert all(i["namespace"] == "list-ns" for i in body["items"])


def test_unknown_tool(write_request):
    result = _call_tool("nope", {}, write_request)
    assert "unknown tool" in _text(result)["error"]


def test_invalid_uuid(write_request):
    result = _call_tool("get", {"id": "not-a-uuid"}, write_request)
    assert "error" in _text(result)
