"""Domain-level exceptions shared across the application."""
from __future__ import annotations


class KnowledgeError(Exception):
    """Base class for domain errors."""


class NotFoundError(KnowledgeError):
    """Raised when a knowledge record does not exist (or is soft-deleted)."""


class AuthError(KnowledgeError):
    """Raised when authentication fails."""
