"""Tests for evalops.judge.LLMJudge -- no real providers, no network.

The judge's provider is a hand-rolled fake ``ProviderClient`` that returns a
canned reply (or raises). Calibration is out of scope (CP 6.2).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from evalops.domain.contracts import ProviderError, ProviderResponse
from evalops.domain.entities import DatasetCase, EvaluationRun, SystemVersion
from evalops.domain.enums import EvaluatorFamily, ProviderName
from evalops.domain.value_objects import UsageMetrics
from evalops.errors import JudgeError
from evalops.judge import LLMJudge, parse_judge_verdict, render_judge_prompt


@dataclass
class _FakeJudgeProvider:
    """Records the prompt/config it is asked to complete; returns a canned reply."""

    reply: str = '{"verdict": "pass", "score": 0.9, "reasoning": "ok"}'
    raises: BaseException | None = None
    name: str = "openai"
    seen_prompt: str | None = None
    seen_config: SystemVersion | None = None

    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        self.seen_prompt = prompt
        self.seen_config = config
        if self.raises is not None:
            raise self.raises
        return ProviderResponse(text=self.reply, usage=UsageMetrics())


def _run(output: str) -> EvaluationRun:
    return EvaluationRun(
        experiment_id="e",
        system_version_id="sv",
        case_id="c",
        repeat_index=0,
        output=output,
    )


def _case(
    *, input_: str = "What is the capital of France?", expected: str | None = "Paris"
) -> DatasetCase:
    return DatasetCase(input=input_, expected_output=expected, id="c")


def _judge(provider: _FakeJudgeProvider) -> LLMJudge:
    return LLMJudge(
        provider_name=ProviderName.OPENAI,
        provider_client=provider,
        model="judge-model",
    )


# --- valid structured responses ----------------------------------------


def test_valid_pass_verdict_produces_a_passing_score() -> None:
    judge = _judge(_FakeJudgeProvider(reply='{"verdict": "pass", "score": 0.8}'))

    score = judge.evaluate(_run("Paris"), _case())

    assert score.evaluator == "llm_judge"
    assert score.family is EvaluatorFamily.LLM_JUDGE
    assert score.passed is True
    assert score.score == 0.8


def test_valid_fail_verdict_produces_a_failing_score() -> None:
    judge = _judge(_FakeJudgeProvider(reply='{"verdict": "fail", "score": 0.1}'))

    score = judge.evaluate(_run("Berlin"), _case())

    assert score.passed is False
    assert score.score == 0.1


def test_score_is_derived_when_omitted() -> None:
    passing = _judge(_FakeJudgeProvider(reply='{"verdict": "pass"}')).evaluate(_run("x"), _case())
    failing = _judge(_FakeJudgeProvider(reply='{"verdict": "fail"}')).evaluate(_run("x"), _case())
    assert (passing.score, passing.passed) == (1.0, True)
    assert (failing.score, failing.passed) == (0.0, False)


def test_json_wrapped_in_a_fenced_block_is_tolerated() -> None:
    reply = 'Sure!\n```json\n{"verdict": "pass", "score": 1.0}\n```\n'
    score = _judge(_FakeJudgeProvider(reply=reply)).evaluate(_run("x"), _case())
    assert score.passed is True


def test_prompt_contains_input_output_and_optional_reference() -> None:
    with_ref = render_judge_prompt("the input", "the output", "the reference")
    assert "the input" in with_ref and "the output" in with_ref
    assert "REFERENCE ANSWER:\nthe reference" in with_ref

    without_ref = render_judge_prompt("the input", "the output", None)
    assert "REFERENCE ANSWER:\n" not in without_ref  # the filled-in section, not the rubric text


def test_judge_is_asked_with_its_own_provider_and_low_temperature() -> None:
    provider = _FakeJudgeProvider()
    judge = LLMJudge(
        provider_name=ProviderName.ANTHROPIC,
        provider_client=provider,
        model="claude-judge",
    )

    judge.evaluate(_run("Paris"), _case())

    assert provider.seen_config is not None
    assert provider.seen_config.provider is ProviderName.ANTHROPIC
    assert provider.seen_config.model == "claude-judge"
    assert provider.seen_config.parameters["temperature"] == 0.0
    assert "CANDIDATE ANSWER:\nParis" in (provider.seen_prompt or "")


# --- malformed judge output must fail, never silently pass -------------


@pytest.mark.parametrize(
    "reply",
    [
        "not json at all",
        "{",
        '{"reasoning": "forgot the verdict"}',
        '{"verdict": "maybe"}',
        '{"verdict": "pass", "score": 4}',
        '{"verdict": "pass", "score": "high"}',
        '["pass"]',
    ],
)
def test_malformed_judge_reply_raises_judge_error(reply: str) -> None:
    judge = _judge(_FakeJudgeProvider(reply=reply))
    with pytest.raises(JudgeError):
        judge.evaluate(_run("x"), _case())


def test_parse_judge_verdict_directly_rejects_bad_shapes() -> None:
    with pytest.raises(JudgeError, match="not a JSON object"):
        parse_judge_verdict("hello", evaluator="j")
    with pytest.raises(JudgeError, match="'verdict'"):
        parse_judge_verdict('{"score": 1}', evaluator="j")


# --- judge provider failure propagation ------------------------------


def test_judge_provider_failure_propagates_as_provider_error() -> None:
    judge = _judge(_FakeJudgeProvider(raises=ProviderError("judge model unreachable")))
    with pytest.raises(ProviderError, match="judge model unreachable"):
        judge.evaluate(_run("x"), _case())


# --- independence from the evaluated system --------------------------


def test_judge_ignores_the_evaluated_system_and_works_without_a_reference() -> None:
    provider = _FakeJudgeProvider(reply='{"verdict": "pass", "score": 0.7}')
    judge = _judge(provider)

    # a case with NO reference answer, and a run from some unrelated system
    score = judge.evaluate(_run("an answer"), _case(expected=None))

    assert score.passed is True
    # the judge built its own config -- nothing from the system under test
    assert provider.seen_config is not None
    assert provider.seen_config.project_id == "judge"
    assert "REFERENCE ANSWER:\n" not in (provider.seen_prompt or "")
