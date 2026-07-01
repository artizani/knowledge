"""Pydantic v2 request and response schemas.

The API surface is deliberately LLM-friendly: plain JSON, Markdown document
bodies, and a flexible ``metadata`` object stored verbatim.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.constants import KNOWLEDGE_STATUS_SET, KNOWLEDGE_TYPE_SET

# A non-empty string that is stripped of surrounding whitespace.
NonEmptyStr = Annotated[str, Field(min_length=1)]


def _validate_type(value: str) -> str:
    if value not in KNOWLEDGE_TYPE_SET:
        allowed = ", ".join(sorted(KNOWLEDGE_TYPE_SET))
        raise ValueError(f"type must be one of: {allowed}")
    return value


def _validate_status(value: str) -> str:
    if value not in KNOWLEDGE_STATUS_SET:
        allowed = ", ".join(sorted(KNOWLEDGE_STATUS_SET))
        raise ValueError(f"status must be one of: {allowed}")
    return value


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #
class DocumentIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: NonEmptyStr
    content: str  # Markdown body; may be empty.


class CaptureRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    namespace: NonEmptyStr
    title: NonEmptyStr
    type: NonEmptyStr
    status: NonEmptyStr
    documents: list[DocumentIn] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    _check_type = field_validator("type")(_validate_type)
    _check_status = field_validator("status")(_validate_status)


class UpdateRequest(BaseModel):
    """Partial update. Any provided field replaces the stored value.

    If ``documents`` is provided the entire document set is replaced.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    namespace: NonEmptyStr | None = None
    title: NonEmptyStr | None = None
    type: NonEmptyStr | None = None
    status: NonEmptyStr | None = None
    documents: list[DocumentIn] | None = None
    metadata: dict | None = None

    @field_validator("type")
    @classmethod
    def _check_type(cls, value: str | None) -> str | None:
        return None if value is None else _validate_type(value)

    @field_validator("status")
    @classmethod
    def _check_status(cls, value: str | None) -> str | None:
        return None if value is None else _validate_status(value)


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: NonEmptyStr
    namespace: str | None = None
    limit: int | None = Field(default=None, ge=1, le=1000)


# --------------------------------------------------------------------------- #
# Responses
# --------------------------------------------------------------------------- #
class CaptureResponse(BaseModel):
    id: uuid.UUID
    status: str = "captured"


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    content: str
    created_at: datetime


class KnowledgeOut(BaseModel):
    # ``populate_by_name`` + ``AliasChoices`` lets this model be built both from
    # the ORM object (attribute ``meta``) and from a plain dict (key
    # ``metadata``), while always serialising back out as ``metadata``.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    namespace: str
    title: str
    type: str
    status: str
    metadata: dict = Field(
        default_factory=dict,
        validation_alias=AliasChoices("meta", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime
    documents: list[DocumentOut] = Field(default_factory=list)


class KnowledgeListResponse(BaseModel):
    items: list[KnowledgeOut]
    count: int


class DeleteResponse(BaseModel):
    id: uuid.UUID
    status: str = "deleted"
