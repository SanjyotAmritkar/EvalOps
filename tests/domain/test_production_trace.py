"""Tests for evalops.domain.entities.ProductionTrace."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime
from typing import Any

import pytest

from evalops.domain.entities import ProductionTrace
from evalops.domain.enums import TraceOrigin
from evalops.domain.errors import DomainValidationError

VALID_KWARGS: dict[str, Any] = {
    "project_id": "proj-1",
    "system_version_id": "sv-1",
    "input": "How do I reset my password?",
}


def test_minimal_trace_defaults() -> None:
    trace = ProductionTrace(**VALID_KWARGS)

    assert trace.output == ""
    assert trace.reference_output is None
    assert trace.metadata == {}
    assert trace.latency_ms is None
    assert trace.cost_usd is None
    assert trace.error is None
    assert trace.origin is TraceOrigin.PRODUCTION
    assert len(trace.id) == 32
    assert trace.created_at.tzinfo is not None


def test_full_trace_keeps_every_field() -> None:
    trace = ProductionTrace(
        **VALID_KWARGS,
        output="Use the reset link on the login page.",
        reference_output="Click 'Forgot password' and follow the email.",
        metadata={"conversation_id": "c-9", "channel": "web"},
        latency_ms=1234.5,
        cost_usd=0.0021,
        error=None,
    )

    assert trace.output.startswith("Use the reset link")
    assert trace.reference_output is not None
    assert trace.metadata == {"conversation_id": "c-9", "channel": "web"}
    assert trace.latency_ms == 1234.5
    assert trace.cost_usd == 0.0021


def test_trace_can_record_a_failed_interaction() -> None:
    trace = ProductionTrace(**VALID_KWARGS, output="", error="provider timeout after 30s")

    assert trace.error == "provider timeout after 30s"
    assert trace.output == ""


@pytest.mark.parametrize("field_name", ["project_id", "system_version_id", "input"])
def test_blank_required_string_is_rejected(field_name: str) -> None:
    with pytest.raises(DomainValidationError):
        ProductionTrace(**{**VALID_KWARGS, field_name: "   "})


def test_blank_error_string_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        ProductionTrace(**VALID_KWARGS, error="   ")


@pytest.mark.parametrize("field_name", ["latency_ms", "cost_usd"])
def test_negative_latency_or_cost_is_rejected(field_name: str) -> None:
    kwargs: dict[str, Any] = {**VALID_KWARGS, field_name: -0.1}
    with pytest.raises(DomainValidationError):
        ProductionTrace(**kwargs)


def test_zero_latency_and_cost_are_allowed() -> None:
    trace = ProductionTrace(**VALID_KWARGS, latency_ms=0.0, cost_usd=0.0)
    assert trace.latency_ms == 0.0
    assert trace.cost_usd == 0.0


def test_non_trace_origin_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        ProductionTrace(**VALID_KWARGS, origin="production")  # type: ignore[arg-type]


def test_naive_created_at_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        ProductionTrace(**VALID_KWARGS, created_at=datetime(2024, 1, 1))


def test_metadata_does_not_alias_the_callers_dict() -> None:
    mutable = {"k": "v"}
    trace = ProductionTrace(**VALID_KWARGS, metadata=mutable)

    mutable["k"] = "changed"
    assert trace.metadata == {"k": "v"}


def test_metadata_mapping_is_read_only() -> None:
    trace = ProductionTrace(**VALID_KWARGS, metadata={"k": "v"})

    with pytest.raises(TypeError):
        trace.metadata["k"] = "x"  # type: ignore[index]


def test_is_immutable() -> None:
    trace = ProductionTrace(**VALID_KWARGS)

    with pytest.raises(FrozenInstanceError):
        trace.output = "other"  # type: ignore[misc]
