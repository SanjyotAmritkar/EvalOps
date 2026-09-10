"""Deterministic case-level regression diagnostics (Phase 10, CP 10.2).

**Explanatory only.** Nothing in this module changes an ``EvaluationResult``,
the statistical evidence, or a PASS/BLOCK decision. Diagnostics are computed
from the persisted ``EvaluationRun`` / ``CaseResult`` records *after* the gate
has already spoken, and exist purely to answer "which cases regressed on the
candidate, and why". No LLM, no embeddings, no clustering, no second gate, no
second statistical engine.

Given the raw records of a :class:`~evalops.runner.RunOutcome`, this module

1. pairs baseline vs candidate runs by ``(case_id, repeat_index)`` -- the same
   deterministic rule :mod:`evalops.stats` uses;
2. for every matched pair compares the candidate against the baseline and
   records zero or more **findings**, each in a category derived mechanically
   from the evidence (an evaluator ``PASS -> FAIL``, a graded-score drop, a new
   provider error, ...); and
3. aggregates the findings into counts by category and by evaluator, the set of
   affected case ids, and one representative pair per case for inspection.

The categorisation never infers a semantic root cause beyond the evidence: a
lower score is a "score drop", not "the answer is wrong".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from evalops.domain.entities import CaseResult, EvaluationRun, Experiment
from evalops.domain.value_objects import EvaluatorScore
from evalops.errors import ConfigError
from evalops.runner import RunOutcome

__all__ = [
    "MIN_SCORE_DROP",
    "CategoryCount",
    "EvaluatorCount",
    "PairFinding",
    "PairRef",
    "RegressingCase",
    "RegressionCategory",
    "RegressionDiagnostics",
    "diagnose_regressions",
]

#: A candidate-side regression category. ``evaluator_regression`` is the generic
#: fallback for any evaluator whose name is not one of the known RAG / agent
#: evaluators (including custom-named deterministic evaluators and future ones).
RegressionCategory = Literal[
    "evaluator_regression",
    "provider_execution_failure",
    "retrieval_regression",
    "groundedness_regression",
    "tool_selection_regression",
    "tool_argument_regression",
    "tool_execution_failure",
    "trajectory_regression",
]

#: What kind of evidence produced a finding.
FindingKind = Literal[
    "provider_failure",
    "evaluator_pass_to_fail",
    "evaluator_score_drop",
]

#: Minimum drop in a graded :class:`EvaluatorScore.score` (0..1) before a pair is
#: reported as a case-level ``score drop``. Deliberately conservative so tiny
#: numeric jitter is not surfaced as a regression. **It never affects gating** --
#: the release decision is made entirely by :mod:`evalops.gate` from the
#: aggregate metrics and their statistical evidence. A ``PASS -> FAIL``
#: transition is always reported regardless of magnitude.
MIN_SCORE_DROP = 0.05

#: Known evaluator name -> category. Unknown names fall back to
#: ``evaluator_regression`` (see :func:`_category_for_evaluator`).
_EVALUATOR_CATEGORY: dict[str, RegressionCategory] = {
    "retrieval_recall": "retrieval_regression",
    "context_precision": "retrieval_regression",
    "groundedness_lexical": "groundedness_regression",
    "tool_selection": "tool_selection_regression",
    "tool_arguments": "tool_argument_regression",
    "tool_success": "tool_execution_failure",
    "tool_trajectory": "trajectory_regression",
}


def _category_for_evaluator(name: str) -> RegressionCategory:
    known = _EVALUATOR_CATEGORY.get(name)
    if known is not None:
        return known
    if name.startswith("groundedness"):
        return "groundedness_regression"
    return "evaluator_regression"


@dataclass(frozen=True, slots=True)
class PairFinding:
    """One candidate-side regression observed on one ``(case_id, repeat_index)``
    pair, relative to the baseline run for the same key."""

    case_id: str
    repeat_index: int
    baseline_run_id: str
    candidate_run_id: str
    category: RegressionCategory
    kind: FindingKind
    evaluator: str | None  # set for the two ``evaluator_*`` kinds
    baseline_detail: str  # e.g. "completed", "pass", "1.000"
    candidate_detail: str  # e.g. "provider error", "fail", "0.500"


@dataclass(frozen=True, slots=True)
class CategoryCount:
    """How many regressing pairs / distinct cases fall in one category."""

    category: RegressionCategory
    pairs: int
    cases: int


@dataclass(frozen=True, slots=True)
class EvaluatorCount:
    """Per-evaluator breakdown of the evaluator-derived findings."""

    evaluator: str
    pairs: int
    cases: int
    pass_to_fail: int
    score_drop: int


@dataclass(frozen=True, slots=True)
class PairRef:
    """A pointer to one baseline/candidate run pair, for case inspection."""

    repeat_index: int
    baseline_run_id: str
    candidate_run_id: str


@dataclass(frozen=True, slots=True)
class RegressingCase:
    """One dataset case with at least one regressing pair on the candidate."""

    case_id: str
    categories: tuple[RegressionCategory, ...]  # sorted, distinct
    evaluators: tuple[str, ...]  # sorted, distinct
    provider_failure: bool
    finding_count: int
    representative: PairRef  # the repeat with the most findings; lowest repeat wins ties


@dataclass(frozen=True, slots=True)
class RegressionDiagnostics:
    """Deterministic explanation of the candidate-side regressions in one
    experiment. Purely descriptive -- see the module docstring."""

    experiment_id: str
    baseline_version_id: str
    candidate_version_id: str
    matched_pairs: int
    regressing_pairs: int
    regressing_cases: int
    categories: tuple[CategoryCount, ...]
    evaluators: tuple[EvaluatorCount, ...]
    cases: tuple[RegressingCase, ...]
    findings: tuple[PairFinding, ...]  # flat, deterministic order
    available: bool  # False when there were no matched pairs to analyse


def _score_map(
    run: EvaluationRun, case_results: dict[str, CaseResult]
) -> dict[str, EvaluatorScore]:
    """Evaluator-name -> score for one run. Empty when the run errored or has no
    persisted case result (missing evidence is tolerated, never raised)."""
    if run.error is not None:
        return {}
    case_result = case_results.get(run.id)
    if case_result is None:
        return {}
    return {score.evaluator: score for score in case_result.scores}


def _runs_by_key(
    runs: Sequence[EvaluationRun], version_id: str
) -> dict[tuple[str, int], EvaluationRun]:
    by_key: dict[tuple[str, int], EvaluationRun] = {}
    for run in runs:
        if run.system_version_id != version_id:
            continue
        key = (run.case_id, run.repeat_index)
        if key in by_key:
            raise ConfigError(
                f"version {version_id!r} has more than one run for case {key[0]!r} repeat {key[1]}"
            )
        by_key[key] = run
    return by_key


def _short_error(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= 160 else cleaned[:159] + "…"


def _pair_findings(
    *,
    case_id: str,
    repeat_index: int,
    baseline: EvaluationRun,
    candidate: EvaluationRun,
    case_results: dict[str, CaseResult],
    score_drop_threshold: float,
) -> list[PairFinding]:
    findings: list[PairFinding] = []

    def _finding(
        category: RegressionCategory,
        kind: FindingKind,
        evaluator: str | None,
        baseline_detail: str,
        candidate_detail: str,
    ) -> PairFinding:
        return PairFinding(
            case_id=case_id,
            repeat_index=repeat_index,
            baseline_run_id=baseline.id,
            candidate_run_id=candidate.id,
            category=category,
            kind=kind,
            evaluator=evaluator,
            baseline_detail=baseline_detail,
            candidate_detail=candidate_detail,
        )

    # A brand-new provider/execution failure on the candidate side.
    if candidate.error is not None and baseline.error is None:
        findings.append(
            _finding(
                "provider_execution_failure",
                "provider_failure",
                None,
                "completed",
                _short_error(candidate.error),
            )
        )

    baseline_scores = _score_map(baseline, case_results)
    candidate_scores = _score_map(candidate, case_results)
    for name in sorted(baseline_scores.keys() & candidate_scores.keys()):
        b_score = baseline_scores[name]
        c_score = candidate_scores[name]
        category = _category_for_evaluator(name)
        if b_score.passed is True and c_score.passed is False:
            findings.append(
                _finding(
                    category,
                    "evaluator_pass_to_fail",
                    name,
                    "pass",
                    "fail",
                )
            )
        elif c_score.score < b_score.score - score_drop_threshold:
            findings.append(
                _finding(
                    category,
                    "evaluator_score_drop",
                    name,
                    f"{b_score.score:.3f}",
                    f"{c_score.score:.3f}",
                )
            )

    return findings


def diagnose_regressions(
    experiment: Experiment,
    outcome: RunOutcome,
    *,
    score_drop_threshold: float = MIN_SCORE_DROP,
) -> RegressionDiagnostics:
    """Explain the candidate-side regressions in ``outcome`` at the case level.

    Pairs baseline/candidate runs by ``(case_id, repeat_index)`` (only keys
    present for **both** versions), compares each pair, and aggregates the
    findings. Deterministic and side-effect free. Reads the same ``RunOutcome``
    the aggregation and statistics read and changes nothing about either.

    ``available`` is ``False`` when there are no matched pairs to analyse (e.g.
    the experiment has not been run).
    """
    baseline_id = experiment.baseline_version_id
    candidate_id = experiment.candidate_version_id
    baseline_by_key = _runs_by_key(outcome.runs, baseline_id)
    candidate_by_key = _runs_by_key(outcome.runs, candidate_id)
    common = sorted(baseline_by_key.keys() & candidate_by_key.keys())

    case_results: dict[str, CaseResult] = {cr.run_id: cr for cr in outcome.case_results}

    findings: list[PairFinding] = []
    for case_id, repeat_index in common:
        findings.extend(
            _pair_findings(
                case_id=case_id,
                repeat_index=repeat_index,
                baseline=baseline_by_key[(case_id, repeat_index)],
                candidate=candidate_by_key[(case_id, repeat_index)],
                case_results=case_results,
                score_drop_threshold=score_drop_threshold,
            )
        )

    return RegressionDiagnostics(
        experiment_id=experiment.id,
        baseline_version_id=baseline_id,
        candidate_version_id=candidate_id,
        matched_pairs=len(common),
        regressing_pairs=len({(f.case_id, f.repeat_index) for f in findings}),
        regressing_cases=len({f.case_id for f in findings}),
        categories=_category_counts(findings),
        evaluators=_evaluator_counts(findings),
        cases=_regressing_cases(findings),
        findings=tuple(findings),
        available=len(common) > 0,
    )


def _category_counts(findings: Sequence[PairFinding]) -> tuple[CategoryCount, ...]:
    pairs: dict[str, set[tuple[str, int]]] = {}
    cases: dict[str, set[str]] = {}
    for f in findings:
        pairs.setdefault(f.category, set()).add((f.case_id, f.repeat_index))
        cases.setdefault(f.category, set()).add(f.case_id)
    counts = [
        CategoryCount(category=category, pairs=len(pairs[category]), cases=len(cases[category]))  # type: ignore[arg-type]
        for category in pairs
    ]
    counts.sort(key=lambda c: (-c.pairs, c.category))
    return tuple(counts)


def _evaluator_counts(findings: Sequence[PairFinding]) -> tuple[EvaluatorCount, ...]:
    by_name: dict[str, list[PairFinding]] = {}
    for f in findings:
        if f.evaluator is None:
            continue
        by_name.setdefault(f.evaluator, []).append(f)
    counts = [
        EvaluatorCount(
            evaluator=name,
            pairs=len({(f.case_id, f.repeat_index) for f in group}),
            cases=len({f.case_id for f in group}),
            pass_to_fail=sum(1 for f in group if f.kind == "evaluator_pass_to_fail"),
            score_drop=sum(1 for f in group if f.kind == "evaluator_score_drop"),
        )
        for name, group in by_name.items()
    ]
    counts.sort(key=lambda c: (-c.pairs, c.evaluator))
    return tuple(counts)


def _regressing_cases(findings: Sequence[PairFinding]) -> tuple[RegressingCase, ...]:
    by_case: dict[str, list[PairFinding]] = {}
    for f in findings:
        by_case.setdefault(f.case_id, []).append(f)

    cases: list[RegressingCase] = []
    for case_id, group in by_case.items():
        by_repeat: dict[int, list[PairFinding]] = {}
        for f in group:
            by_repeat.setdefault(f.repeat_index, []).append(f)
        # Representative = the repeat with the most findings; lowest repeat_index
        # breaks ties. Deterministic.
        repeat_index = min(by_repeat, key=lambda r: (-len(by_repeat[r]), r))
        sample = by_repeat[repeat_index][0]
        cases.append(
            RegressingCase(
                case_id=case_id,
                categories=tuple(sorted({f.category for f in group})),
                evaluators=tuple(sorted({f.evaluator for f in group if f.evaluator})),
                provider_failure=any(f.kind == "provider_failure" for f in group),
                finding_count=len(group),
                representative=PairRef(
                    repeat_index=repeat_index,
                    baseline_run_id=sample.baseline_run_id,
                    candidate_run_id=sample.candidate_run_id,
                ),
            )
        )
    cases.sort(key=lambda c: (-c.finding_count, c.case_id))
    return tuple(cases)
