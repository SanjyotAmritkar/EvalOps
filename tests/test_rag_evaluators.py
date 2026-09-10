"""Deterministic RAG evaluators (Phase 9, CP 9.1): exact metric behaviour."""

from __future__ import annotations

import pytest

from evalops.domain.entities import DatasetCase, EvaluationRun
from evalops.domain.enums import EvaluatorFamily
from evalops.domain.value_objects import RetrievedItem
from evalops.errors import ConfigError
from evalops.evaluators import build_evaluators
from evalops.rag_evaluators import ContextPrecision, GroundednessLexical, RetrievalRecall


def _run(output: str = "", *items: RetrievedItem) -> EvaluationRun:
    return EvaluationRun(
        experiment_id="e1",
        system_version_id="v1",
        case_id="c1",
        repeat_index=0,
        output=output,
        retrieval=items,
    )


def _item(doc_id: str, content: str = "", rank: int = 0) -> RetrievedItem:
    return RetrievedItem(doc_id=doc_id, content=content, rank=rank)


def _case(*relevant: str) -> DatasetCase:
    return DatasetCase(input="q", expected_retrieval_ids=relevant)


# --- RetrievalRecall ------------------------------------------------------


def test_recall_full_and_partial() -> None:
    evaluator = RetrievalRecall(min_recall=1.0)
    case = _case("d1", "d2", "d3")

    full = evaluator.evaluate(_run("", _item("d1"), _item("d2"), _item("d3")), case)
    assert full.score == 1.0
    assert full.passed is True
    assert full.family is EvaluatorFamily.STATISTICAL

    partial = evaluator.evaluate(_run("", _item("d1"), _item("d9")), case)
    assert partial.score == pytest.approx(1 / 3)
    assert partial.passed is False


def test_recall_empty_retrieval_is_zero() -> None:
    score = RetrievalRecall().evaluate(_run(""), _case("d1", "d2"))
    assert score.score == 0.0
    assert score.passed is False


def test_recall_deduplicates_relevant_and_retrieved() -> None:
    # relevant {d1, d2}; retrieved d1 twice + an irrelevant dup -> recall 1/2
    score = RetrievalRecall().evaluate(
        _run("", _item("d1"), _item("d1"), _item("dX"), _item("dX")),
        _case("d1", "d1", "d2"),
    )
    assert score.score == pytest.approx(0.5)


def test_recall_is_deterministic_regardless_of_retrieved_order() -> None:
    case = _case("d1", "d2", "d3")
    a = RetrievalRecall().evaluate(_run("", _item("d3"), _item("d1"), _item("d2")), case)
    b = RetrievalRecall().evaluate(_run("", _item("d1"), _item("d2"), _item("d3")), case)
    assert a.score == b.score == 1.0


def test_recall_without_labels_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="expected_retrieval_ids"):
        RetrievalRecall().evaluate(_run("", _item("d1")), DatasetCase(input="q"))


def test_recall_min_recall_threshold_controls_pass() -> None:
    case = _case("d1", "d2")  # candidate retrieves 1 of 2 -> recall 0.5
    run = _run("", _item("d1"))
    assert RetrievalRecall(min_recall=0.5).evaluate(run, case).passed is True
    assert RetrievalRecall(min_recall=0.75).evaluate(run, case).passed is False


# --- ContextPrecision ---------------------------------------------------


def test_precision_exact() -> None:
    # relevant {d1,d2}; retrieved d1,d2,d3 -> 2/3
    score = ContextPrecision().evaluate(
        _run("", _item("d1"), _item("d2"), _item("d3")), _case("d1", "d2")
    )
    assert score.score == pytest.approx(2 / 3)
    assert score.passed is False  # default min_precision 1.0


def test_precision_zero_denominator_is_zero() -> None:
    """Nothing retrieved when relevant context exists is a retrieval failure."""
    score = ContextPrecision().evaluate(_run(""), _case("d1"))
    assert score.score == 0.0
    assert score.passed is False


def test_precision_deduplicates_retrieved() -> None:
    # retrieved d1 (x2), d2 -> unique {d1, d2}; relevant {d1} -> precision 1/2
    score = ContextPrecision().evaluate(
        _run("", _item("d1"), _item("d1"), _item("d2")), _case("d1")
    )
    assert score.score == pytest.approx(0.5)


def test_precision_without_labels_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="expected_retrieval_ids"):
        ContextPrecision().evaluate(_run("", _item("d1")), DatasetCase(input="q"))


# --- GroundednessLexical ----------------------------------------------


def test_groundedness_fully_supported_answer() -> None:
    run = _run(
        "The mitochondria produces cellular energy",
        _item("d1", "Mitochondria is the organelle that produces cellular energy in a cell"),
    )
    score = GroundednessLexical(min_groundedness=0.8).evaluate(run, _case("d1"))
    assert score.score == 1.0
    assert score.passed is True
    assert score.family is EvaluatorFamily.DETERMINISTIC


def test_groundedness_unsupported_content_lowers_score() -> None:
    run = _run(
        "Mitochondria produces energy and was discovered in Antarctica by penguins",
        _item("d1", "Mitochondria produces energy"),
    )
    score = GroundednessLexical(min_groundedness=0.8).evaluate(run, _case("d1"))
    assert score.score < 0.8
    assert score.passed is False


def test_groundedness_no_context_is_zero_for_nontrivial_answer() -> None:
    score = GroundednessLexical().evaluate(_run("Some substantive claim here"), _case("d1"))
    assert score.score == 0.0
    assert score.passed is False


def test_groundedness_empty_answer_is_vacuously_grounded() -> None:
    score = GroundednessLexical().evaluate(_run("   "), _case("d1"))
    assert score.score == 1.0
    assert score.passed is True


def test_groundedness_is_deterministic() -> None:
    run = _run("alpha beta gamma", _item("d1", "alpha beta only"))
    a = GroundednessLexical().evaluate(run, _case("d1"))
    b = GroundednessLexical().evaluate(run, _case("d1"))
    assert a.score == b.score == pytest.approx(2 / 3)


def test_groundedness_needs_no_relevance_labels() -> None:
    # a promoted-trace case has no expected_retrieval_ids; groundedness still works
    score = GroundednessLexical().evaluate(
        _run("alpha", _item("d1", "alpha")), DatasetCase(input="q")
    )
    assert score.score == 1.0


# --- build_evaluators wiring -----------------------------------------


def test_build_evaluators_constructs_rag_types_with_thresholds() -> None:
    evaluators = build_evaluators(
        [
            {"type": "retrieval_recall", "min_recall": 0.75},
            {"type": "context_precision"},
            {"type": "groundedness", "min_groundedness": 0.5, "name": "grounding"},
        ]
    )
    kinds = {type(e).__name__ for e in evaluators}
    assert kinds == {"RetrievalRecall", "ContextPrecision", "GroundednessLexical"}
    recall = next(e for e in evaluators if isinstance(e, RetrievalRecall))
    assert recall.min_recall == 0.75
    grounding = next(e for e in evaluators if isinstance(e, GroundednessLexical))
    assert grounding.name == "grounding"
    assert grounding.min_groundedness == 0.5


def test_build_evaluators_rejects_out_of_range_threshold() -> None:
    with pytest.raises(ConfigError, match="within"):
        build_evaluators([{"type": "retrieval_recall", "min_recall": 1.5}])
