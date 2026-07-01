"""Controlled vocabularies from the spec.

These are code-level constants, not database constraints -- adding a new type
or status is a one-line change here and requires **no database migration**,
satisfying the spec's "adding new document types requires no database changes".
Namespaces are intentionally *not* enumerated: they are free-form so new
products need no code or schema changes.
"""
from __future__ import annotations

# Types (spec: "Types")
KNOWLEDGE_TYPES: tuple[str, ...] = (
    "idea",
    "spec",
    "decision",
    "research",
    "meeting",
    "architecture",
    "roadmap",
    "bug",
    "task",
    "note",
)

# Status (spec: "Status")
KNOWLEDGE_STATUSES: tuple[str, ...] = (
    "inbox",
    "research",
    "validated",
    "building",
    "completed",
    "archived",
)

KNOWLEDGE_TYPE_SET = frozenset(KNOWLEDGE_TYPES)
KNOWLEDGE_STATUS_SET = frozenset(KNOWLEDGE_STATUSES)
