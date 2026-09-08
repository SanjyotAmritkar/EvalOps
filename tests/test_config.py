"""Tests for evalops.config.load_run_plan."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from evalops.config import load_run_plan
from evalops.domain.entities import ReleasePolicy
from evalops.domain.enums import ProviderName
from evalops.errors import ConfigError
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
    config["execution"]["backend"] = "ollama"
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
