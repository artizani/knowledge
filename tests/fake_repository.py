"""In-memory fake repository for fast API tests without external services."""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from app.repository import DocumentPair


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeKnowledgeRepository:
    """Drop-in fake for :class:`app.repository.KnowledgeRepository`.

    Stores records in memory. Supports the same create/read/update/delete/search
    interface so the service layer and API tests can run offline.
    """

    def __init__(self) -> None:
        self._knowledge: dict[str, dict] = {}
        self._documents: dict[str, list[dict]] = {}

    def create_knowledge(
        self,
        *,
        namespace: str,
        title: str,
        type: str,
        status: str,
        metadata: dict | None = None,
    ) -> dict:
        kid = str(uuid.uuid4())
        now = _utcnow()
        record = {
            "id": kid,
            "namespace": namespace,
            "title": title,
            "type": type,
            "status": status,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        self._knowledge[kid] = record
        self._documents[kid] = []
        return dict(record)

    def create_documents(
        self, knowledge_id: str, documents: Sequence[DocumentPair]
    ) -> list[dict]:
        created = []
        for name, content in documents:
            doc = {
                "id": str(uuid.uuid4()),
                "knowledge_id": knowledge_id,
                "name": name,
                "content": content,
                "created_at": _utcnow(),
            }
            self._documents.setdefault(knowledge_id, []).append(doc)
            created.append(dict(doc))
        return created

    def replace_documents(
        self, knowledge_id: uuid.UUID, documents: Sequence[DocumentPair]
    ) -> list[dict]:
        kid = str(knowledge_id)
        self._documents[kid] = []
        return self.create_documents(kid, documents)

    def update_knowledge(self, knowledge_id: uuid.UUID, changes: dict) -> dict:
        kid = str(knowledge_id)
        record = self._knowledge[kid]
        record.update(changes)
        record["updated_at"] = _utcnow()
        return dict(record)

    def soft_delete(self, knowledge_id: uuid.UUID) -> dict:
        return self.update_knowledge(knowledge_id, {"deleted_at": _utcnow()})

    def get(self, knowledge_id: uuid.UUID) -> dict | None:
        kid = str(knowledge_id)
        record = self._knowledge.get(kid)
        if record is None or record["deleted_at"] is not None:
            return None
        result = dict(record)
        result["documents"] = [dict(d) for d in self._documents.get(kid, [])]
        return result

    def list(
        self,
        *,
        namespace: str | None = None,
        type: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        results = []
        for record in sorted(
            self._knowledge.values(),
            key=lambda r: r["created_at"],
            reverse=True,
        ):
            if record["deleted_at"] is not None:
                continue
            if namespace and record["namespace"] != namespace:
                continue
            if type and record["type"] != type:
                continue
            if status and record["status"] != status:
                continue
            item = dict(record)
            item["documents"] = [dict(d) for d in self._documents.get(record["id"], [])]
            results.append(item)
        if limit is not None:
            results = results[:limit]
        return results

    def search(
        self,
        *,
        query: str,
        namespace: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        q = query.lower()
        results = []
        for item in self.list(namespace=namespace, limit=None):
            if q in item["title"].lower():
                results.append(item)
                continue
            for doc in item.get("documents", []):
                if q in doc["content"].lower():
                    results.append(item)
                    break
        if limit is not None:
            results = results[:limit]
        return results

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass
