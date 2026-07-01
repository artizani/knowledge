"""Tests for structured JSON logging."""
from __future__ import annotations

import json
import logging


def test_json_formatter_outputs_valid_json():
    from app.logging_config import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="knowledge",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-1"
    record.endpoint = "POST /capture"
    record.latency_ms = 12.3
    record.namespace = "icebox"
    record.success = True

    payload = json.loads(formatter.format(record))
    assert payload["message"] == "request"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "req-1"
    assert payload["endpoint"] == "POST /capture"
    assert payload["latency_ms"] == 12.3
    assert payload["namespace"] == "icebox"
    assert payload["success"] is True
    assert "timestamp" in payload


def test_json_formatter_includes_exception():
    from app.logging_config import JsonFormatter

    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="knowledge",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    payload = json.loads(formatter.format(record))
    assert "exception" in payload
    assert "ValueError" in payload["exception"]


def test_configure_logging_is_idempotent():
    from app.logging_config import configure_logging, get_logger

    configure_logging("INFO")
    count_after_first = len(get_logger("knowledge").handlers)
    configure_logging("INFO")
    logger = get_logger("knowledge")
    # Repeated configuration must not add duplicate handlers (avoids double log
    # lines), regardless of any handlers other tests may have attached.
    assert len(logger.handlers) == count_after_first
    assert count_after_first >= 1
    assert logger.level == logging.INFO
