"""API tests for POST /capture."""
from __future__ import annotations

import uuid


def test_capture_success(client, auth_headers, sample_capture_payload):
    resp = client.post("/capture", json=sample_capture_payload, headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "captured"
    # id is a valid UUID
    uuid.UUID(body["id"])
    # request id header present
    assert resp.headers.get("x-request-id")


def test_capture_persists_and_is_retrievable(client, auth_headers, sample_capture_payload):
    rid = client.post("/capture", json=sample_capture_payload, headers=auth_headers).json()["id"]
    got = client.get(f"/knowledge/{rid}")
    assert got.status_code == 200
    body = got.json()
    assert body["title"] == "Life Weeks"
    assert body["namespace"] == "icebox"
    assert body["metadata"]["createdBy"] == "ChatGPT"
    assert {d["name"] for d in body["documents"]} == {"spec.md", "research.md"}


def test_capture_without_auth_is_401(client, sample_capture_payload):
    resp = client.post("/capture", json=sample_capture_payload)
    assert resp.status_code == 401


def test_capture_with_bad_token_is_401(client, sample_capture_payload):
    resp = client.post(
        "/capture", json=sample_capture_payload, headers={"Authorization": "Bearer wrong"}
    )
    assert resp.status_code == 401


def test_capture_invalid_type_is_400(client, auth_headers, sample_capture_payload):
    sample_capture_payload["type"] = "not-a-type"
    resp = client.post("/capture", json=sample_capture_payload, headers=auth_headers)
    assert resp.status_code == 400


def test_capture_missing_title_is_400(client, auth_headers, sample_capture_payload):
    del sample_capture_payload["title"]
    resp = client.post("/capture", json=sample_capture_payload, headers=auth_headers)
    assert resp.status_code == 400


def test_capture_extra_field_is_400(client, auth_headers, sample_capture_payload):
    sample_capture_payload["unexpected"] = "x"
    resp = client.post("/capture", json=sample_capture_payload, headers=auth_headers)
    assert resp.status_code == 400


def test_capture_without_documents_ok(client, auth_headers):
    payload = {"namespace": "ns", "title": "T", "type": "note", "status": "inbox"}
    resp = client.post("/capture", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    rid = resp.json()["id"]
    body = client.get(f"/knowledge/{rid}").json()
    assert body["documents"] == []
    assert body["metadata"] == {}
