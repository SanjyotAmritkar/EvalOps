"""Deterministic RAG regression, end to end through the existing pipeline.

A MockProvider baseline retrieves both relevant chunks per case and answers in
a grounded way; the candidate drops the second relevant chunk on every case.
The run goes through the ordinary ``run_evaluation`` path -- no RAG-specific
runner, no RAG-specific gate -- and a plain ReleasePolicy threshold on
``retrieval_recall.pass_rate`` BLOCKs the release. ``context_precision`` does
not regress (every retrieved chunk stays relevant), showing the metrics are
independent and flow through the generic evaluator path.
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
from evalops.evaluators import build_evaluators
from evalops.execution import ExecutionSpec, build_providers, run_evaluation

_PROJECT = Project(name="rag-e2e")
_TEMPLATE = "Q: ${input}"

# input -> (answer, chunk_a text, chunk_b text). The answer's content words are
# split across both chunks, so dropping chunk_b lowers recall AND groundedness.
_CASES = {
    "capital of France": (
        "Paris is capital of France located in western Europe",
        "Paris is the capital of France",
        "France is located in western Europe",
    ),
    "boiling point of water": (
        "Water boils at 100 celsius under standard atmospheric pressure",
        "Water boils at 100 degrees celsius",
        "boiling occurs under standard atmospheric pressure at sea level",
    ),
    "author of Hamlet": (
        "William Shakespeare wrote Hamlet during the English renaissance",
        "William Shakespeare wrote the tragedy Hamlet",
        "Hamlet was written during the English renaissance period",
    ),
    "speed of light": (
        "Light travels near 300000 kilometers per second through vacuum",
        "Light travels near 300000 kilometers per second",
        "light propagates through vacuum with no medium",
    ),
}


def _mock_params(*, drop_chunk_b: bool) -> dict[str, Any]:
    responses: dict[str, str] = {}
    retrieval: dict[str, list[dict[str, object]]] = {}
    for case_input, (answer, chunk_a, chunk_b) in _CASES.items():
        prompt = f"Q: {case_input}"
        responses[prompt] = answer
        items = [{"doc_id": f"{case_input}-a", "content": chunk_a, "rank": 0}]
        if not drop_chunk_b:
            items.append({"doc_id": f"{case_input}-b", "content": chunk_b, "rank": 1})
        retrieval[prompt] = items
    return {"mock": {"responses": responses, "retrieval": retrieval, "latency_ms": 5}}


def _system_version(version: str, params: dict[str, Any]) -> SystemVersion:
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
            input=case_input,
            expected_output=answer,
            expected_retrieval_ids=(f"{case_input}-a", f"{case_input}-b"),
        )
        for case_input, (answer, _a, _b) in _CASES.items()
    )
    return Dataset(project_id=_PROJECT.id, name="rag", version=1, cases=cases)


def test_rag_regression_blocks_through_the_existing_gate() -> None:
    dataset = _dataset()
    baseline = _system_version("v1", _mock_params(drop_chunk_b=False))
    candidate = _system_version("v2", _mock_params(drop_chunk_b=True))
    experiment = Experiment(
        project_id=_PROJECT.id,
        dataset_id=dataset.id,
        baseline_version_id=baseline.id,
        candidate_version_id=candidate.id,
        repeats=2,
    )
    evaluators = build_evaluators(
        [
            {"type": "retrieval_recall", "min_recall": 1.0},
            {"type": "context_precision", "min_precision": 1.0},
            {"type": "groundedness", "min_groundedness": 0.7},
        ]
    )
    policy = ReleasePolicy(name="rag", thresholds={"retrieval_recall.pass_rate": 0.10})
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
    base_runs = [r for r in runs if r.system_version_id == baseline.id]
    cand_runs = [r for r in runs if r.system_version_id == candidate.id]

    # retrieval evidence captured through the normal runner
    assert all(len(r.retrieval) == 2 for r in base_runs)
    assert all(len(r.retrieval) == 1 for r in cand_runs)

    metrics = {m.metric: m for m in outcome.result.metrics}

    # RAG metrics entered the ordinary EvaluationResult as <name>.pass_rate
    recall = metrics["retrieval_recall.pass_rate"]
    assert recall.baseline_value == 1.0
    assert recall.candidate_value == 0.0

    grounded = metrics["groundedness_lexical.pass_rate"]
    assert grounded.baseline_value == 1.0
    assert grounded.candidate_value < grounded.baseline_value

    precision = metrics["context_precision.pass_rate"]
    assert precision.baseline_value == precision.candidate_value == 1.0  # not a regression

    # statistical evidence produced for the RAG pass-rate metric, same path
    evidence = {e.metric: e for e in outcome.result.evidence}
    assert evidence["retrieval_recall.pass_rate"].n_pairs == 8

    # the ordinary release gate BLOCKs, with no RAG-specific logic
    assert outcome.gate.decision is ReleaseDecision.BLOCK
    assert any("retrieval_recall.pass_rate" in reason for reason in outcome.gate.reasons)
    assert not any("context_precision" in reason for reason in outcome.gate.reasons)


def test_non_rag_run_is_unaffected() -> None:
    """A dataset with no retrieval labels and a text-only evaluator behaves
    exactly as before -- empty retrieval, the same five metric names, PASS."""
    dataset = Dataset(
        project_id=_PROJECT.id,
        name="plain",
        version=1,
        cases=(DatasetCase(input="capital of France", expected_output="Paris"),),
    )
    params: dict[str, Any] = {
        "mock": {"responses": {"Q: capital of France": "Paris is the capital"}}
    }
    baseline = _system_version("v1", params)
    candidate = _system_version("v2", params)
    experiment = Experiment(
        project_id=_PROJECT.id,
        dataset_id=dataset.id,
        baseline_version_id=baseline.id,
        candidate_version_id=candidate.id,
        repeats=2,
    )
    providers = build_providers(ExecutionSpec(backend="mock"), baseline, candidate)
    outcome = run_evaluation(
        experiment,
        dataset,
        baseline,
        candidate,
        None,
        evaluators=build_evaluators([{"type": "contains"}]),
        providers=providers,
    )

    assert all(run.retrieval == () for run in outcome.outcome.runs)
    assert all(run.tool_calls == () for run in outcome.outcome.runs)
    assert {m.metric for m in outcome.result.metrics} == {
        "success_rate",
        "contains.pass_rate",
        "contains.mean_score",  # CP 9.2: generic, added for every evaluator
        "latency_ms.mean",
        "latency_ms.p95",
        "cost_usd.total",
    }
    assert outcome.gate.decision is ReleaseDecision.PASS
