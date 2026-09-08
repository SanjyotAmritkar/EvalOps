"""Tests for evalops.domain.entities.CaseResult."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from evalops.domain.entities import CaseResult
from evalops.domain.enums import EvaluatorFamily
from evalops.domain.errors import DomainValidationError
from evalops.domain.value_objects import EvaluatorScore


def _score(name: str) -> EvaluatorScore:
    return EvaluatorScore(evaluator=name, family=EvaluatorFamily.DETERMINISTIC, score=1.0)


def test_valid_case_result_holds_its_scores() -> None:
    result = CaseResult(run_id="run-1", scores=(_score("exact_match"), _score("regex")))

    assert isinstance(result.scores, tuple)
    assert len(result.scores) == 2
    assert result.created_at.tzinfo is not None


def test_empty_scores_are_allowed() -> None:
    result = CaseResult(run_id="run-1", scores=())

    assert result.scores == ()


def test_duplicate_evaluator_names_are_rejected() -> None:
    with pytest.raises(DomainValidationError):
        CaseResult(run_id="run-1", scores=(_score("exact_match"), _score("exact_match")))


def test_blank_run_id_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        CaseResult(run_id="  ", scores=())


def test_is_immutable() -> None:
    result = CaseResult(run_id="run-1", scores=())

    with pytest.raises(FrozenInstanceError):
        result.run_id = "other"  # type: ignore[misc]
