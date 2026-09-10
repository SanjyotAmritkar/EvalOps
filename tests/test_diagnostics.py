"""Tests for evalops.diagnostics: deterministic, explanatory-only case-level
regression diagnostics. They must never influence a release decision."""

from __future__ import annotations

import pytest

from evalops.aggregate import aggregate_results
from evalops.diagnostics import MIN_SCORE_DROP, diagnose_regressions
from evalops.domain.entities import (
    CaseResult,
    EvaluationRun,
    Experiment,
    ReleasePolicy,
)
from evalops.domain.enums import EvaluatorFamily
from evalops.domain.value_objects import EvaluatorScore, UsageMetrics
from evalops.gate import evaluate_gate
from evalops.runner import RunOutcome

EXPERIMENT = Experiment(
    project_id="p",
    dataset_id="d",
    baseline_version_id="base",
    candidate_version_id="cand",
)


def _run(
    version_id: str,
    *,
    case_id: str,
    repeat: int = 0,
    error: str | None = None,
    latency: float = 10.0,
    cost: float = 0.0,
) -> EvaluationRun:
    return EvaluationRun(
        experiment_id=EXPERIMENT.id,
        system_version_id=version_id,
        case_id=case_id,
        repeat_index=repeat,
        output="" if error else "out",
        usage=UsageMetrics(latency_ms=latency, cost_usd=cost),
        error=error,
    )


def _score(name: str, score: float, *, passed: bool | None = None) -> EvaluatorScore:
    return EvaluatorScore(
        evaluator=name,
        family=EvaluatorFamily.DETERMINISTIC,
        score=score,
        passed=score >= 1.0 if passed is None else passed,
    )


def _outcome(*pairs: tuple[EvaluationRun, tuple[EvaluatorScore, ...]]) -> RunOutcome:
    runs = tuple(run for run, _ in pairs)
    results = tuple(CaseResult(run_id=run.id, scores=scores) for run, scores in pairs)
    return RunOutcome(runs=runs, case_results=results)


# --- clean / no regression -------------------------------------------------


def test_clean_run_reports_no_regressions() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0"), (_score("contains", 1.0),)),
        (_run("cand", case_id="c0"), (_score("contains", 1.0),)),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)

    assert diag.available is True
    assert diag.matched_pairs == 1
    assert diag.regressing_pairs == 0
    assert diag.regressing_cases == 0
    assert diag.categories == ()
    assert diag.evaluators == ()
    assert diag.cases == ()
    assert diag.findings == ()


def test_no_matched_pairs_is_unavailable() -> None:
    diag = diagnose_regressions(EXPERIMENT, RunOutcome(runs=(), case_results=()))
    assert diag.available is False
    assert diag.matched_pairs == 0
    assert diag.cases == ()


def test_a_candidate_improvement_is_not_a_regression() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0"), (_score("contains", 0.5, passed=False),)),
        (_run("cand", case_id="c0"), (_score("contains", 1.0, passed=True),)),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)
    assert diag.regressing_pairs == 0
    assert diag.findings == ()


# --- evaluator transitions ----------------------------------------------


def test_evaluator_pass_to_fail_is_categorised_and_counted() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0"), (_score("contains", 1.0, passed=True),)),
        (_run("cand", case_id="c0"), (_score("contains", 0.0, passed=False),)),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)

    assert diag.regressing_pairs == 1
    assert diag.regressing_cases == 1
    (finding,) = diag.findings
    assert finding.kind == "evaluator_pass_to_fail"
    assert finding.category == "evaluator_regression"
    assert finding.evaluator == "contains"
    assert (finding.baseline_detail, finding.candidate_detail) == ("pass", "fail")

    (cat,) = diag.categories
    assert (cat.category, cat.pairs, cat.cases) == ("evaluator_regression", 1, 1)
    (ev,) = diag.evaluators
    assert (ev.evaluator, ev.pass_to_fail, ev.score_drop) == ("contains", 1, 0)


def test_graded_score_drop_below_threshold_is_reported_once() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0"), (_score("llm_judge", 1.0, passed=True),)),
        (_run("cand", case_id="c0"), (_score("llm_judge", 0.5, passed=True),)),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)

    (finding,) = diag.findings
    assert finding.kind == "evaluator_score_drop"
    assert finding.category == "evaluator_regression"
    assert (finding.baseline_detail, finding.candidate_detail) == ("1.000", "0.500")
    (ev,) = diag.evaluators
    assert (ev.pass_to_fail, ev.score_drop) == (0, 1)


def test_score_jitter_within_threshold_is_not_a_regression() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0"), (_score("llm_judge", 0.90, passed=True),)),
        (
            _run("cand", case_id="c0"),
            (_score("llm_judge", 0.90 - MIN_SCORE_DROP / 2, passed=True),),
        ),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)
    assert diag.findings == ()


def test_pass_to_fail_takes_precedence_over_score_drop_for_one_evaluator_pair() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0"), (_score("contains", 1.0, passed=True),)),
        (_run("cand", case_id="c0"), (_score("contains", 0.2, passed=False),)),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)
    (finding,) = diag.findings
    assert finding.kind == "evaluator_pass_to_fail"


# --- provider / execution failure -------------------------------------


def test_new_candidate_provider_failure_is_its_own_category() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0"), (_score("contains", 1.0, passed=True),)),
        (_run("cand", case_id="c0", error="503 upstream unavailable"), ()),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)

    (finding,) = diag.findings
    assert finding.kind == "provider_failure"
    assert finding.category == "provider_execution_failure"
    assert finding.evaluator is None
    assert "upstream unavailable" in finding.candidate_detail
    (case,) = diag.cases
    assert case.provider_failure is True


