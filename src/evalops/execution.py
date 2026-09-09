"""Reusable evaluation orchestration: build providers, run the Phase 1 pipeline.

Shared by the YAML config loader and the API. No YAML, no HTTP, no database --
just the glue that turns an ``Experiment`` plus runtime choices into a
``RunOutcome`` / ``EvaluationResult`` / ``GateReport`` via the existing
``run_experiment`` / ``aggregate_results`` / ``evaluate_gate``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from evalops.aggregate import aggregate_results
from evalops.domain.contracts import Evaluator, ProviderClient
from evalops.domain.entities import (
    Dataset,
    EvaluationResult,
    Experiment,
    ReleasePolicy,
    SystemVersion,
)
from evalops.domain.enums import ProviderName
from evalops.errors import ConfigError
from evalops.gate import GateReport, evaluate_gate
from evalops.ollama import DEFAULT_BASE_URL, DEFAULT_TIMEOUT_SECONDS, OllamaProvider, build_options
from evalops.providers import MockProvider
from evalops.runner import RunOutcome, run_experiment
from evalops.stats import MetricEvidence, build_statistical_evidence

Backend = Literal["mock", "ollama"]


@dataclass(frozen=True, slots=True)
class ExecutionSpec:
    """Runtime execution choices -- the parts a YAML ``execution:`` block or an
    API request supplies, that are not part of the persisted experiment.
    """

    backend: Backend = "mock"
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class EvaluationOutcome:
    outcome: RunOutcome
    result: EvaluationResult
    gate: GateReport
    #: Additive statistical view (CP 5.1). One entry per gateable metric where a
    #: paired bootstrap is well-defined; does not affect ``result`` or ``gate``.
    evidence: tuple[MetricEvidence, ...]


def build_providers(
    spec: ExecutionSpec, baseline: SystemVersion, candidate: SystemVersion
) -> Mapping[ProviderName, ProviderClient]:
    """Resolve the provider map for the two system versions under ``spec``."""
    if spec.backend == "mock":
        # Deterministic simulation: MockProvider stands in for each declared identity.
        return {name: MockProvider() for name in {baseline.provider, candidate.provider}}

    # backend == "ollama": real local execution -- identities must actually be Ollama.
    for label, version in (("baseline", baseline), ("candidate", candidate)):
        if version.provider is not ProviderName.OLLAMA:
            raise ConfigError(
                f"execution backend is 'ollama' but {label}.provider is "
                f"{version.provider.value!r}; it must be 'ollama'"
            )
        build_options(version.parameters)  # reject unsupported generation params early
    if spec.timeout_seconds <= 0:
        raise ConfigError("execution timeout_seconds must be greater than 0")
    return {
        ProviderName.OLLAMA: OllamaProvider(
            base_url=spec.base_url, timeout_seconds=spec.timeout_seconds
        )
    }


def run_evaluation(
    experiment: Experiment,
    dataset: Dataset,
    baseline: SystemVersion,
    candidate: SystemVersion,
    policy: ReleasePolicy | None,
    *,
    evaluators: Sequence[Evaluator],
    providers: Mapping[ProviderName, ProviderClient],
) -> EvaluationOutcome:
    """Run the experiment, aggregate the metrics, apply the gate, and attach the
    additive statistical evidence."""
    outcome = run_experiment(
        experiment, dataset, baseline, candidate, providers=providers, evaluators=evaluators
    )
    evaluator_names = [evaluator.name for evaluator in evaluators]
    result = aggregate_results(experiment, outcome, evaluator_names=evaluator_names)
    gate = evaluate_gate(result, policy)
    evidence = build_statistical_evidence(experiment, outcome, evaluator_names=evaluator_names)
    return EvaluationOutcome(outcome=outcome, result=result, gate=gate, evidence=evidence)
