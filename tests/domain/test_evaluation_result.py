"""Tests for evalops.domain.entities.EvaluationResult."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from evalops.domain.entities import EvaluationResult
from evalops.domain.errors import DomainValidationError
from evalops.domain.value_objects import MetricComparison


def _metric(name: str) -> MetricComparison:
    return MetricComparison(metric=name, baseline_value=1.0, candidate_value=1.0)


def test_valid_evaluation_result_holds_its_metrics() -> None:
    result = EvaluationResult(
        experiment_id="exp-1", metrics=(_metric("quality"), _metric("cost_usd"))
    )

    assert isinstance(result.metrics, tuple)
    assert len(result.metrics) == 2
    assert result.created_at.tzinfo is not None


def test_empty_metrics_are_allowed() -> None:
    result = EvaluationResult(experiment_id="exp-1", metrics=())

    assert result.metrics == ()


def test_duplicate_metric_names_are_rejected() -> None:
    with pytest.raises(DomainValidationError):
        EvaluationResult(experiment_id="exp-1", metrics=(_metric("quality"), _metric("quality")))


def test_blank_experiment_id_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        EvaluationResult(experiment_id="  ", metrics=())


def test_naive_created_at_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        EvaluationResult(experiment_id="exp-1", metrics=(), created_at=datetime(2024, 1, 1))


def test_is_immutable() -> None:
    result = EvaluationResult(experiment_id="exp-1", metrics=())

    with pytest.raises(FrozenInstanceError):
        result.experiment_id = "other"  # type: ignore[misc]
