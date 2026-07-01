"""Data-access layer for knowledge records.

The repository owns all SQLAlchemy query construction and keeps the service
layer free of ORM details. It never commits -- transaction control belongs to
the caller (the service) so a request maps to a single atomic transaction.

Documents are passed as ``(name, content)`` pairs to keep this layer decoupled
from the Pydantic schemas.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.models import Document, Knowledge

DocumentPair = tuple[str, str]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _like_pattern(query: str) -> str:
    # Escape LIKE wildcards in the user query so they are matched literally.
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class KnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- writes ----------------------------------------------------------- #
    def create(
        self,
        *,
        namespace: str,
        title: str,
        type: str,
        status: str,
        meta: dict | None = None,
        documents: Iterable[DocumentPair] = (),
    ) -> Knowledge:
        knowledge = Knowledge(
            namespace=namespace,
            title=title,
            type=type,
            status=status,
            meta=meta or {},
        )
        for name, content in documents:
            knowledge.documents.append(Document(name=name, content=content))
        self.session.add(knowledge)
        self.session.flush()
        return knowledge

    def replace_documents(
        self, knowledge: Knowledge, documents: Sequence[DocumentPair]
    ) -> None:
        knowledge.documents = [
            Document(name=name, content=content) for name, content in documents
        ]
        self.session.flush()

    def soft_delete(self, knowledge: Knowledge) -> None:
        knowledge.deleted_at = _utcnow()
        self.session.flush()

    def touch(self, knowledge: Knowledge) -> None:
        """Force ``updated_at`` to refresh even if only documents changed."""

        knowledge.updated_at = _utcnow()
        self.session.flush()

    # -- reads ------------------------------------------------------------ #
    def get(self, knowledge_id: uuid.UUID) -> Knowledge | None:
        stmt = select(Knowledge).where(
            Knowledge.id == knowledge_id, Knowledge.deleted_at.is_(None)
        )
        return self.session.scalar(stmt)

    def list(
        self,
        *,
        namespace: str | None = None,
        type: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[Knowledge]:
        stmt: Select = select(Knowledge).where(Knowledge.deleted_at.is_(None))
        if namespace:
            stmt = stmt.where(Knowledge.namespace == namespace)
        if type:
            stmt = stmt.where(Knowledge.type == type)
        if status:
            stmt = stmt.where(Knowledge.status == status)
        stmt = stmt.order_by(Knowledge.created_at.desc(), Knowledge.id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))

    def search(
        self,
        *,
        query: str,
        namespace: str | None = None,
        limit: int | None = None,
    ) -> list[Knowledge]:
        pattern = _like_pattern(query)
        # Knowledge ids whose documents match the query.
        doc_match = select(Document.knowledge_id).where(
            Document.content.ilike(pattern, escape="\\")
        )
        stmt: Select = select(Knowledge).where(
            Knowledge.deleted_at.is_(None),
            or_(
                Knowledge.title.ilike(pattern, escape="\\"),
                Knowledge.id.in_(doc_match),
            ),
        )
        if namespace:
            stmt = stmt.where(Knowledge.namespace == namespace)
        stmt = stmt.order_by(Knowledge.created_at.desc(), Knowledge.id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))
