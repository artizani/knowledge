"""API tests for reads: GET /knowledge/{id}, GET /knowledge, POST /search."""
from __future__ import annotations

import uuid


def _capture(client, auth_headers, **overrides):
    payload = {
        "namespace": "icebox",
        "title": "Life Weeks",
        "type": "idea",
        "status": "research",
        "documents": [{"name": "spec.md", "content": "# Spec about PAYE"}],
        "metadata": {"tags": ["consumer"]},
    }
    payload.update(overrides)
    resp = client.post("/capture", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()["id"]


# -- GET /knowledge/{id} ---------------------------------------------------- #
def test_get_one_open_without_auth(client, auth_headers):
    rid = _capture(client, auth_headers)
    resp = client.get(f"/knowledge/{rid}")  # no auth header
    assert resp.status_code == 200
    assert resp.json()["id"] == rid


def test_get_missing_is_404(client):
    resp = client.get(f"/knowledge/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_get_invalid_uuid_is_400(client):
    resp = client.get("/knowledge/not-a-uuid")
    assert resp.status_code == 400


# -- GET /knowledge (list) -------------------------------------------------- #
def test_list_returns_items_and_count(client, auth_headers):
    _capture(client, auth_headers, title="A")
    _capture(client, auth_headers, title="B")
    resp = client.get("/knowledge")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert len(body["items"]) == 2


def test_list_filters_by_namespace(client, auth_headers):
    _capture(client, auth_headers, namespace="icebox", title="A")
    _capture(client, auth_headers, namespace="taxable", title="B")
    body = client.get("/knowledge", params={"namespace": "taxable"}).json()
    assert body["count"] == 1
    assert body["items"][0]["title"] == "B"


def test_list_filters_by_type_and_status(client, auth_headers):
    _capture(client, auth_headers, type="idea", status="inbox", title="A")
    _capture(client, auth_headers, type="spec", status="building", title="B")
    assert client.get("/knowledge", params={"type": "spec"}).json()["count"] == 1
    assert client.get("/knowledge", params={"status": "inbox"}).json()["count"] == 1


def test_list_respects_limit(client, auth_headers):
    for i in range(3):
        _capture(client, auth_headers, title=f"T{i}")
    body = client.get("/knowledge", params={"limit": 2}).json()
    assert len(body["items"]) == 2


def test_list_newest_first(client, auth_headers):
    import time

    _capture(client, auth_headers, title="older")
    time.sleep(0.01)
    _capture(client, auth_headers, title="newer")
    items = client.get("/knowledge").json()["items"]
    assert items[0]["title"] == "newer"


# -- POST /search ----------------------------------------------------------- #
def test_search_by_title(client, auth_headers):
    _capture(client, auth_headers, title="PAYE rules", documents=[])
    _capture(client, auth_headers, title="unrelated", documents=[])
    body = client.post("/search", json={"query": "paye"}).json()
    assert body["count"] == 1
    assert body["items"][0]["title"] == "PAYE rules"


def test_search_by_document_content(client, auth_headers):
    _capture(client, auth_headers, title="Nothing here",
             documents=[{"name": "d.md", "content": "mentions PAYE deep inside"}])
    body = client.post("/search", json={"query": "PAYE"}).json()
    assert body["count"] == 1


def test_search_empty_query_is_400(client):
    resp = client.post("/search", json={"query": "   "})
    assert resp.status_code == 400


def test_search_namespace_filter(client, auth_headers):
    _capture(client, auth_headers, namespace="taxable", title="PAYE a", documents=[])
    _capture(client, auth_headers, namespace="icebox", title="PAYE b", documents=[])
    body = client.post("/search", json={"query": "PAYE", "namespace": "taxable"}).json()
    assert body["count"] == 1
    assert body["items"][0]["namespace"] == "taxable"
