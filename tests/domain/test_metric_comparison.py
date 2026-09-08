"""Tests for evalops.domain.value_objects.MetricComparison."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from evalops.domain.errors import DomainValidationError
from evalops.domain.value_objects import MetricComparison


def test_delta_and_relative_delta_are_derived() -> None:
    comparison = MetricComparison(
        metric="latency_p95_ms", baseline_value=200.0, candidate_value=250.0
    )

    assert comparison.delta == 50.0
    assert comparison.relative_delta == 0.25


def test_relative_delta_is_none_when_baseline_is_zero() -> None:
    comparison = MetricComparison(
        metric="safety_violations", baseline_value=0.0, candidate_value=3.0
    )

    assert comparison.delta == 3.0
    assert comparison.relative_delta is None


def test_blank_metric_name_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        MetricComparison(metric="   ", baseline_value=1.0, candidate_value=1.0)


def test_is_immutable() -> None:
    comparison = MetricComparison(metric="cost_usd", baseline_value=1.0, candidate_value=1.1)

    with pytest.raises(FrozenInstanceError):
        comparison.candidate_value = 2.0  # type: ignore[misc]
