"""Tests for evalops.calibration -- judge-vs-human agreement metrics.

The judge provider is a scripted fake: one canned reply (or exception) per
call, in order. No network, no keys.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from evalops.calibration import calibrate_judge, compute_metrics
from evalops.domain.contracts import ProviderError, ProviderResponse
from evalops.domain.entities import SystemVersion
from evalops.domain.enums import ProviderName
from evalops.domain.value_objects import (
    JudgeCalibrationCase,
    JudgeCalibrationMetrics,
    LabeledJudgeExample,
    UsageMetrics,
)
from evalops.judge import JUDGE_RUBRIC_ID, LLMJudge

_PASS = '{"verdict": "pass", "score": 0.9}'
_FAIL = '{"verdict": "fail", "score": 0.1}'


@dataclass
class _ScriptedJudgeProvider:
    replies: Sequence[str | BaseException]
    name: str = "openai"
    calls: int = field(default=0)

    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        item = self.replies[self.calls]
        self.calls += 1
        if isinstance(item, BaseException):
            raise item
        return ProviderResponse(text=item, usage=UsageMetrics())


def _judge(replies: Sequence[str | BaseException], **kw: object) -> LLMJudge:
    return LLMJudge(
        provider_name=ProviderName.OPENAI,
        provider_client=_ScriptedJudgeProvider(replies),
        model="judge-model",
        **kw,  # type: ignore[arg-type]
    )


def _ex(human_pass: bool, *, reference: str | None = None) -> LabeledJudgeExample:
    return LabeledJudgeExample(input="q", output="a", human_pass=human_pass, reference=reference)


def _confusion(m: JudgeCalibrationMetrics) -> tuple[int, int, int, int]:
    """(TP, TN, FP, FN) as a compact tuple for assertions."""
    return (m.true_positives, m.true_negatives, m.false_positives, m.false_negatives)


# --- agreement / confusion matrix --------------------------------------


def test_perfect_agreement() -> None:
    examples = [_ex(True), _ex(False), _ex(True), _ex(False)]
    judge = _judge([_PASS, _FAIL, _PASS, _FAIL])

    result = calibrate_judge(judge, examples)
    m = result.metrics

    assert (m.total, m.scored, m.failures) == (4, 4, 0)
    assert _confusion(m) == (2, 2, 0, 0)
    assert m.agreements == 4
    assert m.agreement_rate == 1.0
    assert (m.precision, m.recall, m.f1) == (1.0, 1.0, 1.0)


def test_mixed_tp_tn_fp_fn() -> None:
    # human:  P  P  F  F  P
    # judge:  P  P  P  F  F   -> TP=2, TN=1, FP=1, FN=1
    examples = [_ex(True), _ex(True), _ex(False), _ex(False), _ex(True)]
    judge = _judge([_PASS, _PASS, _PASS, _FAIL, _FAIL])

    m = calibrate_judge(judge, examples).metrics

    assert _confusion(m) == (2, 1, 1, 1)
    assert m.agreements == 3
    assert m.agreement_rate == pytest.approx(0.6)
    assert m.precision == pytest.approx(2 / 3)
    assert m.recall == pytest.approx(2 / 3)
    assert m.f1 == pytest.approx(2 / 3)


def test_precision_recall_f1_are_the_standard_formulas() -> None:
    # human:  P P P F   judge: P F F P  -> TP=1, FN=2, FP=1, TN=0
    m = calibrate_judge(
        _judge([_PASS, _FAIL, _FAIL, _PASS]),
        [_ex(True), _ex(True), _ex(True), _ex(False)],
    ).metrics

    assert _confusion(m) == (1, 0, 1, 2)  # TP, TN, FP, FN
    assert m.precision == pytest.approx(1 / 2)
    assert m.recall == pytest.approx(1 / 3)
    assert m.f1 == pytest.approx(2 * 0.5 * (1 / 3) / (0.5 + 1 / 3))


# --- zero denominators -> None, never 0 ------------------------------


def test_empty_set_leaves_every_rate_undefined() -> None:
    m = calibrate_judge(_judge([]), []).metrics
    assert (m.total, m.scored, m.failures) == (0, 0, 0)
    assert m.agreement_rate is None
    assert m.precision is None and m.recall is None and m.f1 is None


def test_no_human_passes_makes_recall_undefined() -> None:
    # all human fail; judge passes one -> TP+FN == 0 -> recall None
    m = calibrate_judge(_judge([_FAIL, _PASS, _FAIL]), [_ex(False), _ex(False), _ex(False)]).metrics
    assert (m.true_positives, m.false_negatives) == (0, 0)
    assert m.recall is None
    assert m.precision == 0.0  # TP=0, FP=1
    assert m.f1 is None


def test_judge_never_passes_makes_precision_undefined() -> None:
    m = calibrate_judge(_judge([_FAIL, _FAIL, _FAIL]), [_ex(True), _ex(True), _ex(False)]).metrics
    assert (m.true_positives, m.false_positives) == (0, 0)
    assert m.precision is None
    assert m.recall == 0.0  # TP=0, FN=2
    assert m.f1 is None


# --- judge / provider failure: explicit, never agreement ------------


def test_provider_failure_is_recorded_per_case_not_counted() -> None:
    judge = _judge([_PASS, ProviderError("judge model unreachable"), _FAIL])
    examples = [_ex(True), _ex(True), _ex(False)]

    result = calibrate_judge(judge, examples)
    m = result.metrics

    assert (m.total, m.scored, m.failures) == (3, 2, 1)
    failed = result.cases[1]
    assert failed.judge_pass is None and failed.judge_score is None
    assert "ProviderError" in (failed.error or "")
    # the failed example is in neither the confusion matrix nor the agreements
    assert m.true_positives + m.true_negatives + m.false_positives + m.false_negatives == 2
    assert m.agreements == 2  # the pass/pass and fail/fail
    assert m.agreement_rate == 1.0  # over the 2 scored, not 3


def test_malformed_judge_reply_is_recorded_as_a_failure() -> None:
    result = calibrate_judge(_judge(["totally not json"]), [_ex(True)])
    assert result.metrics.failures == 1
    assert "JudgeError" in (result.cases[0].error or "")
    assert result.cases[0].judge_pass is None


def test_a_non_judge_exception_still_propagates() -> None:
    judge = _judge([RuntimeError("bug in the fake")])
    with pytest.raises(RuntimeError, match="bug in the fake"):
        calibrate_judge(judge, [_ex(True)])


# --- per-example inspection detail ---------------------------------


def test_each_case_preserves_human_and_judge_detail() -> None:
    judge = _judge(['{"verdict": "fail", "score": 0.25, "reasoning": "off topic"}'])
    (case,) = calibrate_judge(judge, [_ex(True, reference="the ref")]).cases

    assert case.human_pass is True
    assert case.judge_pass is False
    assert case.judge_score == 0.25
    assert case.judge_reasoning == "off topic"
    assert case.reference == "the ref"
    assert case.error is None


def test_calibration_records_judge_identity_and_rubric() -> None:
    result = calibrate_judge(_judge([_PASS], name="correctness", temperature=0.0), [_ex(True)])
    assert result.judge_provider is ProviderName.OPENAI
    assert result.judge_model == "judge-model"
    assert result.judge_name == "correctness"
    assert result.judge_temperature == 0.0
    assert result.rubric_id == JUDGE_RUBRIC_ID
    assert result.id and result.created_at.tzinfo is not None


# --- compute_metrics in isolation --------------------------------


def _case(human: bool, judge: bool | None) -> JudgeCalibrationCase:
    return JudgeCalibrationCase(
        input="i",
        output="o",
        reference=None,
        human_pass=human,
        judge_pass=judge,
        judge_score=None if judge is None else (1.0 if judge else 0.0),
        judge_reasoning=None,
        error=None if judge is not None else "boom",
    )


def test_compute_metrics_matches_the_engine() -> None:
    m = compute_metrics(
        [_case(True, True), _case(False, False), _case(True, False), _case(False, None)]
    )
    assert (m.total, m.scored, m.failures) == (4, 3, 1)
    assert (m.true_positives, m.true_negatives, m.false_negatives) == (1, 1, 1)
    assert m.agreement_rate == pytest.approx(2 / 3)