def test_pre_existing_baseline_failure_is_not_a_candidate_regression() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0", error="already broken"), ()),
        (_run("cand", case_id="c0", error="still broken"), ()),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)
    assert diag.findings == ()


# --- RAG + agent categorisation -------------------------------------


@pytest.mark.parametrize(
    ("evaluator", "expected_category"),
    [
        ("retrieval_recall", "retrieval_regression"),
        ("context_precision", "retrieval_regression"),
        ("groundedness_lexical", "groundedness_regression"),
        ("tool_selection", "tool_selection_regression"),
        ("tool_arguments", "tool_argument_regression"),
        ("tool_success", "tool_execution_failure"),
        ("tool_trajectory", "trajectory_regression"),
    ],
)
def test_known_rag_and_agent_evaluators_map_to_specific_categories(
    evaluator: str, expected_category: str
) -> None:
    outcome = _outcome(
        (_run("base", case_id="c0"), (_score(evaluator, 1.0, passed=True),)),
        (_run("cand", case_id="c0"), (_score(evaluator, 0.0, passed=False),)),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)
    (finding,) = diag.findings
    assert finding.category == expected_category


def test_unknown_evaluator_name_falls_back_to_generic_category() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0"), (_score("my_custom_check", 1.0, passed=True),)),
        (_run("cand", case_id="c0"), (_score("my_custom_check", 0.0, passed=False),)),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)
    (finding,) = diag.findings
    assert finding.category == "evaluator_regression"


# --- repeated runs / pairing --------------------------------------


def test_repeats_are_paired_by_case_and_repeat_index() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0", repeat=0), (_score("contains", 1.0, passed=True),)),
        (_run("base", case_id="c0", repeat=1), (_score("contains", 1.0, passed=True),)),
        (_run("cand", case_id="c0", repeat=0), (_score("contains", 0.0, passed=False),)),
        (_run("cand", case_id="c0", repeat=1), (_score("contains", 1.0, passed=True),)),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)

    assert diag.matched_pairs == 2
    assert diag.regressing_pairs == 1  # only repeat 0 regressed
    assert diag.regressing_cases == 1
    (case,) = diag.cases
    assert case.representative.repeat_index == 0


def test_representative_pair_is_the_repeat_with_the_most_findings() -> None:
    outcome = _outcome(
        # repeat 0: one finding; repeat 1: two findings -> repeat 1 represents
        (_run("base", case_id="c0", repeat=0), (_score("contains", 1.0, passed=True),)),
        (
            _run("base", case_id="c0", repeat=1),
            (_score("contains", 1.0, passed=True), _score("tool_success", 1.0, passed=True)),
        ),
        (_run("cand", case_id="c0", repeat=0), (_score("contains", 0.0, passed=False),)),
        (
            _run("cand", case_id="c0", repeat=1),
            (_score("contains", 0.0, passed=False), _score("tool_success", 0.0, passed=False)),
        ),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)
    (case,) = diag.cases
    assert case.representative.repeat_index == 1
    assert case.finding_count == 3


def test_unmatched_runs_are_ignored() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0"), (_score("contains", 1.0, passed=True),)),
        (_run("cand", case_id="c9"), (_score("contains", 0.0, passed=False),)),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)
    assert diag.matched_pairs == 0
    assert diag.findings == ()
    assert diag.available is False


# --- missing evidence -------------------------------------------------


def test_missing_case_result_is_tolerated_not_raised() -> None:
    b = _run("base", case_id="c0")
    c = _run("cand", case_id="c0")
    # candidate run has no CaseResult at all
    outcome = RunOutcome(
        runs=(b, c),
        case_results=(CaseResult(run_id=b.id, scores=(_score("contains", 1.0, passed=True),)),),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)
    assert diag.findings == ()  # nothing to compare -> no fabricated regression
    assert diag.available is True


def test_evaluator_only_on_one_side_is_skipped() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0"), (_score("contains", 1.0, passed=True),)),
        (_run("cand", case_id="c0"), (_score("regex_match", 0.0, passed=False),)),
    )
    diag = diagnose_regressions(EXPERIMENT, outcome)
    assert diag.findings == ()


# --- diagnostics never alter the release decision -----------------


def test_diagnostics_do_not_change_the_gate_outcome() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0"), (_score("contains", 1.0, passed=True),)),
        (_run("base", case_id="c1"), (_score("contains", 1.0, passed=True),)),
        (_run("cand", case_id="c0"), (_score("contains", 0.0, passed=False),)),
        (_run("cand", case_id="c1"), (_score("contains", 0.0, passed=False),)),
    )
    result = aggregate_results(EXPERIMENT, outcome, evaluator_names=["contains"])
    policy = ReleasePolicy(name="p", thresholds={"contains.pass_rate": 0.1})

    before = evaluate_gate(result, policy)
    diag = diagnose_regressions(EXPERIMENT, outcome)
    after = evaluate_gate(result, policy)

    assert before == after
    # the diagnostics did observe the regression -- they just do not gate on it
    assert diag.regressing_pairs == 2


def test_diagnose_is_deterministic() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0"), (_score("contains", 1.0, passed=True),)),
        (_run("cand", case_id="c0"), (_score("contains", 0.0, passed=False),)),
    )
    assert diagnose_regressions(EXPERIMENT, outcome) == diagnose_regressions(EXPERIMENT, outcome)
