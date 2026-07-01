"""Tests for Pydantic request/response schemas and validation rules."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


def test_capture_request_valid(sample_capture_payload):
    from app.schemas import CaptureRequest

    req = CaptureRequest.model_validate(sample_capture_payload)
    assert req.namespace == "icebox"
    assert req.title == "Life Weeks"
    assert req.type == "idea"
    assert req.status == "research"
    assert len(req.documents) == 2
    assert req.metadata["createdBy"] == "ChatGPT"


def test_capture_request_metadata_and_documents_default():
    from app.schemas import CaptureRequest

    req = CaptureRequest.model_validate(
        {"namespace": "ns", "title": "T", "type": "note", "status": "inbox"}
    )
    assert req.metadata == {}
    assert req.documents == []


def test_capture_request_strips_whitespace():
    from app.schemas import CaptureRequest

    req = CaptureRequest.model_validate(
        {"namespace": " ns ", "title": "  T  ", "type": "note", "status": "inbox"}
    )
    assert req.namespace == "ns"
    assert req.title == "T"


@pytest.mark.parametrize("field", ["namespace", "title", "type", "status"])
def test_capture_request_missing_required(sample_capture_payload, field):
    from app.schemas import CaptureRequest

    payload = dict(sample_capture_payload)
    payload.pop(field)
    with pytest.raises(ValidationError):
        CaptureRequest.model_validate(payload)


@pytest.mark.parametrize("field", ["namespace", "title"])
def test_capture_request_blank_string_rejected(sample_capture_payload, field):
    from app.schemas import CaptureRequest

    payload = dict(sample_capture_payload)
    payload[field] = "   "
    with pytest.raises(ValidationError):
        CaptureRequest.model_validate(payload)


def test_capture_request_invalid_type(sample_capture_payload):
    from app.schemas import CaptureRequest

    payload = dict(sample_capture_payload)
    payload["type"] = "not-a-type"
    with pytest.raises(ValidationError):
        CaptureRequest.model_validate(payload)


def test_capture_request_invalid_status(sample_capture_payload):
    from app.schemas import CaptureRequest

    payload = dict(sample_capture_payload)
    payload["status"] = "not-a-status"
    with pytest.raises(ValidationError):
        CaptureRequest.model_validate(payload)


def test_all_spec_types_and_statuses_accepted():
    from app.constants import KNOWLEDGE_STATUSES, KNOWLEDGE_TYPES
    from app.schemas import CaptureRequest

    for t in KNOWLEDGE_TYPES:
        for s in KNOWLEDGE_STATUSES:
            CaptureRequest.model_validate(
                {"namespace": "ns", "title": "T", "type": t, "status": s}
            )


def test_document_in_requires_name():
    from app.schemas import DocumentIn

    with pytest.raises(ValidationError):
        DocumentIn.model_validate({"name": "  ", "content": "x"})


def test_document_in_allows_empty_content():
    from app.schemas import DocumentIn

    doc = DocumentIn.model_validate({"name": "empty.md", "content": ""})
    assert doc.content == ""


def test_search_request_requires_query():
    from app.schemas import SearchRequest

    with pytest.raises(ValidationError):
        SearchRequest.model_validate({"query": "   "})

    req = SearchRequest.model_validate({"query": "PAYE"})
    assert req.query == "PAYE"


def test_update_request_all_optional():
    from app.schemas import UpdateRequest

    req = UpdateRequest.model_validate({})
    assert req.title is None
    assert req.documents is None
    assert req.metadata is None


def test_update_request_invalid_type_rejected():
    from app.schemas import UpdateRequest

    with pytest.raises(ValidationError):
        UpdateRequest.model_validate({"type": "bogus"})


def test_update_request_documents_replacement():
    from app.schemas import UpdateRequest

    req = UpdateRequest.model_validate(
        {"documents": [{"name": "a.md", "content": "a"}]}
    )
    assert req.documents is not None
    assert req.documents[0].name == "a.md"


def test_capture_response_shape():
    from app.schemas import CaptureResponse

    rid = uuid.uuid4()
    resp = CaptureResponse(id=rid, status="captured")
    dumped = resp.model_dump(mode="json")
    assert dumped["id"] == str(rid)
    assert dumped["status"] == "captured"


def test_knowledge_out_serialisation():
    from app.schemas import DocumentOut, KnowledgeOut

    now = datetime.now(timezone.utc)
    kid = uuid.uuid4()
    did = uuid.uuid4()
    out = KnowledgeOut(
        id=kid,
        namespace="ns",
        title="T",
        type="idea",
        status="inbox",
        metadata={"tags": ["a"]},
        created_at=now,
        updated_at=now,
        documents=[
            DocumentOut(id=did, name="spec.md", content="# Spec", created_at=now)
        ],
    )
    dumped = out.model_dump(mode="json")
    assert dumped["id"] == str(kid)
    assert dumped["metadata"] == {"tags": ["a"]}
    assert dumped["documents"][0]["name"] == "spec.md"
