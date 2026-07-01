"""Tests for the Supabase PostgREST repository layer."""
from __future__ import annotations

import json
import uuid

import httpx
import pytest

from app.repository import KnowledgeRepository


class _RecordingTransport(httpx.MockTransport):
    def __init__(self, handler):
        super().__init__(handler)
        self.last_request: httpx.Request | None = None

    def handle_request(self, request: httpx.Request):
        self.last_request = request
        return super().handle_request(request)


@pytest.fixture
def repo():
    return KnowledgeRepository(
        base_url="https://example.supabase.co/rest/v1",
        api_key="anon",
        service_key="service",
    )


def _install_write(repo, handler):
    transport = _RecordingTransport(handler)
    repo._write_client = httpx.Client(
        base_url=repo.base_url,
        headers=repo._headers(repo.service_key),
        transport=transport,
        timeout=10.0,
    )
    return transport


def _install_read(repo, handler):
    transport = _RecordingTransport(handler)
    repo._read_client = httpx.Client(
        base_url=repo.base_url,
        headers=repo._headers(repo.api_key),
        transport=transport,
        timeout=10.0,
    )
    return transport


ABC = uuid.UUID("00000000-0000-0000-0000-000000000abc")


def test_create_knowledge_posts_to_table(repo):
    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/knowledge"
        assert request.headers["apikey"] == "service"
        assert request.headers["authorization"] == "Bearer service"
        assert request.headers["prefer"] == "return=representation"
        body = json.loads(request.content)
        assert body["namespace"] == "icebox"
        assert body["title"] == "T"
        assert body["type"] == "idea"
        assert body["status"] == "inbox"
        assert body["metadata"] == {"tags": ["a"]}
        return httpx.Response(201, json=[{"id": str(ABC), "created_at": "2024-01-01T00:00:00Z"}])

    transport = _install_write(repo, handler)
    result = repo.create_knowledge(
        namespace="icebox", title="T", type="idea", status="inbox", metadata={"tags": ["a"]}
    )
    assert result["id"] == str(ABC)
    assert transport.last_request is not None


def test_create_documents_posts_batch(repo):
    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/documents"
        assert request.headers["apikey"] == "service"
        body = json.loads(request.content)
        assert len(body) == 2
        assert {d["name"] for d in body} == {"a.md", "b.md"}
        return httpx.Response(201, json=[{"id": "d1"}, {"id": "d2"}])

    transport = _install_write(repo, handler)
    result = repo.create_documents(
        str(ABC), [("a.md", "content-a"), ("b.md", "content-b")]
    )
    assert len(result) == 2


def test_get_joins_documents(repo):
    def handler(request: httpx.Request):
        assert request.method == "GET"
        assert request.url.path == "/rest/v1/knowledge"
        assert f"id=eq.{ABC}" in str(request.url)
        assert "deleted_at=is.null" in str(request.url)
        assert "select=*,documents(*)" in str(request.url)
        return httpx.Response(200, json=[{"id": str(ABC), "title": "T", "documents": [{"name": "a.md"}]}])

    _install_read(repo, handler)
    result = repo.get(ABC)
    assert result["id"] == str(ABC)
    assert result["documents"][0]["name"] == "a.md"


def test_get_missing_returns_none(repo):
    def handler(request: httpx.Request):
        return httpx.Response(200, json=[])

    _install_read(repo, handler)
    assert repo.get(uuid.uuid4()) is None


def test_list_builds_filters(repo):
    def handler(request: httpx.Request):
        qs = str(request.url.query)
        assert "namespace=eq.icebox" in qs
        assert "type=eq.idea" in qs
        assert "status=eq.research" in qs
        assert "limit=10" in qs
        assert "deleted_at=is.null" in qs
        assert "order=created_at.desc" in qs
        assert "select=*,documents(*)" in qs
        return httpx.Response(200, json=[])

    _install_read(repo, handler)
    repo.list(namespace="icebox", type="idea", status="research", limit=10)


def test_search_queries_titles_and_documents_and_merges(repo):
    calls = []

    def handler(request: httpx.Request):
        path = request.url.path
        calls.append((request.method, path, str(request.url.query)))
        if path.endswith("/knowledge") and "title=ilike" in str(request.url):
            return httpx.Response(200, json=[{"id": "k1"}])
        if path.endswith("/documents"):
            return httpx.Response(200, json=[{"knowledge_id": "k2"}])
        if path.endswith("/knowledge") and "id=in" in str(request.url):
            return httpx.Response(200, json=[{"id": "k1"}, {"id": "k2"}])
        return httpx.Response(200, json=[])

    _install_read(repo, handler)
    results = repo.search(query="paye", namespace="taxable", limit=20)
    assert len(results) == 2
    assert {r["id"] for r in results} == {"k1", "k2"}
    assert any("title=ilike.*paye*" in c[2] for c in calls)
    assert any("content=ilike.*paye*" in c[2] for c in calls)
    assert any("id=in.(k1,k2)" in c[2] for c in calls)


def test_update_patches_knowledge(repo):
    def handler(request: httpx.Request):
        assert request.method == "PATCH"
        assert request.url.path == "/rest/v1/knowledge"
        assert f"id=eq.{ABC}" in str(request.url)
        body = json.loads(request.content)
        assert body["title"] == "New"
        assert body["status"] == "building"
        return httpx.Response(200, json=[{"id": str(ABC), "title": "New", "status": "building"}])

    _install_write(repo, handler)
    result = repo.update_knowledge(ABC, {"title": "New", "status": "building"})
    assert result["title"] == "New"


def test_replace_documents_deletes_then_inserts(repo):
    calls = []

    def handler(request: httpx.Request):
        calls.append((request.method, request.url.path, str(request.url.query)))
        if request.method == "DELETE":
            assert request.url.path == "/rest/v1/documents"
            assert f"knowledge_id=eq.{ABC}" in str(request.url)
            return httpx.Response(204)
        if request.method == "POST":
            assert request.url.path == "/rest/v1/documents"
            return httpx.Response(201, json=[{"id": "d1"}])
        return httpx.Response(200)

    _install_write(repo, handler)
    repo.replace_documents(ABC, [("new.md", "body")])
    assert calls[0][0] == "DELETE"
    assert calls[1][0] == "POST"


def test_soft_delete_patches_deleted_at(repo):
    def handler(request: httpx.Request):
        assert request.method == "PATCH"
        assert request.url.path == "/rest/v1/knowledge"
        assert f"id=eq.{ABC}" in str(request.url)
        body = json.loads(request.content)
        assert body["deleted_at"] is not None
        return httpx.Response(200, json=[{"id": str(ABC), "deleted_at": "2024-01-01T00:00:00Z"}])

    _install_write(repo, handler)
    result = repo.soft_delete(ABC)
    assert result["deleted_at"] is not None


def test_postgrest_error_raises(repo):
    def handler(request: httpx.Request):
        return httpx.Response(500, json={"message": "boom"})

    _install_write(repo, handler)
    with pytest.raises(RuntimeError):
        repo.create_knowledge(namespace="ns", title="T", type="idea", status="inbox")
