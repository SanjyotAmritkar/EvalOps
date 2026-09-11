"""Centralised structured logging for backend runtime code.

One coherent layer, standard library only -- no logging framework dependency.

* :func:`configure_logging` installs a single stdout handler on the root logger.
  ``EVALOPS_LOG_FORMAT=json`` (the default) emits one JSON object per line;
  ``console`` emits a compact human line for local development.
* :func:`log_event` is the only call site helper. It takes a **stable event
  name** (``http_request_completed``, ``provider_call_completed`` …) plus
  structured fields, merges the correlation context, and stashes the whole
  payload on the record so both the formatter and ``caplog`` can read it.

Callers pass identifiers, durations, provider names and outcomes -- never
prompts, outputs, dataset rows, keys or response bodies. Values are coerced to
JSON-safe scalars; strings are length-bounded and credential-stripped by
:mod:`evalops.obs.redact`.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from evalops.obs.context import get_context
from evalops.obs.redact import safe_str
from evalops.obs.settings import ObservabilitySettings

#: LogRecord attributes we must not overwrite via ``extra=``.
_RESERVED = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

#: Attribute names this module stashes its structured payload under.
_PAYLOAD_ATTR = "evalops_payload"
_EVENT_ATTR = "evalops_event"

_configured = False


def _coerce(value: Any) -> Any:
    if isinstance(value, bool | int | float) or value is None:
        return value
    if isinstance(value, str):
        return safe_str(value)
    return safe_str(value)


class JsonFormatter(logging.Formatter):
    """One JSON object per line: timestamp, level, logger, then the event payload."""

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }
        payload = getattr(record, _PAYLOAD_ATTR, None)
        if isinstance(payload, dict):
            out.update(payload)
        else:
            out["event"] = record.getMessage()
        if record.exc_info and record.exc_info[0] is not None:
            out.setdefault("error_type", record.exc_info[0].__name__)
        return json.dumps(out, default=str, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    """Compact single line for local dev: ``HH:MM:SS LEVEL event key=value``."""

    def format(self, record: logging.LogRecord) -> str:
        stamp = datetime.fromtimestamp(record.created, tz=UTC).strftime("%H:%M:%S")
        payload = dict(getattr(record, _PAYLOAD_ATTR, {}) or {})
        event = payload.pop("event", None) or record.getMessage()
        pairs = " ".join(f"{k}={v}" for k, v in payload.items())
        line = f"{stamp} {record.levelname:<5} {event}"
        if pairs:
            line = f"{line}  {pairs}"
        if record.exc_info and record.exc_info[0] is not None:
            line = f"{line}  error_type={record.exc_info[0].__name__}"
        return line


def configure_logging(*, force: bool = False) -> None:
    """Install the structured handler on the root logger. Idempotent."""
    global _configured
    # Defensive: a third-party ``logging.config.fileConfig`` / ``dictConfig`` run
    # (Alembic, gunicorn, …) with ``disable_existing_loggers=True`` would silently
    # set ``.disabled`` on the ``evalops`` logger tree. Clear it on every call.
    logging.getLogger("evalops").disabled = False
    for _name, _logger in logging.root.manager.loggerDict.items():
        if _name.startswith("evalops.") and isinstance(_logger, logging.Logger):
            _logger.disabled = False

    if _configured and not force:
        return

    settings = ObservabilitySettings.from_env()
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.log_format == "json" else ConsoleFormatter())

    root = logging.getLogger()
    # Drop only handlers this module previously installed, so pytest's caplog and
    # any host handler survive a reconfigure.
    for existing in list(root.handlers):
        if getattr(existing, "_evalops_handler", False):
            root.removeHandler(existing)
    handler._evalops_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)

    level = getattr(logging, settings.log_level, logging.INFO)
    # Root stays at WARNING so third-party INFO chatter (httpx, celery, botocore…)
    # is filtered; the ``evalops`` tree logs at the configured level and its
    # records still reach the root handler by propagation.
    root.setLevel(max(level, logging.WARNING))
    logging.getLogger("evalops").setLevel(level)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """A namespaced logger (``evalops.<name>`` unless already dotted under it)."""
    if name == "evalops" or name.startswith("evalops."):
        return logging.getLogger(name)
    return logging.getLogger(f"evalops.{name}")


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    """Emit one structured event.

    ``event`` is a stable machine name. ``fields`` are structured values (drop
    ``None``); the correlation context is merged in automatically. Reserved
    ``LogRecord`` names are namespaced so ``extra=`` never raises.
    """
    payload: dict[str, Any] = {"event": event}
    payload.update(get_context())
    for key, value in fields.items():
        if value is None or key in _RESERVED:
            continue
        payload[key] = _coerce(value)
    logger.log(
        level,
        event,
        extra={_EVENT_ATTR: event, _PAYLOAD_ATTR: payload},
        exc_info=exc_info,
    )
