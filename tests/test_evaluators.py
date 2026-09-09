"""Tests for evalops.evaluators (ExactMatch, Contains, RegexMatch, and the
llm_judge spec branch of build_evaluators)."""

from __future__ import annotations

import pytest

from evalops.cloud_providers import OpenAIProvider
from evalops.domain.contracts import Evaluator
from evalops.domain.entities import DatasetCase, EvaluationRun
from evalops.domain.enums import EvaluatorFamily, ProviderName
from evalops.errors import ConfigError
from evalops.evaluators import Contains, ExactMatch, RegexMatch, build_evaluators
from evalops.judge import LLMJudge
from evalops.ollama import OllamaProvider


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


class TestLLMJudgeSpec:
    def test_builds_an_llm_judge_with_its_own_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        (judge,) = build_evaluators(
            [{"type": "llm_judge", "provider": "openai", "model": "gpt-4o-mini", "name": "j"}]
        )
        assert isinstance(judge, LLMJudge)
        assert judge.name == "j"
        assert judge.provider_name is ProviderName.OPENAI
        assert isinstance(judge.provider_client, OpenAIProvider)
        assert judge.family is EvaluatorFamily.LLM_JUDGE

    def test_judge_provider_is_independent_of_the_ollama_local_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An Ollama judge needs no cloud key at all.
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        (judge,) = build_evaluators(
            [{"type": "llm_judge", "provider": "ollama", "model": "llama3.2"}]
        )
        assert isinstance(judge, LLMJudge)
        assert isinstance(judge.provider_client, OllamaProvider)
        assert judge.temperature == 0.0

    def test_missing_provider_or_model_is_rejected(self) -> None:
        with pytest.raises(ConfigError, match="requires a 'provider'"):
            build_evaluators([{"type": "llm_judge", "model": "m"}])
        with pytest.raises(ConfigError, match="requires a non-empty 'model'"):
            build_evaluators([{"type": "llm_judge", "provider": "ollama"}])

    def test_unknown_judge_provider_is_rejected(self) -> None:
        with pytest.raises(ConfigError, match="is not one of"):
            build_evaluators([{"type": "llm_judge", "provider": "cohere", "model": "m"}])

    def test_missing_api_key_fails_fast_at_build_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
            build_evaluators([{"type": "llm_judge", "provider": "anthropic", "model": "m"}])
