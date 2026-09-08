"""Tests for evalops.domain.value_objects."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from evalops.domain.enums import EvaluatorFamily
from evalops.domain.errors import DomainValidationError
from evalops.domain.value_objects import EvaluatorScore, UsageMetrics


class TestUsageMetrics:
    def test_total_tokens_is_prompt_plus_completion(self) -> None:
        usage = UsageMetrics(prompt_tokens=30, completion_tokens=12)

        assert usage.total_tokens == 42

    def test_zero_value_is_valid_for_a_failed_run(self) -> None:
        usage = UsageMetrics()

        assert usage.total_tokens == 0
        assert usage.cost_usd == 0.0
        assert usage.latency_ms == 0.0

    def test_negative_prompt_tokens_are_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            UsageMetrics(prompt_tokens=-1)

    def test_negative_completion_tokens_are_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            UsageMetrics(completion_tokens=-1)

    def test_negative_cost_is_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            UsageMetrics(cost_usd=-0.01)

    def test_negative_latency_is_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            UsageMetrics(latency_ms=-1.0)

    def test_is_immutable(self) -> None:
        usage = UsageMetrics()

        with pytest.raises(FrozenInstanceError):
            usage.cost_usd = 1.0  # type: ignore[misc]


class TestEvaluatorScore:
    def test_constructs_with_family_and_pass_flag(self) -> None:
        score = EvaluatorScore(
            evaluator="exact_match",
            family=EvaluatorFamily.DETERMINISTIC,
            score=1.0,
            passed=True,
        )

        assert score.evaluator == "exact_match"
        assert score.family is EvaluatorFamily.DETERMINISTIC
        assert score.passed is True

    def test_passed_is_optional(self) -> None:
        score = EvaluatorScore(
            evaluator="embedding_similarity",
            family=EvaluatorFamily.STATISTICAL,
            score=0.5,
        )

        assert score.passed is None

    @pytest.mark.parametrize("value", [0.0, 1.0])
    def test_score_bounds_are_inclusive(self, value: float) -> None:
        score = EvaluatorScore(evaluator="x", family=EvaluatorFamily.DETERMINISTIC, score=value)

        assert score.score == value

    @pytest.mark.parametrize("value", [-0.01, 1.01])
    def test_score_outside_the_unit_interval_is_rejected(self, value: float) -> None:
        with pytest.raises(DomainValidationError):
            EvaluatorScore(evaluator="x", family=EvaluatorFamily.DETERMINISTIC, score=value)

    def test_blank_evaluator_name_is_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            EvaluatorScore(evaluator="   ", family=EvaluatorFamily.DETERMINISTIC, score=1.0)

    def test_is_immutable(self) -> None:
        score = EvaluatorScore(
            evaluator="exact_match", family=EvaluatorFamily.DETERMINISTIC, score=1.0
        )

        with pytest.raises(FrozenInstanceError):
            score.score = 0.0  # type: ignore[misc]
