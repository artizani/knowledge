"""Service layer: business logic.

One :class:`KnowledgeService` wraps a :class:`KnowledgeRepository`. Each
mutating method is a single logical operation against the repository. The
service no longer manages SQLAlchemy transactions because PostgREST is
stateless HTTP.
"""
from __future__ import annotations

import uuid

from app.config import get_settings
from app.errors import NotFoundError
from app.repository import KnowledgeRepository
from app.schemas import CaptureRequest, SearchRequest, UpdateRequest


def _pairs(documents) -> list[tuple[str, str]]:
    return [(d.name, d.content) for d in documents]


class KnowledgeService:
    def __init__(self, repo: KnowledgeRepository) -> None:
        self.repo = repo

    def _resolve_limit(self, limit: int | None) -> int:
        settings = get_settings()
        if limit is None:
            return settings.default_list_limit
        return min(limit, settings.max_list_limit)

    # -- commands --------------------------------------------------------- #
    def capture(self, request: CaptureRequest) -> dict:
        knowledge = self.repo.create_knowledge(
            namespace=request.namespace,
            title=request.title,
            type=request.type,
            status=request.status,
            metadata=request.metadata,
        )
        documents = _pairs(request.documents)
        if documents:
            self.repo.create_documents(knowledge["id"], documents)
        return self.repo.get(uuid.UUID(knowledge["id"]))

    def update(self, knowledge_id: uuid.UUID, request: UpdateRequest) -> dict:
        if self.repo.get(knowledge_id) is None:
            raise NotFoundError(str(knowledge_id))
        changes: dict = {}
        if request.namespace is not None:
            changes["namespace"] = request.namespace
        if request.title is not None:
            changes["title"] = request.title
        if request.type is not None:
            changes["type"] = request.type
        if request.status is not None:
            changes["status"] = request.status
        if request.metadata is not None:
            changes["metadata"] = request.metadata
        if changes:
            self.repo.update_knowledge(knowledge_id, changes)
        if request.documents is not None:
            self.repo.replace_documents(knowledge_id, _pairs(request.documents))
        result = self.repo.get(knowledge_id)
        if result is None:
            raise NotFoundError(str(knowledge_id))
        return result

    def delete(self, knowledge_id: uuid.UUID) -> dict:
        if self.repo.get(knowledge_id) is None:
            raise NotFoundError(str(knowledge_id))
        return self.repo.soft_delete(knowledge_id)

    # -- queries ---------------------------------------------------------- #
    def get(self, knowledge_id: uuid.UUID) -> dict:
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
    ) -> list[dict]:
        return self.repo.list(
            namespace=namespace,
            type=type,
            status=status,
            limit=self._resolve_limit(limit),
        )

    def search(self, request: SearchRequest) -> list[dict]:
        return self.repo.search(
            query=request.query,
            namespace=request.namespace,
            limit=self._resolve_limit(request.limit),
        )
