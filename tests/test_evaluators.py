"""Tests for evalops.evaluators (ExactMatch, Contains, RegexMatch)."""

from __future__ import annotations

import pytest

from evalops.domain.contracts import Evaluator
from evalops.domain.entities import DatasetCase, EvaluationRun
from evalops.domain.enums import EvaluatorFamily
from evalops.errors import ConfigError
from evalops.evaluators import Contains, ExactMatch, RegexMatch


def _run(output: str) -> EvaluationRun:
    return EvaluationRun(
        experiment_id="e",
        system_version_id="sv",
        case_id="c",
        repeat_index=0,
        output=output,
    )


def _ref(expected: str | None) -> DatasetCase:
    return DatasetCase(input="q", expected_output=expected, id="case-1")


def test_each_evaluator_satisfies_the_protocol() -> None:
    for evaluator in (ExactMatch(), Contains(), RegexMatch(pattern="x")):
        typed: Evaluator = evaluator
        assert isinstance(typed, Evaluator)


class TestExactMatch:
    def test_pass_produces_a_deterministic_family_score(self) -> None:
        score = ExactMatch().evaluate(_run("4"), _ref("4"))

        assert score.evaluator == "exact_match"
        assert score.family is EvaluatorFamily.DETERMINISTIC
        assert (score.score, score.passed) == (1.0, True)

    def test_surrounding_whitespace_is_ignored(self) -> None:
        assert ExactMatch().evaluate(_run("  4\n"), _ref("4")).passed is True

    def test_case_sensitive_by_default(self) -> None:
        assert ExactMatch().evaluate(_run("Paris"), _ref("paris")).passed is False

    def test_case_insensitive_when_configured(self) -> None:
        assert (
            ExactMatch(case_sensitive=False).evaluate(_run("Paris"), _ref("paris")).passed is True
        )

    def test_fail_scores_zero(self) -> None:
        score = ExactMatch().evaluate(_run("5"), _ref("4"))

        assert (score.score, score.passed) == (0.0, False)

    def test_missing_expected_output_raises_config_error(self) -> None:
        with pytest.raises(ConfigError):
            ExactMatch().evaluate(_run("4"), _ref(None))


class TestContains:
    def test_substring_of_output_passes(self) -> None:
        assert Contains().evaluate(_run("The capital is Paris."), _ref("Paris")).passed is True

    def test_case_insensitive_by_default(self) -> None:
        assert Contains().evaluate(_run("the capital is paris"), _ref("Paris")).passed is True

    def test_case_sensitive_when_configured(self) -> None:
        result = Contains(case_sensitive=True).evaluate(_run("the capital is paris"), _ref("Paris"))
        assert result.passed is False

    def test_missing_substring_fails(self) -> None:
        assert Contains().evaluate(_run("London"), _ref("Paris")).passed is False

    def test_whitespace_is_not_normalised(self) -> None:
        # Documented: only ExactMatch strips; Contains does a literal substring test.
        assert Contains().evaluate(_run("Paris"), _ref(" Paris ")).passed is False

    def test_missing_expected_output_raises_config_error(self) -> None:
        with pytest.raises(ConfigError):
            Contains().evaluate(_run("Paris"), _ref(None))


class TestRegexMatch:
    def test_match_passes(self) -> None:
        score = RegexMatch(pattern=r"^\d+$").evaluate(_run("42"), _ref(None))

        assert score.evaluator == "regex_match"
        assert score.family is EvaluatorFamily.DETERMINISTIC
        assert (score.score, score.passed) == (1.0, True)

    def test_non_match_fails(self) -> None:
        assert RegexMatch(pattern=r"^\d+$").evaluate(_run("forty"), _ref(None)).passed is False

    def test_uses_search_not_fullmatch(self) -> None:
        assert RegexMatch(pattern=r"\d+").evaluate(_run("abc123"), _ref(None)).passed is True

    def test_does_not_require_expected_output(self) -> None:
        # _ref(None) has no expected_output and this must not raise.
        RegexMatch(pattern=r".").evaluate(_run("x"), _ref(None))

    def test_name_can_be_overridden(self) -> None:
        score = RegexMatch(pattern=r"\d", name="has_digit").evaluate(_run("a1"), _ref(None))

        assert score.evaluator == "has_digit"

    def test_invalid_pattern_is_rejected_at_construction(self) -> None:
        with pytest.raises(ConfigError):
            RegexMatch(pattern="(unclosed")
