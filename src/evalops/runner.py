"""Synchronous evaluation runner.

Executes one ``Experiment`` over a baseline and a candidate ``SystemVersion``
against a ``Dataset``, using injected ``ProviderClient`` implementations and
configured ``Evaluator`` implementations, and returns the raw
``EvaluationRun`` / ``CaseResult`` records. No aggregation, no metrics, no
release decision -- those belong to later checkpoints.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from evalops.domain.contracts import Evaluator, ProviderClient, ProviderError
from evalops.domain.entities import (
    CaseResult,
    Dataset,
    DatasetCase,
    EvaluationRun,
    Experiment,
    SystemVersion,
)
from evalops.domain.enums import ProviderName
from evalops.domain.value_objects import UsageMetrics
from evalops.errors import ConfigError
from evalops.prompt import render_prompt


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """Raw output of one runner execution.

    ``runs`` and ``case_results`` are parallel and in execution order:
    ``case_results[i]`` is the scored outcome of ``runs[i]`` and
    ``case_results[i].run_id == runs[i].id``.
    """

    runs: tuple[EvaluationRun, ...]
    case_results: tuple[CaseResult, ...]


def run_experiment(
    experiment: Experiment,
    dataset: Dataset,
    baseline_version: SystemVersion,
    candidate_version: SystemVersion,
    *,
    providers: Mapping[ProviderName, ProviderClient],
    evaluators: Sequence[Evaluator],
) -> RunOutcome:
    """Execute ``experiment`` and return its runs and per-run case results.

    Deterministic order: baseline version, then candidate version; within each,
    dataset case order; within each case, ``repeat_index`` 0..repeats-1.

    A ``ProviderError`` from a single ``complete`` call is recorded as a failed
    ``EvaluationRun`` (empty output, zero usage, ``error`` set) with an empty
    ``CaseResult``; execution continues. Every other exception -- prompt
    ``ConfigError``, an evaluator raising, a bug in a provider -- propagates.
    """
    _preflight(experiment, dataset, baseline_version, candidate_version, providers, evaluators)

    runs: list[EvaluationRun] = []
    case_results: list[CaseResult] = []

    for system_version in (baseline_version, candidate_version):
        provider = providers[system_version.provider]
        for case in dataset.cases:
            prompt = render_prompt(system_version.prompt_template, case.input)
            for repeat_index in range(experiment.repeats):
                run = _execute(experiment, system_version, case, repeat_index, prompt, provider)
                runs.append(run)
                case_results.append(_score(run, case, evaluators))

    return RunOutcome(runs=tuple(runs), case_results=tuple(case_results))


def _execute(
    experiment: Experiment,
    system_version: SystemVersion,
    case: DatasetCase,
    repeat_index: int,
    prompt: str,
    provider: ProviderClient,
) -> EvaluationRun:
    try:
        response = provider.complete(prompt, system_version)
    except ProviderError as exc:
        return EvaluationRun(
            experiment_id=experiment.id,
            system_version_id=system_version.id,
            case_id=case.id,
            repeat_index=repeat_index,
            output="",
            usage=UsageMetrics(),
            error=str(exc).strip() or type(exc).__name__,
        )
    return EvaluationRun(
        experiment_id=experiment.id,
        system_version_id=system_version.id,
        case_id=case.id,
        repeat_index=repeat_index,
        output=response.text,
        usage=response.usage,
    )


def _score(run: EvaluationRun, case: DatasetCase, evaluators: Sequence[Evaluator]) -> CaseResult:
    if run.error is not None:
        return CaseResult(run_id=run.id, scores=())
    scores = tuple(evaluator.evaluate(run, case) for evaluator in evaluators)
    return CaseResult(run_id=run.id, scores=scores)


def _preflight(
    experiment: Experiment,
    dataset: Dataset,
    baseline_version: SystemVersion,
    candidate_version: SystemVersion,
    providers: Mapping[ProviderName, ProviderClient],
    evaluators: Sequence[Evaluator],
) -> None:
    for label, got, expected in (
        ("dataset", dataset.id, experiment.dataset_id),
        ("baseline_version", baseline_version.id, experiment.baseline_version_id),
        ("candidate_version", candidate_version.id, experiment.candidate_version_id),
    ):
        if got != expected:
            raise ConfigError(
                f"{label} id {got!r} does not match the experiment's {label}_id {expected!r}"
            )

    required = {baseline_version.provider, candidate_version.provider}
    missing = sorted(name.value for name in required - set(providers))
    if missing:
        raise ConfigError(f"no ProviderClient supplied for provider(s): {missing}")

    names = [evaluator.name for evaluator in evaluators]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ConfigError(f"evaluator names must be unique; duplicated: {duplicates}")
