"""API tests for the error contract (400 / 401 / 404 / 500)."""
from __future__ import annotations

import uuid


def test_400_shape(client, auth_headers):
    resp = client.post("/capture", json={"title": "x"}, headers=auth_headers)
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "invalid_payload"
    assert "detail" in body


def test_401_shape_and_header(client, sample_capture_payload):
    resp = client.post("/capture", json=sample_capture_payload)
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorised"
    assert "www-authenticate" in {k.lower() for k in resp.headers}


def test_404_shape(client):
    resp = client.get(f"/knowledge/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_500_is_masked(client, auth_headers, monkeypatch):
    # Force an unexpected error inside the service layer.
    from app import service

    def boom(self, *args, **kwargs):
        raise RuntimeError("db exploded with secret details")

    monkeypatch.setattr(service.KnowledgeService, "list", boom)

    resp = client.get("/knowledge")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"] == "internal_error"
    # internal details must not leak
    assert "secret details" not in resp.text
