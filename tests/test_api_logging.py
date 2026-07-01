"""API tests for request logging and health checks."""
from __future__ import annotations

import logging


def _attach_capture(logger_name="knowledge"):
    logger = logging.getLogger(logger_name)
    records: list[logging.LogRecord] = []

    class _H(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _H(level=logging.INFO)
    logger.addHandler(handler)
    return logger, handler, records


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_root_endpoint(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_request_id_header_generated(client):
    resp = client.get("/health")
    assert resp.headers.get("x-request-id")


def test_request_id_header_echoed(client):
    resp = client.get("/health", headers={"x-request-id": "trace-123"})
    assert resp.headers.get("x-request-id") == "trace-123"


def test_request_logged_with_fields(client, auth_headers):
    logger, handler, records = _attach_capture()
    try:
        client.get("/knowledge", params={"namespace": "icebox"})
    finally:
        logger.removeHandler(handler)

    request_logs = [r for r in records if getattr(r, "endpoint", None)]
    assert request_logs, "expected a structured request log record"
    rec = request_logs[-1]
    assert rec.endpoint == "GET /knowledge"
    assert rec.namespace == "icebox"
    assert isinstance(rec.latency_ms, (int, float))
    assert rec.success is True
    assert getattr(rec, "request_id", None)


def test_failed_request_logged_as_unsuccessful(client, auth_headers, monkeypatch):
    from app import service

    def boom(self, *args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(service.KnowledgeService, "list", boom)

    logger, handler, records = _attach_capture()
    try:
        resp = client.get("/knowledge")
    finally:
        logger.removeHandler(handler)

    assert resp.status_code == 500
    request_logs = [r for r in records if getattr(r, "endpoint", None)]
    assert request_logs[-1].success is False


def test_capture_logs_namespace(client, auth_headers, sample_capture_payload):
    logger, handler, records = _attach_capture()
    try:
        client.post("/capture", json=sample_capture_payload, headers=auth_headers)
    finally:
        logger.removeHandler(handler)

    request_logs = [r for r in records if getattr(r, "endpoint", None)]
    assert request_logs[-1].endpoint == "POST /capture"
    assert request_logs[-1].namespace == "icebox"
