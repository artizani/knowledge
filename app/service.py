"""Service layer: business logic and transaction control.

One :class:`KnowledgeService` wraps a single database session; each mutating
method commits (or rolls back) so a request equals one atomic transaction.
The service speaks Pydantic schemas at its boundary and returns ORM objects
for the transport layer to serialise.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import NotFoundError
from app.models import Knowledge
from app.repository import KnowledgeRepository
from app.schemas import CaptureRequest, SearchRequest, UpdateRequest


def _pairs(documents) -> list[tuple[str, str]]:
    return [(d.name, d.content) for d in documents]


class KnowledgeService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = KnowledgeRepository(session)

    def _resolve_limit(self, limit: int | None) -> int:
        settings = get_settings()
        if limit is None:
            return settings.default_list_limit
        return min(limit, settings.max_list_limit)

    # -- commands --------------------------------------------------------- #
    def capture(self, request: CaptureRequest) -> Knowledge:
        try:
            knowledge = self.repo.create(
                namespace=request.namespace,
                title=request.title,
                type=request.type,
                status=request.status,
                meta=request.metadata,
                documents=_pairs(request.documents),
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(knowledge)
        return knowledge

    def update(self, knowledge_id: uuid.UUID, request: UpdateRequest) -> Knowledge:
        knowledge = self.repo.get(knowledge_id)
        if knowledge is None:
            raise NotFoundError(str(knowledge_id))
        try:
            if request.namespace is not None:
                knowledge.namespace = request.namespace
            if request.title is not None:
                knowledge.title = request.title
            if request.type is not None:
                knowledge.type = request.type
            if request.status is not None:
                knowledge.status = request.status
            if request.metadata is not None:
                knowledge.meta = request.metadata
            if request.documents is not None:
                self.repo.replace_documents(knowledge, _pairs(request.documents))
            # Ensure updated_at advances even when only documents changed.
            self.repo.touch(knowledge)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(knowledge)
        return knowledge

    def delete(self, knowledge_id: uuid.UUID) -> Knowledge:
        knowledge = self.repo.get(knowledge_id)
        if knowledge is None:
            raise NotFoundError(str(knowledge_id))
        try:
            self.repo.soft_delete(knowledge)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(knowledge)
        return knowledge

    # -- queries ---------------------------------------------------------- #
    def get(self, knowledge_id: uuid.UUID) -> Knowledge:
        knowledge = self.repo.get(knowledge_id)
        if knowledge is None:
            raise NotFoundError(str(knowledge_id))
        return knowledge

    def list(
        self,
        *,
        namespace: str | None = None,
        type: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[Knowledge]:
        return self.repo.list(
            namespace=namespace,
            type=type,
            status=status,
            limit=self._resolve_limit(limit),
        )

    def search(self, request: SearchRequest) -> list[Knowledge]:
        return self.repo.search(
            query=request.query,
            namespace=request.namespace,
            limit=self._resolve_limit(request.limit),
        )
