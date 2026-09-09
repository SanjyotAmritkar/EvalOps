"""Tests for evalops.config.load_run_plan."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from evalops.cloud_providers import OpenAIProvider
from evalops.config import load_run_plan
from evalops.domain.entities import ReleasePolicy
from evalops.domain.enums import ProviderName
from evalops.errors import ConfigError
from evalops.judge import LLMJudge
from evalops.ollama import DEFAULT_BASE_URL, OllamaProvider
from evalops.providers import MockProvider


def _base() -> dict[str, Any]:
    version = {
        "name": "p",
        "version": "v1",
        "provider": "openai",
        "model": "m",
        "prompt_template": "Q: ${input}",
        "parameters": {"mock": {"responses": {"Q: hi": "yo"}, "default": "d", "latency_ms": 10}},
    }
    candidate = {**copy.deepcopy(version), "version": "v2"}
    return {
        "project": "Test QA",
        "dataset": {"path": "cases.jsonl", "name": "test"},
        "repeats": 1,
        "execution": {"backend": "mock"},
        "baseline": copy.deepcopy(version),
        "candidate": candidate,
        "evaluators": [{"type": "regex_match", "pattern": "."}],
    }


def _write(
    tmp_path: Path,
    config: dict[str, Any],
    *,
    cases: list[dict[str, Any]] | None = None,
) -> Path:
    if cases is None:
        cases = [{"input": "hi", "expected_output": "yo"}]
    (tmp_path / "cases.jsonl").write_text(
        "\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8"
    )
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_valid_config_builds_coherent_objects(tmp_path: Path) -> None:
    plan = load_run_plan(_write(tmp_path, _base()))

    assert plan.project.name == "Test QA"
    assert plan.dataset.project_id == plan.project.id
    assert plan.baseline.project_id == plan.project.id
    assert plan.candidate.project_id == plan.project.id
    assert plan.experiment.project_id == plan.project.id
    assert plan.experiment.dataset_id == plan.dataset.id
    assert plan.experiment.baseline_version_id == plan.baseline.id
    assert plan.experiment.candidate_version_id == plan.candidate.id
    assert plan.policy is None
    assert set(plan.providers) == {ProviderName.OPENAI}
    assert isinstance(plan.providers[ProviderName.OPENAI], MockProvider)


def test_relative_dataset_path_is_resolved_against_the_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "cases.jsonl").write_text(
        '{"input": "hi", "expected_output": "yo"}\n', encoding="utf-8"
    )
    (tmp_path / "conf").mkdir()
    config = _base()
    config["dataset"]["path"] = "../data/cases.jsonl"
    config_path = tmp_path / "conf" / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)  # a cwd that does not contain the dataset

    plan = load_run_plan(config_path)

    assert len(plan.dataset.cases) == 1


def test_yaml_root_must_be_a_mapping(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="config root must be a mapping"):
        load_run_plan(path)


def test_invalid_yaml_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("a: [1, 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_run_plan(path)


def test_missing_required_section(tmp_path: Path) -> None:
    config = _base()
    del config["baseline"]
    with pytest.raises(ConfigError, match="missing required field 'baseline'"):
        load_run_plan(_write(tmp_path, config))


def test_wrong_scalar_type(tmp_path: Path) -> None:
    config = _base()
    config["project"] = 123
    with pytest.raises(ConfigError, match="must be a string"):
        load_run_plan(_write(tmp_path, config))


def test_invalid_provider(tmp_path: Path) -> None:
    config = _base()
    config["baseline"]["provider"] = "gpt-9"
    with pytest.raises(ConfigError, match="is not one of"):
        load_run_plan(_write(tmp_path, config))


def test_unsupported_execution_backend(tmp_path: Path) -> None:
    config = _base()
    config["execution"]["backend"] = "vllm"
    with pytest.raises(ConfigError, match="not supported"):
        load_run_plan(_write(tmp_path, config))


@pytest.mark.parametrize("bad", [0, -1, "two"])
def test_repeats_invalid(tmp_path: Path, bad: object) -> None:
    config = _base()
    config["repeats"] = bad
    with pytest.raises(ConfigError):
        load_run_plan(_write(tmp_path, config))


def test_evaluators_are_constructed_with_names(tmp_path: Path) -> None:
    config = _base()
    config["evaluators"] = [
        {"type": "exact_match"},
        {"type": "contains", "case_sensitive": False},
        {"type": "regex_match", "name": "nz", "pattern": "\\S"},
    ]
    plan = load_run_plan(_write(tmp_path, config))

    assert [e.name for e in plan.evaluators] == ["exact_match", "contains", "nz"]


def test_duplicate_evaluator_names_rejected(tmp_path: Path) -> None:
    config = _base()
    config["evaluators"] = [
        {"type": "regex_match", "name": "dup", "pattern": "a"},
        {"type": "regex_match", "name": "dup", "pattern": "b"},
    ]
    with pytest.raises(ConfigError, match="duplicate evaluator name"):
        load_run_plan(_write(tmp_path, config))


def test_unknown_evaluator_type_rejected(tmp_path: Path) -> None:
    config = _base()
    config["evaluators"] = [{"type": "bleu"}]
    with pytest.raises(ConfigError, match="is not one of"):
        load_run_plan(_write(tmp_path, config))


def test_regex_match_requires_pattern(tmp_path: Path) -> None:
    config = _base()
    config["evaluators"] = [{"type": "regex_match"}]
    with pytest.raises(ConfigError, match="missing required field 'pattern'"):
        load_run_plan(_write(tmp_path, config))


def test_malformed_regex_rejected(tmp_path: Path) -> None:
    config = _base()
    config["evaluators"] = [{"type": "regex_match", "pattern": "("}]
    with pytest.raises(ConfigError, match="invalid regex"):
        load_run_plan(_write(tmp_path, config))


def test_reference_evaluator_needs_expected_output(tmp_path: Path) -> None:
    config = _base()
    config["evaluators"] = [{"type": "exact_match"}]
    with pytest.raises(ConfigError, match="require expected_output"):
        load_run_plan(
            _write(tmp_path, config, cases=[{"input": "hi"}]),
        )


def test_release_policy_unknown_metric_rejected(tmp_path: Path) -> None:
    config = _base()
    config["release_policy"] = {"name": "p", "thresholds": {"made_up.metric": 0.1}}
    with pytest.raises(ConfigError, match="cannot produce"):
        load_run_plan(_write(tmp_path, config))


def test_valid_release_policy_is_built(tmp_path: Path) -> None:
    config = _base()
    config["evaluators"] = [{"type": "regex_match", "name": "nz", "pattern": "\\S"}]
    config["release_policy"] = {
        "name": "default",
        "thresholds": {"success_rate": 0.0, "nz.pass_rate": 0.05, "latency_ms.p95": 0.2},
        "max_safety_violations": 0,
    }
    plan = load_run_plan(_write(tmp_path, config))

    assert isinstance(plan.policy, ReleasePolicy)
    assert plan.policy.thresholds["latency_ms.p95"] == 0.2


def test_missing_dataset_path(tmp_path: Path) -> None:
    config = _base()
    del config["dataset"]["path"]
    with pytest.raises(ConfigError, match="missing required field 'path'"):
        load_run_plan(_write(tmp_path, config))


def test_dataset_file_not_found(tmp_path: Path) -> None:
    config = _base()
    config["dataset"]["path"] = "nope.jsonl"
    with pytest.raises(ConfigError, match="cannot read dataset file"):
        load_run_plan(_write(tmp_path, config))


# --- execution backends -------------------------------------------------------


def _ollama_base() -> dict[str, Any]:
    config = _base()
    config["execution"] = {"backend": "ollama"}
    config["baseline"]["provider"] = "ollama"
    config["candidate"]["provider"] = "ollama"
    for version in ("baseline", "candidate"):
        config[version].pop("parameters", None)
    return config


def test_backend_mock_injects_mock_provider_for_the_declared_identity(tmp_path: Path) -> None:
    config = _base()
    config["baseline"]["provider"] = "ollama"
    config["candidate"]["provider"] = "ollama"
    plan = load_run_plan(_write(tmp_path, config))

    assert set(plan.providers) == {ProviderName.OLLAMA}
    assert isinstance(plan.providers[ProviderName.OLLAMA], MockProvider)


def test_backend_ollama_builds_an_ollama_provider_with_defaults(tmp_path: Path) -> None:
    plan = load_run_plan(_write(tmp_path, _ollama_base()))

    provider = plan.providers[ProviderName.OLLAMA]
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == DEFAULT_BASE_URL
    assert provider.timeout_seconds == 120.0


def test_backend_ollama_reads_explicit_connection_settings(tmp_path: Path) -> None:
    config = _ollama_base()
    config["execution"] = {
        "backend": "ollama",
        "base_url": "http://ollama.local:1234/",
        "timeout_seconds": 30,
    }
    plan = load_run_plan(_write(tmp_path, config))

    provider = plan.providers[ProviderName.OLLAMA]
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://ollama.local:1234"  # trailing slash normalized
    assert provider.timeout_seconds == 30.0


def test_backend_ollama_rejects_non_ollama_provider(tmp_path: Path) -> None:
    config = _ollama_base()
    config["baseline"]["provider"] = "openai"
    with pytest.raises(ConfigError, match="must be 'ollama'"):
        load_run_plan(_write(tmp_path, config))


def test_backend_ollama_rejects_unsupported_generation_parameter(tmp_path: Path) -> None:
    config = _ollama_base()
    config["candidate"]["parameters"] = {"frequency_penalty": 0.5}
    with pytest.raises(ConfigError, match="not a supported Ollama generation parameter"):
        load_run_plan(_write(tmp_path, config))


def test_unknown_backend_is_rejected(tmp_path: Path) -> None:
    config = _base()
    config["execution"] = {"backend": "cohere"}
    with pytest.raises(ConfigError, match="is not supported"):
        load_run_plan(_write(tmp_path, config))


def test_backend_openai_builds_a_hosted_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    config = _base()
    config["execution"] = {"backend": "openai"}
    for version in ("baseline", "candidate"):
        config[version]["provider"] = "openai"
        config[version]["parameters"] = {"temperature": 0.0}

    plan = load_run_plan(_write(tmp_path, config))

    assert set(plan.providers) == {ProviderName.OPENAI}
    assert isinstance(plan.providers[ProviderName.OPENAI], OpenAIProvider)


def test_backend_openai_without_a_key_fails_fast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = _base()
    config["execution"] = {"backend": "openai"}
    for version in ("baseline", "candidate"):
        config[version]["provider"] = "openai"
        config[version].pop("parameters", None)
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_run_plan(_write(tmp_path, config))


def test_backend_live_supports_a_mixed_provider_experiment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    config = _base()
    config["execution"] = {"backend": "live"}
    config["baseline"]["provider"] = "ollama"
    config["baseline"]["model"] = "llama3.2"
    config["baseline"].pop("parameters", None)
    config["candidate"]["provider"] = "openai"
    config["candidate"]["model"] = "gpt-4o-mini"
    config["candidate"]["parameters"] = {"temperature": 0.0}

    plan = load_run_plan(_write(tmp_path, config))

    assert set(plan.providers) == {ProviderName.OLLAMA, ProviderName.OPENAI}
    assert isinstance(plan.providers[ProviderName.OLLAMA], OllamaProvider)
    assert isinstance(plan.providers[ProviderName.OPENAI], OpenAIProvider)
    assert plan.baseline.provider is ProviderName.OLLAMA
    assert plan.candidate.provider is ProviderName.OPENAI


def test_llm_judge_evaluator_parses_from_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    config = _base()
    config["evaluators"] = [
        {"type": "regex_match", "pattern": "."},
        {
            "type": "llm_judge",
            "name": "correctness",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.0,
        },
    ]
    plan = load_run_plan(_write(tmp_path, config))

    assert [e.name for e in plan.evaluators] == ["regex_match", "correctness"]
    judge = plan.evaluators[1]
    assert isinstance(judge, LLMJudge)
    assert judge.provider_name is ProviderName.OPENAI and judge.model == "gpt-4o-mini"


def test_backend_ollama_rejects_non_positive_timeout(tmp_path: Path) -> None:
    config = _ollama_base()
    config["execution"] = {"backend": "ollama", "timeout_seconds": 0}
    with pytest.raises(ConfigError, match="greater than 0"):
        load_run_plan(_write(tmp_path, config))
