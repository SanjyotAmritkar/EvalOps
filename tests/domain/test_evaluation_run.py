"""Tests for evalops.domain.entities.EvaluationRun."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime
from typing import Any

import pytest

from evalops.domain.entities import EvaluationRun
from evalops.domain.errors import DomainValidationError
from evalops.domain.value_objects import UsageMetrics

VALID_KWARGS: dict[str, Any] = {
    "experiment_id": "exp-1",
    "system_version_id": "sv-1",
    "case_id": "case-1",
    "repeat_index": 0,
    "output": "4",
}


def test_successful_run_carries_output_and_usage() -> None:
    run = EvaluationRun(**VALID_KWARGS, usage=UsageMetrics(prompt_tokens=5, completion_tokens=1))

    assert run.error is None
    assert run.output == "4"
    assert run.usage.total_tokens == 6
    assert run.created_at.tzinfo is not None


def test_failed_run_has_error_and_zero_usage_by_default() -> None:
    run = EvaluationRun(
        experiment_id="exp-1",
        system_version_id="sv-1",
        case_id="case-1",
        repeat_index=2,
        output="",
        error="provider timeout",
    )

    assert run.error == "provider timeout"
    assert run.usage.total_tokens == 0


def test_negative_repeat_index_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        EvaluationRun(**{**VALID_KWARGS, "repeat_index": -1})


def test_blank_error_string_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        EvaluationRun(**VALID_KWARGS, error="   ")


@pytest.mark.parametrize("field_name", ["experiment_id", "system_version_id", "case_id"])
def test_blank_required_reference_is_rejected(field_name: str) -> None:
    kwargs = {**VALID_KWARGS, field_name: "  "}

    with pytest.raises(DomainValidationError):
        EvaluationRun(**kwargs)


def test_naive_created_at_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        EvaluationRun(**VALID_KWARGS, created_at=datetime(2024, 1, 1))


def test_is_immutable() -> None:
    run = EvaluationRun(**VALID_KWARGS)

    with pytest.raises(FrozenInstanceError):
        run.output = "other"  # type: ignore[misc]


def test_retrieval_defaults_empty_and_normalises_to_tuple() -> None:
    from evalops.domain.value_objects import RetrievedItem

    assert EvaluationRun(**VALID_KWARGS).retrieval == ()
    items = [RetrievedItem(doc_id="d1", content="x", rank=0)]
    run = EvaluationRun(**VALID_KWARGS, retrieval=items)  # type: ignore[arg-type]
    assert run.retrieval == tuple(items)
    assert isinstance(run.retrieval, tuple)
