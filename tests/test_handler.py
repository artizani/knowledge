"""Tests for the AWS Lambda entrypoint."""
from __future__ import annotations


def test_handler_module_exposes_app_and_handler():
    import handler

    from fastapi import FastAPI

    assert isinstance(handler.app, FastAPI)
    assert callable(handler.handler)


def test_handler_processes_api_gateway_event():
    """A minimal API Gateway HTTP API (v2) event should route to /health."""
    import handler

    event = {
        "version": "2.0",
        "routeKey": "GET /health",
        "rawPath": "/health",
        "rawQueryString": "",
        "headers": {"host": "example.com"},
        "requestContext": {
            "http": {
                "method": "GET",
                "path": "/health",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
            },
            "requestId": "test-req",
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }
    response = handler.handler(event, None)
    assert response["statusCode"] == 200
    assert "ok" in response["body"]
