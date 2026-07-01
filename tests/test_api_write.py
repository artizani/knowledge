"""API tests for writes: PUT /knowledge/{id}, DELETE /knowledge/{id}."""
from __future__ import annotations

import uuid


def _capture(client, auth_headers, **overrides):
    payload = {
        "namespace": "icebox",
        "title": "Original",
        "type": "idea",
        "status": "inbox",
        "documents": [{"name": "spec.md", "content": "original"}],
        "metadata": {"tags": ["a"]},
    }
    payload.update(overrides)
    return client.post("/capture", json=payload, headers=auth_headers).json()["id"]


# -- PUT -------------------------------------------------------------------- #
def test_update_fields(client, auth_headers):
    rid = _capture(client, auth_headers)
    resp = client.put(
        f"/knowledge/{rid}",
        json={"title": "Updated", "status": "building"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Updated"
    assert body["status"] == "building"
    assert body["namespace"] == "icebox"  # unchanged


def test_update_replaces_documents_and_metadata(client, auth_headers):
    rid = _capture(client, auth_headers)
    resp = client.put(
        f"/knowledge/{rid}",
        json={
            "documents": [{"name": "new.md", "content": "new body"}],
            "metadata": {"priority": "high"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [d["name"] for d in body["documents"]] == ["new.md"]
    assert body["metadata"] == {"priority": "high"}


def test_update_missing_is_404(client, auth_headers):
    resp = client.put(
        f"/knowledge/{uuid.uuid4()}", json={"title": "x"}, headers=auth_headers
    )
    assert resp.status_code == 404


def test_update_without_auth_is_401(client, auth_headers):
    rid = _capture(client, auth_headers)
    resp = client.put(f"/knowledge/{rid}", json={"title": "x"})
    assert resp.status_code == 401


def test_update_invalid_type_is_400(client, auth_headers):
    rid = _capture(client, auth_headers)
    resp = client.put(f"/knowledge/{rid}", json={"type": "bogus"}, headers=auth_headers)
    assert resp.status_code == 400


# -- DELETE ----------------------------------------------------------------- #
def test_delete_soft_deletes(client, auth_headers):
    rid = _capture(client, auth_headers)
    resp = client.request("DELETE", f"/knowledge/{rid}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "deleted"
    assert body["id"] == rid
    # gone from reads
    assert client.get(f"/knowledge/{rid}").status_code == 404
    assert client.get("/knowledge").json()["count"] == 0


def test_delete_missing_is_404(client, auth_headers):
    resp = client.request("DELETE", f"/knowledge/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


def test_delete_without_auth_is_401(client, auth_headers):
    rid = _capture(client, auth_headers)
    resp = client.request("DELETE", f"/knowledge/{rid}")
    assert resp.status_code == 401


def test_double_delete_is_404(client, auth_headers):
    rid = _capture(client, auth_headers)
    client.request("DELETE", f"/knowledge/{rid}", headers=auth_headers)
    resp = client.request("DELETE", f"/knowledge/{rid}", headers=auth_headers)
    assert resp.status_code == 404
