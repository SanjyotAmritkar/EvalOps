"""Deterministic agent/tool evaluators (Phase 9, CP 9.2)."""

from __future__ import annotations

import pytest

from evalops.agent_evaluators import (
    ToolArguments,
    ToolSelection,
    ToolSuccess,
    ToolTrajectory,
)
from evalops.domain.entities import DatasetCase, EvaluationRun
from evalops.domain.enums import EvaluatorFamily
from evalops.domain.value_objects import ExpectedToolCall, ToolCall
from evalops.errors import ConfigError
from evalops.evaluators import build_evaluators


def _run(*calls: ToolCall) -> EvaluationRun:
    return EvaluationRun(
        experiment_id="e1",
        system_version_id="v1",
        case_id="c1",
        repeat_index=0,
        output="done",
        tool_calls=calls,
    )


def _tc(
    name: str,
    arguments: dict[str, object] | None = None,
    *,
    ok: bool = True,
    error: str | None = None,
) -> ToolCall:
    return ToolCall(name=name, arguments=arguments or {}, ok=ok, error=error)


def _case(*expected: ExpectedToolCall) -> DatasetCase:
    return DatasetCase(input="q", expected_tool_calls=expected)


# --- ToolSelection ------------------------------------------------------


def test_tool_selection_exact_partial_extra_missing() -> None:
    ev = ToolSelection(min_score=1.0)
    case = _case(ExpectedToolCall("search"), ExpectedToolCall("fetch"))

    exact = ev.evaluate(_run(_tc("search"), _tc("fetch")), case)
    assert exact.score == 1.0 and exact.passed is True
    assert exact.family is EvaluatorFamily.DETERMINISTIC

    missing = ev.evaluate(_run(_tc("search")), case)
    assert missing.score == pytest.approx(0.5)  # {search} / {search, fetch}
    assert missing.passed is False

    extra = ev.evaluate(_run(_tc("search"), _tc("fetch"), _tc("delete")), case)
    assert extra.score == pytest.approx(2 / 3)  # 2 / |{search,fetch,delete}|

    wrong = ev.evaluate(_run(_tc("delete")), case)
    assert wrong.score == 0.0


def test_tool_selection_ignores_duplicates_and_order() -> None:
    case = _case(ExpectedToolCall("a"), ExpectedToolCall("a"), ExpectedToolCall("b"))
    a = ToolSelection().evaluate(_run(_tc("b"), _tc("a"), _tc("a")), case)
    assert a.score == 1.0  # dup names collapse; order ignored


def test_tool_selection_no_observed_calls_is_zero() -> None:
    score = ToolSelection().evaluate(_run(), _case(ExpectedToolCall("x")))
    assert score.score == 0.0 and score.passed is False


def test_tool_selection_without_labels_raises() -> None:
    with pytest.raises(ConfigError, match="expected_tool_calls"):
        ToolSelection().evaluate(_run(_tc("x")), DatasetCase(input="q"))


# --- ToolArguments ----------------------------------------------------


def test_tool_arguments_structural_equality_key_order_independent() -> None:
    ev = ToolArguments(min_score=1.0)
    case = _case(ExpectedToolCall("search", {"q": "cats", "limit": 5}))

    same = ev.evaluate(_run(_tc("search", {"limit": 5, "q": "cats"})), case)
    assert same.score == 1.0 and same.passed is True

    changed = ev.evaluate(_run(_tc("search", {"q": "dogs", "limit": 5})), case)
    assert changed.score == 0.0

    extra_key = ev.evaluate(_run(_tc("search", {"q": "cats", "limit": 5, "page": 1})), case)
    assert extra_key.score == 0.0  # extra key -> not structurally equal

    missing_key = ev.evaluate(_run(_tc("search", {"q": "cats"})), case)
    assert missing_key.score == 0.0


def test_tool_arguments_nested_structures() -> None:
    case = _case(ExpectedToolCall("call", {"filter": {"tags": ["a", "b"], "n": 2}}))
    ok = ToolArguments().evaluate(_run(_tc("call", {"filter": {"n": 2, "tags": ["a", "b"]}})), case)
    assert ok.score == 1.0
    reordered_list = ToolArguments().evaluate(
        _run(_tc("call", {"filter": {"n": 2, "tags": ["b", "a"]}})), case
    )
    assert reordered_list.score == 0.0  # list order is significant


