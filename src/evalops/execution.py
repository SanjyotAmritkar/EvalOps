"""Reusable evaluation orchestration: build providers, run the Phase 1 pipeline.

Shared by the YAML config loader and the API. No YAML, no HTTP, no database --
just the glue that turns an ``Experiment`` plus runtime choices into a
``RunOutcome`` / ``EvaluationResult`` / ``GateReport`` via the existing
``run_experiment`` / ``aggregate_results`` / ``evaluate_gate``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from evalops.aggregate import aggregate_results
from evalops.cloud_providers import cloud_params
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
from evalops.ollama import DEFAULT_BASE_URL, DEFAULT_TIMEOUT_SECONDS, build_options
from evalops.provider_registry import make_provider
from evalops.providers import MockProvider
from evalops.runner import RunOutcome, run_experiment
from evalops.stats import build_statistical_evidence

#: ``mock`` / ``ollama`` are the historical single-backend switches (kept
#: verbatim). ``openai`` / ``anthropic`` are the hosted single-provider modes.
#: ``live`` honours each SystemVersion's own declared ``provider`` -- the
#: cross-provider mode (e.g. an Ollama baseline vs an OpenAI candidate).
Backend = Literal["mock", "ollama", "openai", "anthropic", "live"]

_REAL_BACKENDS: dict[str, ProviderName] = {
    "ollama": ProviderName.OLLAMA,
    "openai": ProviderName.OPENAI,
    "anthropic": ProviderName.ANTHROPIC,
}


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
    #: ``result.evidence`` carries the CP 5.1 paired-bootstrap view; the gate
    #: (CP 5.2) reads it straight off the result.
    result: EvaluationResult
    gate: GateReport


def build_providers(
    spec: ExecutionSpec, baseline: SystemVersion, candidate: SystemVersion
) -> Mapping[ProviderName, ProviderClient]:
    """Resolve the provider map for the two system versions under ``spec``.

    The map is keyed by :class:`ProviderName` and passed straight to
    ``run_experiment``, which already dispatches each SystemVersion to
    ``providers[version.provider]`` -- so a baseline and candidate on different
    providers needs no change to the experiment model, only a two-entry map.
    """
    if spec.backend == "mock":
        # Deterministic simulation: MockProvider stands in for each declared identity.
        return {name: MockProvider() for name in {baseline.provider, candidate.provider}}

    if spec.timeout_seconds <= 0:
        raise ConfigError("execution timeout_seconds must be greater than 0")

    versions = (("baseline", baseline), ("candidate", candidate))

    if spec.backend == "live":
        used = {baseline.provider, candidate.provider}
    else:
        # Single-provider backend: both versions must declare exactly that provider.
        target = _REAL_BACKENDS[spec.backend]
        for label, version in versions:
            if version.provider is not target:
                raise ConfigError(
                    f"execution backend is {spec.backend!r} but {label}.provider is "
                    f"{version.provider.value!r}; it must be {spec.backend!r}"
                )
        used = {target}

    for _, version in versions:
        _validate_generation_params(version)

    providers: dict[ProviderName, ProviderClient] = {}
    for provider_name in used:
        providers[provider_name] = make_provider(
            provider_name,
            # Only Ollama takes a connection URL from the execution block; the
            # hosted providers use their SDK default (or their own env override).
            base_url=spec.base_url if provider_name is ProviderName.OLLAMA else None,
            timeout_seconds=spec.timeout_seconds,
        )
    return providers


_PROVIDER_LABEL = {ProviderName.OPENAI: "OpenAI", ProviderName.ANTHROPIC: "Anthropic"}


def _validate_generation_params(version: SystemVersion) -> None:
    """Fail fast on an unsupported generation parameter for a version's provider."""
    if version.provider is ProviderName.OLLAMA:
        build_options(version.parameters)
    else:
        cloud_params(version.parameters, provider=_PROVIDER_LABEL[version.provider])


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
    """Run the experiment, aggregate the metrics, attach the paired-bootstrap
    statistical evidence, then apply the (statistically-aware) gate."""
    outcome = run_experiment(
        experiment, dataset, baseline, candidate, providers=providers, evaluators=evaluators
    )
    evaluator_names = [evaluator.name for evaluator in evaluators]
    result = aggregate_results(experiment, outcome, evaluator_names=evaluator_names)
    evidence = build_statistical_evidence(experiment, outcome, evaluator_names=evaluator_names)
    result = replace(result, evidence=evidence)
    gate = evaluate_gate(result, policy)
    return EvaluationOutcome(outcome=outcome, result=result, gate=gate)
