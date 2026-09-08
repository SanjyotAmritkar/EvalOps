"""Load a YAML run config into an in-memory RunPlan of domain objects.

Small explicit parsing -- no schema framework. ``yaml.safe_load`` only. All
malformed user input becomes a :class:`ConfigError`. The dataset path is
resolved relative to the config file, not the working directory.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import yaml

from evalops.aggregate import expected_metric_names
from evalops.datasets import load_jsonl
from evalops.domain.contracts import Evaluator, ProviderClient
from evalops.domain.entities import (
    Dataset,
    Experiment,
    Project,
    ReleasePolicy,
    SystemVersion,
)
from evalops.domain.enums import ProviderName
from evalops.domain.errors import DomainValidationError
from evalops.errors import ConfigError
from evalops.evaluators import Contains, ExactMatch, RegexMatch
from evalops.ollama import DEFAULT_BASE_URL, DEFAULT_TIMEOUT_SECONDS, OllamaProvider, build_options
from evalops.providers import MockProvider

_SUPPORTED_BACKENDS = frozenset({"mock", "ollama"})

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class RunPlan:
    """Everything needed to execute one evaluation. No runtime state or results."""

    project: Project
    dataset: Dataset
    experiment: Experiment
    baseline: SystemVersion
    candidate: SystemVersion
    evaluators: tuple[Evaluator, ...]
    policy: ReleasePolicy | None
    providers: Mapping[ProviderName, ProviderClient]


def load_run_plan(config_path: str | Path) -> RunPlan:
    """Parse the YAML file at ``config_path`` and assemble a :class:`RunPlan`."""
    path = Path(config_path)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc
    try:
        loaded = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML ({exc})") from exc

    root = _as_mapping(loaded, "config root")

    project = _build(lambda: Project(name=_req_str(root, "project", "config")), "project")

    dataset_section = _as_mapping(_req(root, "dataset", "config"), "dataset")
    dataset_path = (path.parent / _req_str(dataset_section, "path", "dataset")).resolve()
    dataset_name = _opt_str(dataset_section, "name", "dataset", default=None)
    dataset = _build(
        lambda: load_jsonl(dataset_path, project_id=project.id, name=dataset_name),
        "dataset",
    )

    backend = _read_backend(root)
    repeats = _opt_int(root, "repeats", "config", default=1)
    if repeats < 1:
        raise ConfigError(f"config.repeats must be >= 1, got {repeats}")

    baseline = _build_system_version(root, "baseline", project.id)
    candidate = _build_system_version(root, "candidate", project.id)

    experiment = _build(
        lambda: Experiment(
            project_id=project.id,
            dataset_id=dataset.id,
            baseline_version_id=baseline.id,
            candidate_version_id=candidate.id,
            repeats=repeats,
        ),
        "experiment",
    )

    evaluators = _build_evaluators(root)
    _check_reference_outputs(evaluators, dataset)

    policy = _build_policy(root, [e.name for e in evaluators])

    providers = _build_providers(backend, root, baseline, candidate)

    return RunPlan(
        project=project,
        dataset=dataset,
        experiment=experiment,
        baseline=baseline,
        candidate=candidate,
        evaluators=evaluators,
        policy=policy,
        providers=providers,
    )


# --- section builders ---------------------------------------------------------


def _build_system_version(root: Mapping[str, Any], key: str, project_id: str) -> SystemVersion:
    section = _as_mapping(_req(root, key, "config"), key)
    provider_name = _req_str(section, "provider", key)
    try:
        provider = ProviderName(provider_name)
    except ValueError as exc:
        allowed = sorted(p.value for p in ProviderName)
        raise ConfigError(f"{key}.provider {provider_name!r} is not one of {allowed}") from exc

    parameters = _opt_mapping(section, "parameters", key)
    return _build(
        lambda: SystemVersion(
            project_id=project_id,
            name=_req_str(section, "name", key),
            version=_req_str(section, "version", key),
            provider=provider,
            model=_req_str(section, "model", key),
            prompt_template=_req_str(section, "prompt_template", key),
            parameters=parameters,
        ),
        key,
    )


def _build_evaluators(root: Mapping[str, Any]) -> tuple[Evaluator, ...]:
    specs = _req(root, "evaluators", "config")
    if not isinstance(specs, list) or not specs:
        raise ConfigError("config.evaluators must be a non-empty list")

    built: list[Evaluator] = []
    seen: set[str] = set()
    for index, spec in enumerate(specs):
        label = f"evaluators[{index}]"
        mapping = _as_mapping(spec, label)
        evaluator_type = _req_str(mapping, "type", label)
        name = _opt_str(mapping, "name", label, default=None)

        if evaluator_type == "exact_match":
            evaluator: Evaluator = ExactMatch(
                case_sensitive=_opt_bool(mapping, "case_sensitive", label, default=True),
                name=name or "exact_match",
            )
        elif evaluator_type == "contains":
            evaluator = Contains(
                case_sensitive=_opt_bool(mapping, "case_sensitive", label, default=False),
                name=name or "contains",
            )
        elif evaluator_type == "regex_match":
            evaluator = RegexMatch(
                pattern=_req_str(mapping, "pattern", label),
                name=name or "regex_match",
            )
        else:
            raise ConfigError(
                f"{label}.type {evaluator_type!r} is not one of "
                "['exact_match', 'contains', 'regex_match']"
            )

        if evaluator.name in seen:
            raise ConfigError(f"duplicate evaluator name {evaluator.name!r}")
        seen.add(evaluator.name)
        built.append(evaluator)
    return tuple(built)


def _check_reference_outputs(evaluators: Sequence[Evaluator], dataset: Dataset) -> None:
    if not any(isinstance(e, ExactMatch | Contains) for e in evaluators):
        return
    missing = [case.id for case in dataset.cases if case.expected_output is None]
    if missing:
        raise ConfigError(
            f"exact_match/contains require expected_output on every case; missing for: {missing}"
        )


def _build_policy(root: Mapping[str, Any], evaluator_names: Sequence[str]) -> ReleasePolicy | None:
    if "release_policy" not in root or root["release_policy"] is None:
        return None
    section = _as_mapping(root["release_policy"], "release_policy")

    raw_thresholds = _opt_mapping(section, "thresholds", "release_policy")
    thresholds: dict[str, float] = {}
    for metric, value in raw_thresholds.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"release_policy.thresholds[{metric!r}] must be a number")
        thresholds[metric] = float(value)

    producible = set(expected_metric_names(evaluator_names))
    unknown = sorted(m for m in thresholds if m not in producible)
    if unknown:
        raise ConfigError(
            f"release_policy.thresholds names metric(s) this run cannot produce: {unknown}; "
            f"producible metrics are {sorted(producible)}"
        )

    return _build(
        lambda: ReleasePolicy(
            name=_req_str(section, "name", "release_policy"),
            thresholds=thresholds,
            max_safety_violations=_opt_int(
                section, "max_safety_violations", "release_policy", default=0
            ),
        ),
        "release_policy",
    )


def _read_backend(root: Mapping[str, Any]) -> str:
    execution = _as_mapping(_req(root, "execution", "config"), "execution")
    backend = _req_str(execution, "backend", "execution")
    if backend not in _SUPPORTED_BACKENDS:
        raise ConfigError(
            f"execution.backend {backend!r} is not supported; "
            f"supported backends: {sorted(_SUPPORTED_BACKENDS)}"
        )
    return backend


def _build_providers(
    backend: str,
    root: Mapping[str, Any],
    baseline: SystemVersion,
    candidate: SystemVersion,
) -> Mapping[ProviderName, ProviderClient]:
    if backend == "mock":
        # Deterministic simulation: MockProvider stands in for each declared identity.
        return {name: MockProvider() for name in {baseline.provider, candidate.provider}}

    # backend == "ollama": real local execution -- identities must actually be Ollama.
    for label, version in (("baseline", baseline), ("candidate", candidate)):
        if version.provider is not ProviderName.OLLAMA:
            raise ConfigError(
                f"execution.backend is 'ollama' but {label}.provider is "
                f"{version.provider.value!r}; it must be 'ollama'"
            )
        build_options(version.parameters)  # reject unsupported generation params early

    execution = _as_mapping(root["execution"], "execution")
    base_url = _opt_str(execution, "base_url", "execution", default=None) or DEFAULT_BASE_URL
    timeout_seconds = _opt_number(
        execution, "timeout_seconds", "execution", default=DEFAULT_TIMEOUT_SECONDS
    )
    if timeout_seconds <= 0:
        raise ConfigError("execution.timeout_seconds must be greater than 0")
    return {ProviderName.OLLAMA: OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds)}


# --- small typed parsing helpers -------------------------------------------------


def _build(factory: Callable[[], _T], label: str) -> _T:
    try:
        return factory()
    except DomainValidationError as exc:
        raise ConfigError(f"{label}: {exc}") from exc


def _as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{label} must be a mapping, got {type(value).__name__}")
    return value


def _req(mapping: Mapping[str, Any], key: str, label: str) -> Any:
    if key not in mapping:
        raise ConfigError(f"{label}: missing required field {key!r}")
    return mapping[key]


def _req_str(mapping: Mapping[str, Any], key: str, label: str) -> str:
    value = _req(mapping, key, label)
    if not isinstance(value, str):
        raise ConfigError(f"{label}.{key} must be a string, got {type(value).__name__}")
    return value


def _opt_str(
    mapping: Mapping[str, Any], key: str, label: str, *, default: str | None
) -> str | None:
    if key not in mapping or mapping[key] is None:
        return default
    value = mapping[key]
    if not isinstance(value, str):
        raise ConfigError(f"{label}.{key} must be a string, got {type(value).__name__}")
    return value


def _opt_bool(mapping: Mapping[str, Any], key: str, label: str, *, default: bool) -> bool:
    if key not in mapping:
        return default
    value = mapping[key]
    if not isinstance(value, bool):
        raise ConfigError(f"{label}.{key} must be a boolean, got {type(value).__name__}")
    return value


def _opt_int(mapping: Mapping[str, Any], key: str, label: str, *, default: int) -> int:
    if key not in mapping:
        return default
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{label}.{key} must be an integer, got {type(value).__name__}")
    return value


def _opt_number(mapping: Mapping[str, Any], key: str, label: str, *, default: float) -> float:
    if key not in mapping:
        return default
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{label}.{key} must be a number, got {type(value).__name__}")
    return float(value)


def _opt_mapping(mapping: Mapping[str, Any], key: str, label: str) -> Mapping[str, Any]:
    if key not in mapping or mapping[key] is None:
        return {}
    return _as_mapping(mapping[key], f"{label}.{key}")