def test_tool_arguments_repeated_tool_names_positional() -> None:
    case = _case(
        ExpectedToolCall("get", {"id": 1}),
        ExpectedToolCall("get", {"id": 2}),
    )
    both = ToolArguments().evaluate(_run(_tc("get", {"id": 1}), _tc("get", {"id": 2})), case)
    assert both.score == 1.0
    swapped = ToolArguments().evaluate(_run(_tc("get", {"id": 2}), _tc("get", {"id": 1})), case)
    assert swapped.score == 0.0  # positional pairing


def test_tool_arguments_partial_when_one_of_two_matches() -> None:
    case = _case(
        ExpectedToolCall("a", {"x": 1}),
        ExpectedToolCall("b", {"y": 2}),
    )
    score = ToolArguments().evaluate(_run(_tc("a", {"x": 1}), _tc("b", {"y": 9})), case)
    assert score.score == pytest.approx(0.5)


def test_tool_arguments_requires_arg_labels() -> None:
    with pytest.raises(ConfigError, match="explicit arguments"):
        ToolArguments().evaluate(_run(_tc("a")), _case(ExpectedToolCall("a")))
    with pytest.raises(ConfigError, match="expected_tool_calls"):
        ToolArguments().evaluate(_run(_tc("a")), DatasetCase(input="q"))


# --- ToolSuccess ----------------------------------------------------


def test_tool_success_rate() -> None:
    case = DatasetCase(input="q")  # no labels needed
    all_ok = ToolSuccess().evaluate(_run(_tc("a"), _tc("b")), case)
    assert all_ok.score == 1.0 and all_ok.passed is True
    half = ToolSuccess().evaluate(_run(_tc("a"), _tc("b", ok=False, error="boom")), case)
    assert half.score == pytest.approx(0.5) and half.passed is False


def test_tool_success_zero_calls_is_one() -> None:
    score = ToolSuccess().evaluate(_run(), DatasetCase(input="q"))
    assert score.score == 1.0 and score.passed is True


# --- ToolTrajectory -----------------------------------------------


def test_tool_trajectory_exact_and_reordered() -> None:
    ev = ToolTrajectory(min_score=1.0)
    case = _case(ExpectedToolCall("a"), ExpectedToolCall("b"), ExpectedToolCall("c"))

    exact = ev.evaluate(_run(_tc("a"), _tc("b"), _tc("c")), case)
    assert exact.score == 1.0 and exact.passed is True

    reordered = ev.evaluate(_run(_tc("a"), _tc("c"), _tc("b")), case)
    assert reordered.score == pytest.approx(2 / 3)  # LCS length 2 of 3
    assert reordered.passed is False

    missing = ev.evaluate(_run(_tc("a"), _tc("b")), case)
    assert missing.score == pytest.approx(2 * 2 / (3 + 2))  # LCS 2, dice 4/5

    empty = ev.evaluate(_run(), case)
    assert empty.score == 0.0


def test_tool_trajectory_without_labels_raises() -> None:
    with pytest.raises(ConfigError, match="expected_tool_calls"):
        ToolTrajectory().evaluate(_run(_tc("a")), DatasetCase(input="q"))


# --- build_evaluators wiring --------------------------------------


def test_build_agent_evaluators() -> None:
    evaluators = build_evaluators(
        [
            {"type": "tool_selection", "min_score": 0.5},
            {"type": "tool_arguments"},
            {"type": "tool_success"},
            {"type": "tool_trajectory", "name": "traj"},
        ]
    )
    assert {type(e).__name__ for e in evaluators} == {
        "ToolSelection",
        "ToolArguments",
        "ToolSuccess",
        "ToolTrajectory",
    }
    sel = next(e for e in evaluators if isinstance(e, ToolSelection))
    assert sel.min_score == 0.5
    traj = next(e for e in evaluators if isinstance(e, ToolTrajectory))
    assert traj.name == "traj"


def test_build_agent_evaluator_rejects_bad_threshold() -> None:
    with pytest.raises(ConfigError, match="within"):
        build_evaluators([{"type": "tool_success", "min_score": 2}])
