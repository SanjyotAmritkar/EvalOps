"""Tests for evalops.cli.main (offline)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from evalops.cli import main


def _mock(
    responses: dict[str, str], *, latency: float, fail_on: list[str] | None = None
) -> dict[str, Any]:
    block: dict[str, Any] = {"responses": responses, "default": "", "latency_ms": latency}
    if fail_on is not None:
        block["fail_on"] = fail_on
    return {"mock": block}


def _write_config(
    tmp_path: Path,
    *,
    baseline_latency: float,
    candidate_latency: float,
    fail_on: list[str] | None = None,
    policy: dict[str, Any] | None = None,
) -> Path:
    cases = [
        {"input": "one", "expected_output": "1", "id": "c1"},
        {"input": "two", "expected_output": "2", "id": "c2"},
    ]
    (tmp_path / "cases.jsonl").write_text(
        "\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8"
    )
    responses = {"Q: one": "1", "Q: two": "2"}
    config: dict[str, Any] = {
        "project": "T",
        "dataset": {"path": "cases.jsonl", "name": "t"},
        "repeats": 1,
        "execution": {"backend": "mock"},
        "baseline": {
            "name": "p",
            "version": "v1",
            "provider": "openai",
            "model": "m",
            "prompt_template": "Q: ${input}",
            "parameters": _mock(responses, latency=baseline_latency),
        },
        "candidate": {
            "name": "p",
            "version": "v2",
            "provider": "openai",
            "model": "m",
            "prompt_template": "Q: ${input}",
            "parameters": _mock(responses, latency=candidate_latency, fail_on=fail_on),
        },
        "evaluators": [{"type": "exact_match"}],
    }
    if policy is not None:
        config["release_policy"] = policy
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_regression_config_exits_1(tmp_path: Path) -> None:
    cfg = _write_config(
        tmp_path,
        baseline_latency=40,
        candidate_latency=80,
        policy={"name": "p", "thresholds": {"latency_ms.p95": 0.20}},
    )

    assert main(["run", str(cfg)]) == 1


def test_passing_config_exits_0(tmp_path: Path) -> None:
    cfg = _write_config(
        tmp_path,
        baseline_latency=40,
        candidate_latency=44,
        policy={"name": "p", "thresholds": {"latency_ms.p95": 0.20}},
    )

    assert main(["run", str(cfg)]) == 0


def test_invalid_config_exits_2_and_writes_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [1, 2\n", encoding="utf-8")

    rc = main(["run", str(bad)])
    captured = capsys.readouterr()

    assert rc == 2
    assert captured.out == ""
    assert captured.err.startswith("error:")


def test_human_report_goes_to_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = _write_config(tmp_path, baseline_latency=40, candidate_latency=44)

    rc = main(["run", str(cfg)])
    captured = capsys.readouterr()

    assert rc == 0
    assert "EvalOps Evaluation" in captured.out
    assert "Release decision: PASS" in captured.out
    assert captured.err == ""


def test_json_file_is_written(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, baseline_latency=40, candidate_latency=44)
    out = tmp_path / "result.json"

    rc = main(["run", str(cfg), "--json", str(out)])

    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["decision"] == "pass"


def test_json_dash_quiet_writes_only_json_to_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _write_config(tmp_path, baseline_latency=40, candidate_latency=44)

    main(["run", str(cfg), "--json", "-", "--quiet"])
    captured = capsys.readouterr()

    assert "EvalOps Evaluation" not in captured.out
    assert json.loads(captured.out)["decision"] == "pass"


def test_json_dash_without_quiet_suppresses_human_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _write_config(tmp_path, baseline_latency=40, candidate_latency=44)

    main(["run", str(cfg), "--json", "-"])
    captured = capsys.readouterr()

    assert "EvalOps Evaluation" not in captured.out
    assert json.loads(captured.out)["schema_version"] == 1


def test_individual_provider_error_is_not_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Candidate fails one case; success_rate drops to 0.5 and the policy blocks.
    cfg = _write_config(
        tmp_path,
        baseline_latency=40,
        candidate_latency=40,
        fail_on=["Q: two"],
        policy={"name": "p", "thresholds": {"success_rate": 0.0}},
    )

    rc = main(["run", str(cfg)])
    captured = capsys.readouterr()

    assert rc == 1  # a release decision, not a system error
    assert "error:" not in captured.err
    assert "Failures: 1" in captured.out


def test_missing_subcommand_is_exit_2() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_missing_config_argument_is_exit_2() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["run"])
    assert exc.value.code == 2
