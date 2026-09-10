"""Tests for evalops.domain.value_objects."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from evalops.domain.enums import EvaluatorFamily
from evalops.domain.errors import DomainValidationError
from evalops.domain.value_objects import (
    EvaluatorScore,
    ExpectedToolCall,
    RetrievedItem,
    ToolCall,
    UsageMetrics,
)


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


class TestRetrievedItem:
    def test_valid_item(self) -> None:
        item = RetrievedItem(doc_id="d1", content="text", rank=2, score=0.7)
        assert (item.doc_id, item.rank, item.score) == ("d1", 2, 0.7)
        assert RetrievedItem(doc_id="d1", content="", rank=0).score is None

    def test_blank_doc_id_is_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            RetrievedItem(doc_id="  ", content="x", rank=0)

    def test_negative_rank_is_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            RetrievedItem(doc_id="d1", content="x", rank=-1)

    def test_is_immutable(self) -> None:
        item = RetrievedItem(doc_id="d1", content="x", rank=0)
        with pytest.raises(FrozenInstanceError):
            item.doc_id = "d2"  # type: ignore[misc]


class TestToolCall:
    def test_defaults_and_read_only_arguments(self) -> None:
        tc = ToolCall(name="search")
        assert dict(tc.arguments) == {} and tc.result is None and tc.ok is True
        tc2 = ToolCall(name="search", arguments={"q": "x"})
        with pytest.raises(TypeError):
            tc2.arguments["q"] = "y"  # type: ignore[index]

    def test_arguments_do_not_alias_the_callers_dict(self) -> None:
        mutable = {"q": "x"}
        tc = ToolCall(name="s", arguments=mutable)
        mutable["q"] = "changed"
        assert dict(tc.arguments) == {"q": "x"}

    def test_blank_name_and_ok_with_error_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            ToolCall(name="  ")
        with pytest.raises(DomainValidationError):
            ToolCall(name="s", ok=True, error="boom")
        with pytest.raises(DomainValidationError):
            ToolCall(name="s", ok=False, error="   ")

    def test_failed_call_with_error_is_allowed(self) -> None:
        assert ToolCall(name="s", ok=False, error="denied").error == "denied"


class TestExpectedToolCall:
    def test_name_only_and_with_args(self) -> None:
        assert ExpectedToolCall("search").arguments is None
        e = ExpectedToolCall("search", {"q": "x"})
        assert e.arguments is not None and dict(e.arguments) == {"q": "x"}
        with pytest.raises(TypeError):
            e.arguments["q"] = "y"  # type: ignore[index]

    def test_blank_name_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            ExpectedToolCall("  ")
