"""Deterministic agent regression, end to end through the existing pipeline.

A MockProvider baseline selects the right tools with the right arguments in the
expected order; the candidate sends wrong arguments and adds an extra tool on
every case. The run goes through the ordinary ``run_evaluation`` path -- no
agent runner, no agent gate -- and plain ReleasePolicy thresholds BLOCK on:

* ``tool_arguments.pass_rate`` -- pass rate and mean score both collapse, and
* ``tool_selection.mean_score`` -- a graded regression (1.0 -> 0.667) that is
  invisible to ``tool_selection.pass_rate`` because both stay above the
  evaluator's own pass threshold. This is the CP 9.1 blind spot, now fixed by
  the generic ``<evaluator>.mean_score`` metric.
"""

from __future__ import annotations

from typing import Any

from evalops.domain.entities import (
    Dataset,
    DatasetCase,
    Experiment,
    Project,
    ReleasePolicy,
    SystemVersion,
)
from evalops.domain.enums import ProviderName, ReleaseDecision
from evalops.domain.value_objects import ExpectedToolCall
from evalops.evaluators import build_evaluators
from evalops.execution import ExecutionSpec, build_providers, run_evaluation

_PROJECT = Project(name="agent-e2e")
_TEMPLATE = "Q: ${input}"
_TOPICS = ["cats", "dogs", "birds", "fish"]


def _mock_params(*, misbehave: bool) -> dict[str, Any]:
    tool_calls: dict[str, list[dict[str, Any]]] = {}
    for topic in _TOPICS:
        prompt = f"Q: {topic}"
        if misbehave:
            tool_calls[prompt] = [
                {"name": "search", "arguments": {"q": "WRONG"}},
                {"name": "summarize", "arguments": {}},
                {"name": "debug", "arguments": {}},  # unexpected extra tool
            ]
        else:
            tool_calls[prompt] = [
                {"name": "search", "arguments": {"q": topic}},
                {"name": "summarize", "arguments": {}},
            ]
    return {
        "mock": {
            "responses": {f"Q: {t}": "ok" for t in _TOPICS},
            "tool_calls": tool_calls,
            "latency_ms": 5,
        }
    }


def _sv(version: str, params: dict[str, Any]) -> SystemVersion:
    return SystemVersion(
        project_id=_PROJECT.id,
        name="cfg",
        version=version,
        provider=ProviderName.OPENAI,
        model="m",
        prompt_template=_TEMPLATE,
        parameters=params,
    )


def _dataset() -> Dataset:
    cases = tuple(
        DatasetCase(
            input=topic,
            expected_output="ok",
            expected_tool_calls=(
                ExpectedToolCall("search", {"q": topic}),
                ExpectedToolCall("summarize"),
            ),
        )
        for topic in _TOPICS
    )
    return Dataset(project_id=_PROJECT.id, name="agent", version=1, cases=cases)


def test_agent_regression_blocks_through_generic_gate() -> None:
    dataset = _dataset()
    baseline = _sv("v1", _mock_params(misbehave=False))
    candidate = _sv("v2", _mock_params(misbehave=True))
    experiment = Experiment(
        project_id=_PROJECT.id,
        dataset_id=dataset.id,
        baseline_version_id=baseline.id,
        candidate_version_id=candidate.id,
        repeats=2,
    )
    evaluators = build_evaluators(
        [
            {"type": "tool_selection", "min_score": 0.5},
            {"type": "tool_arguments", "min_score": 1.0},
            {"type": "tool_success", "min_score": 1.0},
        ]
    )
    policy = ReleasePolicy(
        name="agent",
        thresholds={
            "tool_selection.mean_score": 0.10,
            "tool_arguments.pass_rate": 0.10,
        },
    )
    providers = build_providers(ExecutionSpec(backend="mock"), baseline, candidate)

    outcome = run_evaluation(
        experiment,
        dataset,
        baseline,
        candidate,
        policy,
        evaluators=evaluators,
        providers=providers,
    )

    runs = outcome.outcome.runs
    # tool evidence captured through the normal runner
    assert all(len(r.tool_calls) >= 2 for r in runs)
    cand_runs = [r for r in runs if r.system_version_id == candidate.id]
    assert all(r.tool_calls[0].name == "search" for r in cand_runs)
    assert all(dict(r.tool_calls[0].arguments) == {"q": "WRONG"} for r in cand_runs)

    m = {mc.metric: mc for mc in outcome.result.metrics}

    # tool_arguments: pass_rate AND mean_score both collapse
    assert m["tool_arguments.pass_rate"].baseline_value == 1.0
    assert m["tool_arguments.pass_rate"].candidate_value == 0.0
    assert m["tool_arguments.mean_score"].candidate_value == 0.0

    # tool_selection: pass_rate is UNCHANGED (both above the 0.5 threshold) but
    # mean_score shows the graded regression -- the CP 9.1 blind spot, fixed.
    assert m["tool_selection.pass_rate"].baseline_value == 1.0
    assert m["tool_selection.pass_rate"].candidate_value == 1.0
    assert m["tool_selection.mean_score"].baseline_value == 1.0
    assert m["tool_selection.mean_score"].candidate_value < 0.7

    # tool_success does not regress
    assert m["tool_success.pass_rate"].candidate_value == 1.0

    # paired statistical evidence produced for the graded metric, same path
    ev = {e.metric: e for e in outcome.result.evidence}
    assert ev["tool_selection.mean_score"].n_pairs == 8
    assert ev["tool_selection.mean_score"].kind == "continuous"

    # ordinary release gate BLOCKs, on both metrics, via generic logic
    assert outcome.gate.decision is ReleaseDecision.BLOCK
    reasons = " ".join(outcome.gate.reasons)
    assert "tool_selection.mean_score" in reasons
    assert "tool_arguments.pass_rate" in reasons
