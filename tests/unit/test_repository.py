"""Unit tests for the data-access repository."""
from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def repo(db_session):
    from app.repository import KnowledgeRepository

    return KnowledgeRepository(db_session)


def _make(repo, db_session, **overrides):
    data = {
        "namespace": "icebox",
        "title": "Life Weeks",
        "type": "idea",
        "status": "research",
        "meta": {"tags": ["consumer"]},
        "documents": [("spec.md", "# Spec PAYE"), ("research.md", "# Research")],
    }
    data.update(overrides)
    k = repo.create(**data)
    db_session.commit()
    return k


def test_create_persists_knowledge_and_documents(repo, db_session):
    k = _make(repo, db_session)
    assert isinstance(k.id, uuid.UUID)
    assert k.meta == {"tags": ["consumer"]}
    assert {d.name for d in k.documents} == {"spec.md", "research.md"}


def test_get_returns_item(repo, db_session):
    k = _make(repo, db_session)
    fetched = repo.get(k.id)
    assert fetched is not None
    assert fetched.id == k.id


def test_get_missing_returns_none(repo):
    assert repo.get(uuid.uuid4()) is None


def test_soft_delete_hides_from_get(repo, db_session):
    k = _make(repo, db_session)
    repo.soft_delete(k)
    db_session.commit()
    assert repo.get(k.id) is None
    assert k.deleted_at is not None


def test_list_filters_by_namespace(repo, db_session):
    _make(repo, db_session, namespace="icebox", title="A")
    _make(repo, db_session, namespace="taxable", title="B")

    results = repo.list(namespace="taxable")
    assert len(results) == 1
    assert results[0].title == "B"


def test_list_filters_by_type_and_status(repo, db_session):
    _make(repo, db_session, type="idea", status="inbox", title="A")
    _make(repo, db_session, type="spec", status="building", title="B")

    assert [k.title for k in repo.list(type="spec")] == ["B"]
    assert [k.title for k in repo.list(status="inbox")] == ["A"]


def test_list_excludes_soft_deleted(repo, db_session):
    a = _make(repo, db_session, title="A")
    _make(repo, db_session, title="B")
    repo.soft_delete(a)
    db_session.commit()

    titles = {k.title for k in repo.list()}
    assert titles == {"B"}


def test_list_respects_limit_and_orders_newest_first(repo, db_session):
    import time

    first = _make(repo, db_session, title="first")
    time.sleep(0.01)
    second = _make(repo, db_session, title="second")

    results = repo.list(limit=1)
    assert len(results) == 1
    assert results[0].id == second.id
    assert first.id != second.id


def test_search_matches_title_case_insensitive(repo, db_session):
    _make(repo, db_session, title="PAYE rules", documents=[])
    _make(repo, db_session, title="Something else", documents=[])

    results = repo.search(query="paye")
    assert len(results) == 1
    assert results[0].title == "PAYE rules"


def test_search_matches_document_content(repo, db_session):
    _make(repo, db_session, title="Nothing", documents=[("d.md", "contains PAYE inside")])
    _make(repo, db_session, title="Other", documents=[("d.md", "unrelated")])

    results = repo.search(query="PAYE")
    assert len(results) == 1
    assert results[0].title == "Nothing"


def test_search_excludes_soft_deleted(repo, db_session):
    k = _make(repo, db_session, title="PAYE thing", documents=[])
    repo.soft_delete(k)
    db_session.commit()
    assert repo.search(query="PAYE") == []


def test_search_namespace_filter(repo, db_session):
    _make(repo, db_session, namespace="taxable", title="PAYE a", documents=[])
    _make(repo, db_session, namespace="icebox", title="PAYE b", documents=[])

    results = repo.search(query="PAYE", namespace="taxable")
    assert len(results) == 1
    assert results[0].namespace == "taxable"


def test_search_no_duplicate_rows(repo, db_session):
    # Two documents both matching should not duplicate the knowledge row.
    _make(
        repo,
        db_session,
        title="PAYE title",
        documents=[("a.md", "PAYE one"), ("b.md", "PAYE two")],
    )
    results = repo.search(query="PAYE")
    assert len(results) == 1


def test_replace_documents(repo, db_session):
    k = _make(repo, db_session)
    repo.replace_documents(k, [("new.md", "new content")])
    db_session.commit()
    db_session.refresh(k)
    assert [d.name for d in k.documents] == ["new.md"]
