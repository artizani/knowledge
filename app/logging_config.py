"""Structured JSON logging for CloudWatch.

Logs are written as single-line JSON to stdout; AWS Lambda forwards stdout to
CloudWatch Logs. No database logging (per spec).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

LOGGER_NAME = "knowledge"

# LogRecord attributes that are not part of our structured "extra" payload.
_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Render a :class:`logging.LogRecord` as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge structured fields passed via ``extra=``.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure and return the application logger (idempotent)."""

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    else:
        for handler in logger.handlers:
            handler.setFormatter(JsonFormatter())
    return logger


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    return logging.getLogger(name)
