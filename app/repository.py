"""Supabase PostgREST data-access layer.

Replaces direct PostgreSQL/SQLAlchemy access. The repository talks to the
Supabase REST API using the service_role key (bypasses RLS) because the public
Knowledge API performs its own authentication and access control.

Tables targeted:
* ``knowledge.knowledge`` — main records
* ``knowledge.documents`` — Markdown source files

Future v2 tables (embeddings, nodes, links) can be added here without changing
the public REST contract.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone

import httpx

DocumentPair = tuple[str, str]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _quote_ilike(query: str) -> str:
    # PostgREST horizontal-filter operators use * as the wildcard.
    escaped = query.replace("\\", "\\\\").replace("*", "\\*").replace("%", "\\%")
    return f"*{escaped}*"


class KnowledgeRepository:
    """Repository for knowledge records backed by Supabase PostgREST."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        service_key: str,
        schema: str = "knowledge",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.service_key = service_key
        self.schema = schema
        self._read_client = httpx.Client(
            base_url=self.base_url,
            headers=self._headers(self.api_key),
            timeout=10.0,
        )
        self._write_client = httpx.Client(
            base_url=self.base_url,
            headers=self._headers(self.service_key),
            timeout=10.0,
        )

    def _headers(self, key: str) -> dict[str, str]:
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept-Profile": self.schema,
            "Content-Profile": self.schema,
        }

    def _check(self, response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"PostgREST error {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc

    def _request(self, client: httpx.Client, method: str, path: str, **kwargs) -> httpx.Response:
        # httpx encodes query params in ways PostgREST doesn't expect (e.g.
        # %2A for *, list suffixes). Build the URL ourselves.
        params = kwargs.pop("params", None)
        url = self.base_url + path
        if params:
            qs_parts = []
            for k, v in params.items():
                # Keep PostgREST operators/raw values intact; only encode
                # characters that are illegal in query strings.
                encoded = httpx.QueryParams({k: v}).__getitem__(k)
                qs_parts.append(f"{k}={encoded}")
            url = url + "?" + "&".join(qs_parts)
        response = client.request(method, url, **kwargs)
        self._check(response)
        return response

    # -- writes ----------------------------------------------------------- #
    def create_knowledge(
        self,
        *,
        namespace: str,
        title: str,
        type: str,
        status: str,
        metadata: dict | None = None,
    ) -> dict:
        payload = {
            "namespace": namespace,
            "title": title,
            "type": type,
            "status": status,
            "metadata": metadata or {},
        }
        response = self._request(
            self._write_client,
            "POST",
            "/knowledge",
            json=payload,
            params={"select": "*"},
            headers={"Prefer": "return=representation"},
        )
        data = response.json()
        return data[0] if isinstance(data, list) else data

    def create_documents(
        self, knowledge_id: str, documents: Iterable[DocumentPair]
    ) -> list[dict]:
        payload = [
            {"knowledge_id": knowledge_id, "name": name, "content": content}
            for name, content in documents
        ]
        if not payload:
            return []
        response = self._request(
            self._write_client,
            "POST",
            "/documents",
            json=payload,
            params={"select": "*"},
            headers={"Prefer": "return=representation"},
        )
        data = response.json()
        return data if isinstance(data, list) else [data]

    def replace_documents(
        self, knowledge_id: uuid.UUID, documents: Sequence[DocumentPair]
    ) -> list[dict]:
        kid = str(knowledge_id)
        self._request(
            self._write_client,
            "DELETE",
            "/documents",
            params={"knowledge_id": f"eq.{kid}"},
        )
        return self.create_documents(kid, documents)

    def update_knowledge(
        self, knowledge_id: uuid.UUID, changes: dict
    ) -> dict:
        kid = str(knowledge_id)
        response = self._request(
            self._write_client,
            "PATCH",
            "/knowledge",
            params={"id": f"eq.{kid}", "select": "*"},
            json=changes,
            headers={"Prefer": "return=representation"},
        )
        data = response.json()
        return data[0] if isinstance(data, list) else data

    def soft_delete(self, knowledge_id: uuid.UUID) -> dict:
        return self.update_knowledge(knowledge_id, {"deleted_at": _utcnow()})

    # -- reads ------------------------------------------------------------ #
    def get(self, knowledge_id: uuid.UUID) -> dict | None:
        kid = str(knowledge_id)
        response = self._request(
            self._read_client,
            "GET",
            "/knowledge",
            params={
                "id": f"eq.{kid}",
                "deleted_at": "is.null",
                "select": "*,documents(*)",
            },
        )
        data = response.json()
        if not data:
            return None
        return data[0] if isinstance(data, list) else data

    def list(
        self,
        *,
        namespace: str | None = None,
        type: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        params: dict = {
            "deleted_at": "is.null",
            "select": "*,documents(*)",
            "order": "created_at.desc",
        }
        if namespace:
            params["namespace"] = f"eq.{namespace}"
        if type:
            params["type"] = f"eq.{type}"
        if status:
            params["status"] = f"eq.{status}"
        if limit is not None:
            params["limit"] = str(limit)
        response = self._request(self._read_client, "GET", "/knowledge", params=params)
        data = response.json()
        return data if isinstance(data, list) else []

    def search(
        self,
        *,
        query: str,
        namespace: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        pattern = _quote_ilike(query)
        params: dict = {
            "or": f"(title.ilike.{pattern},documents.content.ilike.{pattern})",
            "deleted_at": "is.null",
            "select": "*,documents(*)",
            "order": "created_at.desc",
        }
        if namespace:
            params["namespace"] = f"eq.{namespace}"
        if limit is not None:
            params["limit"] = str(limit)
        response = self._request(self._read_client, "GET", "/knowledge", params=params)
        data = response.json()
        return data if isinstance(data, list) else []

    def close(self) -> None:
        self._read_client.close()
        self._write_client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
