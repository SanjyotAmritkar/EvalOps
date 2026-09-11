"""Structured logging: JSON shape, context merge, redaction, reserved-name safety."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from evalops.obs.context import correlation_scope
from evalops.obs.logging import (
    ConsoleFormatter,
    JsonFormatter,
    get_logger,
    log_event,
)
from evalops.obs.redact import redact, safe_error


def _record(**fields: Any) -> logging.LogRecord:
    logger = get_logger("test")
    captured: list[logging.LogRecord] = []

    class _Grab(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = _Grab(level=logging.DEBUG)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        log_event(logger, "unit_event", level=logging.INFO, **fields)
    finally:
        logger.removeHandler(handler)
    assert len(captured) == 1
    return captured[0]


def test_json_formatter_emits_one_object_with_core_fields() -> None:
    with correlation_scope(request_id="r1", experiment_id="e1"):
        record = _record(duration_ms=12.5, status="success")
    line = JsonFormatter().format(record)
    obj = json.loads(line)

    assert obj["event"] == "unit_event"
    assert obj["level"] == "INFO"
    assert obj["logger"] == "evalops.test"
    assert obj["request_id"] == "r1"
    assert obj["experiment_id"] == "e1"
    assert obj["duration_ms"] == 12.5
    assert obj["status"] == "success"
    assert "timestamp" in obj


def test_console_formatter_is_a_single_readable_line() -> None:
    record = _record(job_id="j1")
    line = ConsoleFormatter().format(record)
    assert "\n" not in line
    assert "unit_event" in line
    assert "job_id=j1" in line


def test_context_fields_are_merged_without_being_passed_explicitly() -> None:
    with correlation_scope(request_id="abc", job_id="job-9", celery_task_id="task-9"):
        record = _record()
    payload = record.evalops_payload  # type: ignore[attr-defined]
    assert payload["request_id"] == "abc"
    assert payload["job_id"] == "job-9"
    assert payload["celery_task_id"] == "task-9"


def test_reserved_logrecord_names_never_raise_and_are_dropped() -> None:
    # 'message', 'name', 'levelname', 'args' are reserved; passing them must not
    # raise a KeyError from logging's ``extra`` handling.
    record = _record(message="should be ignored", name="nope", args="nope", safe_field="kept")
    payload = record.evalops_payload  # type: ignore[attr-defined]
    assert payload["safe_field"] == "kept"
    assert "message" not in payload and "name" not in payload


def test_string_values_are_redacted_and_bounded() -> None:
    record = _record(detail="authorization: Bearer sk-secret-abc123def456 tail")
    payload = record.evalops_payload  # type: ignore[attr-defined]
    assert "sk-secret-abc123def456" not in payload["detail"]
    assert "***" in payload["detail"]


@pytest.mark.parametrize(
    ("raw", "gone"),
    [
        ("api_key=sk-abcdef123456", "sk-abcdef123456"),
        ('{"authorization": "Bearer tok_live_9999"}', "tok_live_9999"),
        ("password: hunter2moremore", "hunter2moremore"),
        ("sk-ant-api03-ABCDEFGHIJKL", "ABCDEFGHIJKL"),
    ],
)
def test_redact_masks_credential_shapes(raw: str, gone: str) -> None:
    assert gone not in redact(raw)


def test_safe_error_is_type_plus_bounded_message() -> None:
    out = safe_error(ValueError("key=sk-should-not-appear-here " + "x" * 900), limit=50)
    assert out.startswith("ValueError: ")
    assert "sk-should-not-appear-here" not in out
    assert len(out) <= len("ValueError: ") + 50
