"""Sanitisation for anything that reaches a log line.

The rule (see ``docs/ARCHITECTURE.md`` observability section): identifiers,
exception *types*, provider names and operation names are safe; API keys,
``Authorization`` values, cookies, prompts, model output, dataset content and
external-provider response bodies are not. These helpers bound length and strip
the credential shapes that occasionally end up inside an exception message.
"""

from __future__ import annotations

import re

_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # OpenAI / Anthropic style keys: sk-..., sk-ant-..., rk-..., pk-...
    (re.compile(r"(?i)\b((?:sk|rk|pk)-(?:ant-)?)[A-Za-z0-9_\-]{6,}"), r"\1***"),
    # HTTP auth schemes: "Bearer <token>", "Token <token>", "Basic <blob>"
    (re.compile(r"(?i)\b(bearer|token|basic)\s+[A-Za-z0-9._\-+/=]{6,}"), r"\1 ***"),
    # key=VALUE / "authorization": "VALUE" / api_key: VALUE
    (
        re.compile(
            r"(?i)(authorization|api[_-]?key|access[_-]?token|secret|password)"
            r"([\"'\s:=]+)[^\s\"',}\]]+"
        ),
        r"\1\2***",
    ),
)

#: Hard cap on any single sanitised string that goes to a log.
DEFAULT_LIMIT = 500


def redact(text: str) -> str:
    """Mask credential-shaped substrings. Idempotent."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def safe_str(value: object, *, limit: int = DEFAULT_LIMIT) -> str:
    """A bounded, credential-stripped, single-line rendering of ``value``."""
    text = redact(" ".join(str(value).split()))
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def safe_error(exc: BaseException, *, limit: int = DEFAULT_LIMIT) -> str:
    """``"ExceptionType: bounded, redacted message"`` -- never a raw payload."""
    message = safe_str(exc, limit=limit)
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def error_type(exc: BaseException) -> str:
    """The exception's class name (always safe to log)."""
    return type(exc).__name__
