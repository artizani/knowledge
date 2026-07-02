"""MCP server layer exposing Knowledge API tools over Streamable HTTP.

The server wraps the existing :class:`app.service.KnowledgeService` so no
business logic is duplicated. It is mounted into the main FastAPI application at
``/mcp`` and uses the MCP Streamable HTTP transport in JSON-response mode so it
runs statelessly on AWS Lambda:

* ``POST /mcp`` — JSON-RPC request/response (inline JSON, no SSE)
* ``GET /mcp``  — standalone SSE stream for server-to-client messages
* ``DELETE /mcp`` — terminate session

Each Lambda invocation creates a fresh transport/session because Lambda has no
shared memory between requests. We pass ``stateless=True`` to the MCP server so
clients can initialize on any invocation.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import anyio
import mcp.types as types
from mcp.server import Server
from mcp.server.streamable_http import (
    MCP_SESSION_ID_HEADER,
    StreamableHTTPServerTransport,
)
from starlette.requests import Request
from starlette.responses import Response

from app.auth import require_read_auth, require_write_auth
from app.config import get_settings
from app.errors import AuthError, NotFoundError
from app.logging_config import get_logger
from app.schemas import CaptureRequest, SearchRequest, UpdateRequest
from app.service import KnowledgeService

logger = get_logger()


# --------------------------------------------------------------------------- #
# Tool input schemas (kept in one place for consistency)
# ---------------------------------------------------------------------------
_CAPTURE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "namespace": {
            "type": "string",
            "description": "Logical product or team namespace for the record.",
        },
        "title": {
            "type": "string",
            "description": "Short human-readable title.",
        },
        "type": {
            "type": "string",
            "description": "One of: idea, spec, decision, research, meeting, architecture, roadmap, bug, task, note.",
        },
        "status": {
            "type": "string",
            "description": "One of: inbox, research, validated, building, completed, archived.",
        },
        "content": {
            "type": "string",
            "description": "Primary Markdown document body.",
        },
        "document_name": {
            "type": "string",
            "description": "Filename for the primary document (default: body.md).",
        },
        "metadata": {
            "type": "object",
            "description": "Optional key/value metadata.",
        },
    },
    "required": ["namespace", "title", "type", "status", "content"],
}

_GET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "UUID of the knowledge record.",
        },
    },
    "required": ["id"],
}

_LIST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "namespace": {
            "type": "string",
            "description": "Filter by namespace.",
        },
        "type": {
            "type": "string",
            "description": "Filter by knowledge type.",
        },
        "status": {
            "type": "string",
            "description": "Filter by status.",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum records to return (default from config, max 200).",
        },
    },
}

_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Free-text query matched against titles and document contents.",
        },
        "namespace": {
            "type": "string",
            "description": "Restrict search to a namespace.",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum records to return (default from config, max 200).",
        },
    },
    "required": ["query"],
}

_UPDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "UUID of the knowledge record to update.",
        },
        "namespace": {"type": "string"},
        "title": {"type": "string"},
        "type": {"type": "string"},
        "status": {"type": "string"},
        "content": {
            "type": "string",
            "description": "If provided, replaces all existing documents with a single body.md document.",
        },
        "metadata": {"type": "object"},
    },
    "required": ["id"],
}

_DELETE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "UUID of the knowledge record to delete.",
        },
    },
    "required": ["id"],
}


# --------------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------------
def _service() -> KnowledgeService:
    """Build a service from the default repository dependency."""

    from app.main import get_repository  # local import avoids circular dependency

    return KnowledgeService(get_repository())


def _require_write(request: Request) -> None:
    """Enforce write auth inside MCP tool handlers.

    The auth dependencies expect a Starlette request. We call them directly and
    swallow/discard the principal; failures raise :class:`app.errors.AuthError`.
    """

    require_write_auth(request)


def _require_read(request: Request) -> None:
    require_read_auth(request)


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"invalid uuid: {value}") from exc


def _ok(data: Any) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


def _error(message: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps({"error": message}))]


# --------------------------------------------------------------------------- #
# MCP Server
# ---------------------------------------------------------------------------
server = Server("knowledge-api")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name="capture", description="Create a new knowledge record.", inputSchema=_CAPTURE_SCHEMA),
        types.Tool(name="get", description="Retrieve a single knowledge record by ID.", inputSchema=_GET_SCHEMA),
        types.Tool(name="list", description="List knowledge records with optional filters.", inputSchema=_LIST_SCHEMA),
        types.Tool(name="search", description="Search titles and document contents.", inputSchema=_SEARCH_SCHEMA),
        types.Tool(name="update", description="Update an existing knowledge record.", inputSchema=_UPDATE_SCHEMA),
        types.Tool(
            name="delete",
            description="Soft-delete a knowledge record by ID.",
            inputSchema=_DELETE_SCHEMA,
            annotations=types.ToolAnnotations(destructiveHint=True),
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    request = server.request_context.request
    try:
        if name == "capture":
            _require_write(request)
            return _capture(arguments)
        if name == "get":
            _require_read(request)
            return _get(arguments)
        if name == "list":
            _require_read(request)
            return _list(arguments)
        if name == "search":
            _require_read(request)
            return _search(arguments)
        if name == "update":
            _require_write(request)
            return _update(arguments)
        if name == "delete":
            _require_write(request)
            return _delete(arguments)
    except AuthError as exc:
        logger.warning("mcp auth failed", extra={"tool": name, "reason": str(exc)})
        return _error(f"unauthorised: {exc}")
    except NotFoundError as exc:
        return _error(f"not_found: {exc}")
    except Exception as exc:
        logger.exception("mcp tool error", extra={"tool": name})
        return _error(f"error: {exc}")

    return _error(f"unknown tool: {name}")


def _capture(arguments: dict) -> list[types.TextContent]:
    request = CaptureRequest(
        namespace=arguments["namespace"],
        title=arguments["title"],
        type=arguments["type"],
        status=arguments["status"],
        documents=[
            {
                "name": arguments.get("document_name", "body.md"),
                "content": arguments["content"],
            }
        ],
        metadata=arguments.get("metadata", {}),
    )
    result = _service().capture(request)
    return _ok({"id": result["id"], "status": "captured"})


def _get(arguments: dict) -> list[types.TextContent]:
    kid = _uuid(arguments["id"])
    result = _service().get(kid)
    return _ok(result)


def _list(arguments: dict) -> list[types.TextContent]:
    items = _service().list(
        namespace=arguments.get("namespace"),
        type=arguments.get("type"),
        status=arguments.get("status"),
        limit=arguments.get("limit"),
    )
    return _ok({"items": items, "count": len(items)})


def _search(arguments: dict) -> list[types.TextContent]:
    request = SearchRequest(
        query=arguments["query"],
        namespace=arguments.get("namespace"),
        limit=arguments.get("limit"),
    )
    items = _service().search(request)
    return _ok({"items": items, "count": len(items)})


def _update(arguments: dict) -> list[types.TextContent]:
    kid = _uuid(arguments["id"])
    documents = None
    if "content" in arguments:
        documents = [{"name": "body.md", "content": arguments["content"]}]
    request = UpdateRequest(
        namespace=arguments.get("namespace"),
        title=arguments.get("title"),
        type=arguments.get("type"),
        status=arguments.get("status"),
        documents=documents,
        metadata=arguments.get("metadata"),
    )
    result = _service().update(kid, request)
    return _ok(result)


def _delete(arguments: dict) -> list[types.TextContent]:
    kid = _uuid(arguments["id"])
    result = _service().delete(kid)
    return _ok({"id": result["id"], "status": "deleted"})


# --------------------------------------------------------------------------- #
# Streamable HTTP transport + FastAPI mount helper
# ---------------------------------------------------------------------------
async def mcp_streamable_endpoint(request: Request) -> Response:
    """ASGI handler for the MCP Streamable HTTP endpoint.

    A new transport and session are created for each invocation so the endpoint
    remains stateless and Lambda-friendly. JSON responses are returned inline
    (``is_json_response_enabled=True``) rather than holding open an SSE stream.
    """

    transport = StreamableHTTPServerTransport(
        mcp_session_id=None,  # stateless: no session validation between invocations
        is_json_response_enabled=True,
    )

    scope = request.scope
    receive = request.receive
    send = request._send  # noqa: SLF001  # required by transport.handle_request

    async with transport.connect() as (read_stream, write_stream):
        async with anyio.create_task_group() as tg:
            tg.start_soon(
                server.run,
                read_stream,
                write_stream,
                server.create_initialization_options(),
                False,  # raise_exceptions
                True,  # stateless
            )
            await transport.handle_request(scope, receive, send)
            tg.cancel_scope.cancel()

    # The transport already sent the real response via ``send``; return an empty
    # response so FastAPI/Starlette has a valid ASGI return value.
    return Response(status_code=200)
