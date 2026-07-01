"""Unit tests for the service layer (business logic)."""
from __future__ import annotations

import uuid

import pytest

from tests.fake_repository import FakeKnowledgeRepository


@pytest.fixture
def service():
    from app.service import KnowledgeService

    return KnowledgeService(FakeKnowledgeRepository())


def _capture(service, **overrides):
    from app.schemas import CaptureRequest

    data = {
        "namespace": "icebox",
        "title": "Life Weeks",
        "type": "idea",
        "status": "research",
        "documents": [{"name": "spec.md", "content": "# Spec PAYE"}],
        "metadata": {"tags": ["consumer"]},
    }
    data.update(overrides)
    return service.capture(CaptureRequest.model_validate(data))


def test_capture_persists(service):
    k = _capture(service)
    assert uuid.UUID(k["id"])
    assert k["title"] == "Life Weeks"
    assert k["metadata"] == {"tags": ["consumer"]}
    assert len(k["documents"]) == 1
    assert service.get(uuid.UUID(k["id"]))["id"] == k["id"]


def test_get_missing_raises(service):
    from app.errors import NotFoundError

    with pytest.raises(NotFoundError):
        service.get(uuid.uuid4())


def test_list_returns_items(service):
    _capture(service, title="A")
    _capture(service, title="B")
    items = service.list()
    assert {i["title"] for i in items} == {"A", "B"}


def test_list_applies_default_limit(service, monkeypatch):
    from app import config

    monkeypatch.setenv("DEFAULT_LIST_LIMIT", "2")
    config.get_settings.cache_clear()
    try:
        for i in range(3):
            _capture(service, title=f"T{i}")
        assert len(service.list()) == 2
    finally:
        config.get_settings.cache_clear()


def test_list_clamps_to_max_limit(service, monkeypatch):
    from app import config

    monkeypatch.setenv("MAX_LIST_LIMIT", "1")
    config.get_settings.cache_clear()
    try:
        for i in range(3):
            _capture(service, title=f"T{i}")
        assert len(service.list(limit=50)) == 1
    finally:
        config.get_settings.cache_clear()


def test_search(service):
    _capture(service, title="PAYE rules", documents=[])
    _capture(service, title="Unrelated", documents=[])
    from app.schemas import SearchRequest

    results = service.search(SearchRequest(query="paye"))
    assert len(results) == 1
    assert results[0]["title"] == "PAYE rules"


def test_update_changes_fields(service):
    from app.schemas import UpdateRequest

    k = _capture(service, title="Old", status="inbox")
    updated = service.update(uuid.UUID(k["id"]), UpdateRequest(title="New", status="building"))
    assert updated["title"] == "New"
    assert updated["status"] == "building"
    assert updated["namespace"] == "icebox"


def test_update_replaces_documents_and_metadata(service):
    from app.schemas import DocumentIn, UpdateRequest

    k = _capture(service)
    service.update(
        uuid.UUID(k["id"]),
        UpdateRequest(
            documents=[DocumentIn(name="new.md", content="new")],
            metadata={"priority": "high"},
        ),
    )
    fetched = service.get(uuid.UUID(k["id"]))
    assert [d["name"] for d in fetched["documents"]] == ["new.md"]
    assert fetched["metadata"] == {"priority": "high"}


def test_update_missing_raises(service):
    from app.errors import NotFoundError
    from app.schemas import UpdateRequest

    with pytest.raises(NotFoundError):
        service.update(uuid.uuid4(), UpdateRequest(title="X"))


def test_delete_soft_deletes(service):
    from app.errors import NotFoundError

    k = _capture(service)
    deleted = service.delete(uuid.UUID(k["id"]))
    assert deleted["id"] == k["id"]
    assert deleted["deleted_at"] is not None
    with pytest.raises(NotFoundError):
        service.get(uuid.UUID(k["id"]))


def test_delete_missing_raises(service):
    from app.errors import NotFoundError

    with pytest.raises(NotFoundError):
        service.delete(uuid.uuid4())


def test_double_delete_raises(service):
    from app.errors import NotFoundError

    k = _capture(service)
    service.delete(uuid.UUID(k["id"]))
    with pytest.raises(NotFoundError):
        service.delete(uuid.UUID(k["id"]))
