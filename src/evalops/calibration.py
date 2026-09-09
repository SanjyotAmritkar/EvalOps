"""LLM-judge calibration (Phase 6, CP 6.2).

Run a configured :class:`~evalops.judge.LLMJudge` over a set of human-labeled
examples and quantify how well it agrees with the humans: agreement rate, the
pass/fail confusion matrix, precision, recall, F1.

Deliberately small and additive:

* binary pass/fail only -- no multiclass, no Cohen's kappa, no bootstrap;
* a judge/provider failure on an example is recorded on that case and excluded
  from every metric -- **never** silently counted as agreement;
* this is pure measurement. It does not touch Phase 5 release gating and never
  disables a judge.
"""

from __future__ import annotations

from collections.abc import Sequence

from evalops.domain.contracts import ProviderError
from evalops.domain.entities import JudgeCalibration
from evalops.domain.value_objects import (
    JudgeCalibrationCase,
    JudgeCalibrationMetrics,
    LabeledJudgeExample,
)
from evalops.errors import JudgeError
from evalops.judge import JUDGE_RUBRIC_ID, LLMJudge

#: Failure text is bounded so one stray provider error cannot bloat a row.
_MAX_ERROR_CHARS = 2000


def calibrate_judge(
    judge: LLMJudge,
    examples: Sequence[LabeledJudgeExample],
    *,
    rubric_id: str = JUDGE_RUBRIC_ID,
) -> JudgeCalibration:
    """Score every example with ``judge`` and return a :class:`JudgeCalibration`.

    A :class:`ProviderError` or :class:`JudgeError` on a single example is
    caught, recorded as that case's ``error`` (with ``judge_pass = None``), and
    the calibration continues. Any other exception propagates.
    """
    cases: list[JudgeCalibrationCase] = []
    for example in examples:
        try:
            verdict = judge.judge(
                case_input=example.input,
                candidate_output=example.output,
                reference=example.reference,
            )
        except (ProviderError, JudgeError) as exc:
            cases.append(
                JudgeCalibrationCase(
                    input=example.input,
                    output=example.output,
                    reference=example.reference,
                    human_pass=example.human_pass,
                    judge_pass=None,
                    judge_score=None,
                    judge_reasoning=None,
                    error=_bounded(f"{type(exc).__name__}: {exc}"),
                )
            )
        else:
            cases.append(
                JudgeCalibrationCase(
                    input=example.input,
                    output=example.output,
                    reference=example.reference,
                    human_pass=example.human_pass,
                    judge_pass=verdict.passed,
                    judge_score=verdict.score,
                    judge_reasoning=verdict.reasoning,
                    error=None,
                )
            )

    return JudgeCalibration(
        judge_provider=judge.provider_name,
        judge_model=judge.model,
        judge_name=judge.name,
        judge_temperature=judge.temperature,
        rubric_id=rubric_id,
        metrics=compute_metrics(cases),
        cases=tuple(cases),
    )


def compute_metrics(cases: Sequence[JudgeCalibrationCase]) -> JudgeCalibrationMetrics:
    """Aggregate scored cases into agreement / confusion / P / R / F1.

    Cases where the judge failed (``judge_pass is None``) are counted only in
    ``failures``. Undefined ratios (zero denominator) are ``None``.
    """
    total = len(cases)
    scored = [c for c in cases if c.judge_pass is not None]
    failures = total - len(scored)

    tp = sum(1 for c in scored if c.human_pass and c.judge_pass)
    tn = sum(1 for c in scored if not c.human_pass and not c.judge_pass)
    fp = sum(1 for c in scored if not c.human_pass and c.judge_pass)
    fn = sum(1 for c in scored if c.human_pass and not c.judge_pass)

    agreements = tp + tn
    agreement_rate = _ratio(agreements, len(scored))
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = (
        None
        if precision is None or recall is None or (precision + recall) == 0.0
        else 2.0 * precision * recall / (precision + recall)
    )

    return JudgeCalibrationMetrics(
        total=total,
        scored=len(scored),
        failures=failures,
        agreements=agreements,
        agreement_rate=agreement_rate,
        true_positives=tp,
        true_negatives=tn,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _bounded(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) > _MAX_ERROR_CHARS:
        cleaned = cleaned[: _MAX_ERROR_CHARS - 1] + "…"
    return cleaned or "unknown error"
