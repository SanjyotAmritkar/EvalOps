"""Tests for evalops.runner.run_experiment."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import FrozenInstanceError

import pytest

from evalops.domain.contracts import Evaluator, ProviderClient, ProviderError, ProviderResponse
from evalops.domain.entities import Dataset, DatasetCase, EvaluationRun, Experiment, SystemVersion
from evalops.domain.enums import EvaluatorFamily, ProviderName
from evalops.domain.value_objects import (
    EvaluatorScore,
    RetrievedItem,
    ToolCall,
    UsageMetrics,
)
from evalops.errors import ConfigError
from evalops.evaluators import ExactMatch, RegexMatch
from evalops.runner import RunOutcome, run_experiment

# --- test doubles ------------------------------------------------------------


class _StubProvider:
    """Records the prompts it is asked to complete, in call order."""

    def __init__(
        self,
        name: str,
        *,
        response: str = "ok",
        fail_on: Collection[str] = (),
        raises: type[BaseException] | None = None,
        retrieval: tuple[RetrievedItem, ...] = (),
        tool_calls: tuple[ToolCall, ...] = (),
    ) -> None:
        self.name = name
        self._response = response
        self._fail_on = set(fail_on)
        self._raises = raises
        self._retrieval = retrieval
        self._tool_calls = tool_calls
        self.seen: list[str] = []

    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        self.seen.append(prompt)
        if self._raises is not None:
            raise self._raises("stub blew up")
        if prompt in self._fail_on:
            raise ProviderError(f"stub failure for {prompt!r}")
        return ProviderResponse(
            text=self._response,
            usage=UsageMetrics(prompt_tokens=2, completion_tokens=3, latency_ms=7.0),
            retrieval=self._retrieval,
            tool_calls=self._tool_calls,
        )


class _BoomEvaluator:
    name = "boom"
    family = EvaluatorFamily.DETERMINISTIC

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        raise RuntimeError("evaluator bug")


# --- fixtures --------------------------------------------------------------------


def _sv(
    *, provider: ProviderName = ProviderName.OPENAI, prompt: str = "P: ${input}"
) -> SystemVersion:
    return SystemVersion(
        project_id="proj",
        name="cfg",
        version="v",
        provider=provider,
        model="m",
        prompt_template=prompt,
    )


def _dataset(*inputs: str) -> Dataset:
    cases = tuple(
        DatasetCase(input=text, expected_output="ok", id=f"case-{i}")
        for i, text in enumerate(inputs)
    )
    return Dataset(project_id="proj", name="ds", version=1, cases=cases)


def _experiment(
    dataset: Dataset, baseline: SystemVersion, candidate: SystemVersion, *, repeats: int = 1
) -> Experiment:
    return Experiment(
        project_id="proj",
        dataset_id=dataset.id,
        baseline_version_id=baseline.id,
        candidate_version_id=candidate.id,
        repeats=repeats,
    )


def _run(
    *,
    baseline: SystemVersion,
    candidate: SystemVersion,
    dataset: Dataset,
    providers: Mapping[ProviderName, ProviderClient],
    evaluators: Sequence[Evaluator] = (),
    repeats: int = 1,
) -> RunOutcome:
    experiment = _experiment(dataset, baseline, candidate, repeats=repeats)
    return run_experiment(
        experiment,
        dataset,
        baseline,
        candidate,
        providers=providers,
        evaluators=evaluators,
    )


# --- tests ---------------------------------------------------------------------


def test_execution_order_is_deterministic() -> None:
    baseline = _sv(prompt="B: ${input}")
    candidate = _sv(prompt="C: ${input}")
    stub = _StubProvider("openai")
    dataset = _dataset("a", "b")

    outcome = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=dataset,
        providers={ProviderName.OPENAI: stub},
        repeats=2,
    )

    assert stub.seen == ["B: a", "B: a", "B: b", "B: b", "C: a", "C: a", "C: b", "C: b"]
    assert [(r.system_version_id, r.case_id, r.repeat_index) for r in outcome.runs] == [
        (baseline.id, "case-0", 0),
        (baseline.id, "case-0", 1),
        (baseline.id, "case-1", 0),
        (baseline.id, "case-1", 1),
        (candidate.id, "case-0", 0),
        (candidate.id, "case-0", 1),
        (candidate.id, "case-1", 0),
        (candidate.id, "case-1", 1),
    ]


def test_both_versions_execute_over_every_case() -> None:
    baseline, candidate = _sv(), _sv(prompt="X: ${input}")
    outcome = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=_dataset("a", "b", "c"),
        providers={ProviderName.OPENAI: _StubProvider("openai")},
    )

    assert len(outcome.runs) == 6
    assert {r.system_version_id for r in outcome.runs} == {baseline.id, candidate.id}


def test_repeats_produce_indices_zero_to_n_minus_one() -> None:
    baseline, candidate = _sv(), _sv(prompt="X: ${input}")
    outcome = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=_dataset("only"),
        providers={ProviderName.OPENAI: _StubProvider("openai")},
        repeats=3,
    )

    per_version: dict[str, list[int]] = {baseline.id: [], candidate.id: []}
    for run in outcome.runs:
        per_version[run.system_version_id].append(run.repeat_index)
    assert per_version[baseline.id] == [0, 1, 2]
    assert per_version[candidate.id] == [0, 1, 2]


def test_run_records_domain_ids() -> None:
    baseline, candidate = _sv(), _sv(prompt="X: ${input}")
    dataset = _dataset("a")
    experiment = _experiment(dataset, baseline, candidate)

    outcome = run_experiment(
        experiment,
        dataset,
        baseline,
        candidate,
        providers={ProviderName.OPENAI: _StubProvider("openai")},
        evaluators=[],
    )

    for run in outcome.runs:
        assert run.experiment_id == experiment.id
        assert run.system_version_id in {baseline.id, candidate.id}
        assert run.case_id == "case-0"
        assert run.repeat_index == 0


def test_successful_output_and_usage_are_preserved() -> None:
    baseline, candidate = _sv(), _sv(prompt="X: ${input}")
    outcome = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=_dataset("a"),
        providers={ProviderName.OPENAI: _StubProvider("openai", response="hello")},
    )

    run = outcome.runs[0]
    assert run.error is None
    assert run.output == "hello"
    assert (run.usage.prompt_tokens, run.usage.completion_tokens) == (2, 3)
    assert run.usage.latency_ms == 7.0
    assert run.retrieval == ()  # text-only provider: no retrieval evidence
    assert run.tool_calls == ()  # text-only provider: no tool-call evidence


def test_provider_retrieval_evidence_is_threaded_onto_the_run() -> None:
    baseline, candidate = _sv(), _sv(prompt="X: ${input}")
    items = (
        RetrievedItem(doc_id="d1", content="alpha", rank=0, score=0.5),
        RetrievedItem(doc_id="d2", content="beta", rank=1),
    )
    outcome = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=_dataset("a"),
        providers={ProviderName.OPENAI: _StubProvider("openai", retrieval=items)},
    )

    assert outcome.runs[0].retrieval == items
    # a failed run carries no retrieval evidence
    failed = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=_dataset("a"),
        providers={
            ProviderName.OPENAI: _StubProvider("openai", fail_on={"P: a", "X: a"}, retrieval=items)
        },
    )
    assert all(run.retrieval == () for run in failed.runs)


def test_provider_tool_call_evidence_is_threaded_onto_the_run() -> None:
    baseline, candidate = _sv(), _sv(prompt="X: ${input}")
    calls = (
        ToolCall(name="search", arguments={"q": "cats"}),
        ToolCall(name="done", ok=False, error="nope"),
    )
    outcome = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=_dataset("a"),
        providers={ProviderName.OPENAI: _StubProvider("openai", tool_calls=calls)},
    )
    assert outcome.runs[0].tool_calls == calls

    failed = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=_dataset("a"),
        providers={
            ProviderName.OPENAI: _StubProvider("openai", fail_on={"P: a", "X: a"}, tool_calls=calls)
        },
    )
    assert all(run.tool_calls == () for run in failed.runs)


def test_one_case_result_per_run_in_order() -> None:
    baseline, candidate = _sv(), _sv(prompt="X: ${input}")
    outcome = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=_dataset("a", "b"),
        providers={ProviderName.OPENAI: _StubProvider("openai")},
    )

    assert len(outcome.case_results) == len(outcome.runs)
    assert all(cr.run_id == r.id for cr, r in zip(outcome.case_results, outcome.runs, strict=True))


def test_successful_run_has_one_score_per_evaluator() -> None:
    baseline, candidate = _sv(), _sv(prompt="X: ${input}")
    outcome = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=_dataset("a"),
        providers={ProviderName.OPENAI: _StubProvider("openai", response="ok")},
        evaluators=[ExactMatch(), RegexMatch(pattern=".")],
    )

    for case_result in outcome.case_results:
        assert [s.evaluator for s in case_result.scores] == ["exact_match", "regex_match"]


def test_providers_are_resolved_per_system_version() -> None:
    baseline = _sv(provider=ProviderName.OPENAI, prompt="B: ${input}")
    candidate = _sv(provider=ProviderName.ANTHROPIC, prompt="C: ${input}")
    openai = _StubProvider("openai", response="from-openai")
    anthropic = _StubProvider("anthropic", response="from-anthropic")

    outcome = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=_dataset("a"),
        providers={ProviderName.OPENAI: openai, ProviderName.ANTHROPIC: anthropic},
    )

    assert openai.seen == ["B: a"]
    assert anthropic.seen == ["C: a"]
    assert {r.system_version_id: r.output for r in outcome.runs} == {
        baseline.id: "from-openai",
        candidate.id: "from-anthropic",
    }


def test_provider_error_yields_failed_run_and_empty_case_result() -> None:
    baseline, candidate = _sv(prompt="B: ${input}"), _sv(prompt="C: ${input}")
    stub = _StubProvider("openai", fail_on={"B: a"})

    outcome = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=_dataset("a"),
        providers={ProviderName.OPENAI: stub},
        evaluators=[ExactMatch()],
    )

    failed = next(r for r in outcome.runs if r.system_version_id == baseline.id)
    assert failed.output == ""
    assert failed.error is not None and "stub failure" in failed.error
    assert failed.usage == UsageMetrics()
    failed_result = next(cr for cr in outcome.case_results if cr.run_id == failed.id)
    assert failed_result.scores == ()


def test_experiment_continues_after_a_provider_failure() -> None:
    baseline, candidate = _sv(prompt="B: ${input}"), _sv(prompt="C: ${input}")
    stub = _StubProvider("openai", fail_on={"B: a"})

    outcome = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=_dataset("a", "b"),
        providers={ProviderName.OPENAI: stub},
        evaluators=[ExactMatch()],
    )

    assert len(outcome.runs) == 4  # 2 versions x 2 cases
    failures = [r for r in outcome.runs if r.error is not None]
    successes = {r.id for r in outcome.runs if r.error is None}
    assert len(failures) == 1
    assert len(successes) == 3
    scored = [cr for cr in outcome.case_results if cr.run_id in successes]
    assert all(len(cr.scores) == 1 for cr in scored)


def test_multiple_failures_do_not_abort_the_experiment() -> None:
    baseline, candidate = _sv(prompt="B: ${input}"), _sv(prompt="C: ${input}")
    stub = _StubProvider("openai", fail_on={"B: a", "C: b"})

    outcome = _run(
        baseline=baseline,
        candidate=candidate,
        dataset=_dataset("a", "b"),
        providers={ProviderName.OPENAI: stub},
    )

    assert len(outcome.runs) == 4
    assert sum(r.error is not None for r in outcome.runs) == 2


def test_runtime_error_from_provider_propagates() -> None:
    baseline, candidate = _sv(), _sv(prompt="X: ${input}")
    with pytest.raises(RuntimeError):
        _run(
            baseline=baseline,
            candidate=candidate,
            dataset=_dataset("a"),
            providers={ProviderName.OPENAI: _StubProvider("openai", raises=RuntimeError)},
        )


def test_evaluator_exception_propagates() -> None:
    baseline, candidate = _sv(), _sv(prompt="X: ${input}")
    with pytest.raises(RuntimeError):
        _run(
            baseline=baseline,
            candidate=candidate,
            dataset=_dataset("a"),
            providers={ProviderName.OPENAI: _StubProvider("openai")},
            evaluators=[_BoomEvaluator()],
        )


def test_prompt_config_error_propagates() -> None:
    baseline = _sv(prompt="no placeholder")
    candidate = _sv(prompt="X: ${input}")
    with pytest.raises(ConfigError):
        _run(
            baseline=baseline,
            candidate=candidate,
            dataset=_dataset("a"),
            providers={ProviderName.OPENAI: _StubProvider("openai")},
        )


def test_missing_provider_mapping_is_rejected() -> None:
    baseline = _sv(provider=ProviderName.OPENAI)
    candidate = _sv(provider=ProviderName.ANTHROPIC, prompt="X: ${input}")
    with pytest.raises(ConfigError, match="anthropic"):
        _run(
            baseline=baseline,
            candidate=candidate,
            dataset=_dataset("a"),
            providers={ProviderName.OPENAI: _StubProvider("openai")},
        )


def test_id_mismatch_is_rejected_before_execution() -> None:
    baseline, candidate = _sv(), _sv(prompt="X: ${input}")
    dataset = _dataset("a")
    other_dataset = _dataset("a")  # different generated id
    experiment = _experiment(dataset, baseline, candidate)
    stub = _StubProvider("openai")

    with pytest.raises(ConfigError, match="dataset id"):
        run_experiment(
            experiment,
            other_dataset,
            baseline,
            candidate,
            providers={ProviderName.OPENAI: stub},
            evaluators=[],
        )
    assert stub.seen == []


def test_duplicate_evaluator_names_are_rejected() -> None:
    baseline, candidate = _sv(), _sv(prompt="X: ${input}")
    with pytest.raises(ConfigError, match="unique"):
        _run(
            baseline=baseline,
            candidate=candidate,
            dataset=_dataset("a"),
            providers={ProviderName.OPENAI: _StubProvider("openai")},
            evaluators=[RegexMatch(pattern="a", name="dup"), RegexMatch(pattern="b", name="dup")],
        )


def test_run_outcome_is_immutable() -> None:
    outcome = RunOutcome(runs=(), case_results=())
    with pytest.raises(FrozenInstanceError):
        outcome.runs = ()  # type: ignore[misc]
