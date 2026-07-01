"""Tests for SQLAlchemy ORM models."""
from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture
def session():
    from app.database import Base
    from app.models import Document, Knowledge  # noqa: F401 (register mappers)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_knowledge_defaults(session):
    from app.models import Knowledge

    k = Knowledge(namespace="icebox", title="Life Weeks", type="idea", status="research")
    session.add(k)
    session.commit()
    session.refresh(k)

    assert isinstance(k.id, uuid.UUID)
    assert k.created_at is not None
    assert k.updated_at is not None
    assert k.deleted_at is None
    assert k.meta == {}  # JSON default is an empty object


def test_knowledge_documents_relationship(session):
    from app.models import Document, Knowledge

    k = Knowledge(namespace="icebox", title="Life Weeks", type="idea", status="research")
    k.documents.append(Document(name="spec.md", content="# Spec"))
    k.documents.append(Document(name="research.md", content="# Research"))
    session.add(k)
    session.commit()

    fetched = session.scalar(select(Knowledge).where(Knowledge.id == k.id))
    assert len(fetched.documents) == 2
    names = {d.name for d in fetched.documents}
    assert names == {"spec.md", "research.md"}
    # back-reference
    assert fetched.documents[0].knowledge is fetched
    # document has its own id + timestamp
    assert isinstance(fetched.documents[0].id, uuid.UUID)
    assert fetched.documents[0].created_at is not None


def test_metadata_stored_as_json(session):
    from app.models import Knowledge

    payload = {"tags": ["ios", "consumer"], "priority": "low"}
    k = Knowledge(
        namespace="icebox", title="T", type="idea", status="inbox", meta=payload
    )
    session.add(k)
    session.commit()
    session.refresh(k)
    assert k.meta == payload


def test_cascade_delete_orphans_documents(session):
    from app.models import Document, Knowledge

    k = Knowledge(namespace="ns", title="T", type="idea", status="inbox")
    k.documents.append(Document(name="a.md", content="a"))
    session.add(k)
    session.commit()

    session.delete(k)
    session.commit()

    assert session.scalar(select(Document)) is None


def test_replacing_documents_removes_old(session):
    from app.models import Document, Knowledge

    k = Knowledge(namespace="ns", title="T", type="idea", status="inbox")
    k.documents.append(Document(name="old.md", content="old"))
    session.add(k)
    session.commit()

    k.documents = [Document(name="new.md", content="new")]
    session.commit()

    remaining = session.scalars(select(Document)).all()
    assert len(remaining) == 1
    assert remaining[0].name == "new.md"


def test_updated_at_changes_on_update(session):
    from app.models import Knowledge

    k = Knowledge(namespace="ns", title="T", type="idea", status="inbox")
    session.add(k)
    session.commit()
    original = k.updated_at

    time.sleep(0.01)
    k.title = "Changed"
    session.commit()
    session.refresh(k)
    assert k.updated_at >= original
