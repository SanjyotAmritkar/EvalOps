"""Tests for evalops.domain.entities.DatasetCase."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from evalops.domain.entities import DatasetCase
from evalops.domain.enums import CaseOrigin
from evalops.domain.errors import DomainValidationError


def test_authored_case_is_the_default() -> None:
    case = DatasetCase(input="What is 2 + 2?", expected_output="4")

    assert case.origin is CaseOrigin.AUTHORED
    assert case.source_trace_id is None
    assert len(case.id) == 32


def test_expected_output_is_optional() -> None:
    case = DatasetCase(input="Summarize the passage.")

    assert case.expected_output is None


def test_promoted_trace_case_requires_a_source_trace_id() -> None:
    case = DatasetCase(
        input="prod query",
        origin=CaseOrigin.PROMOTED_TRACE,
        source_trace_id="trace-42",
    )

    assert case.source_trace_id == "trace-42"


def test_promoted_trace_without_source_trace_id_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        DatasetCase(input="prod query", origin=CaseOrigin.PROMOTED_TRACE)


def test_authored_case_with_source_trace_id_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        DatasetCase(input="q", source_trace_id="trace-1")


def test_blank_input_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        DatasetCase(input="   ")


def test_is_immutable() -> None:
    case = DatasetCase(input="q")

    with pytest.raises(FrozenInstanceError):
        case.input = "other"  # type: ignore[misc]


def test_expected_retrieval_ids_default_empty_and_normalise_to_tuple() -> None:
    assert DatasetCase(input="q").expected_retrieval_ids == ()
    case = DatasetCase(input="q", expected_retrieval_ids=["d1", "d2"])  # type: ignore[arg-type]
    assert case.expected_retrieval_ids == ("d1", "d2")


def test_blank_expected_retrieval_id_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        DatasetCase(input="q", expected_retrieval_ids=("d1", "  "))
