"""CP 7.1: the CLI release gate uses the same statistically-aware semantics as
the persisted/API path.

Offline, deterministic (fixed bootstrap seed). Exit codes: 0 = PASS (incl. PASS
with advisories), 1 = BLOCK, 2 = execution/config error.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from evalops.cli import main
from evalops.config import load_run_plan
from evalops.domain.enums import ReleaseDecision
from evalops.execution import run_evaluation


def _write(
    tmp_path: Path,
    *,
    cases: int,
    repeats: int = 1,
    fail_indices: tuple[int, ...] = (),
    thresholds: dict[str, float],
    baseline_latency: float = 40.0,
    candidate_latency: float = 40.0,
    provider: str = "openai",
) -> Path:
    rows = [{"input": f"case-{i}", "expected_output": "ok", "id": f"c{i}"} for i in range(cases)]
    (tmp_path / "cases.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    responses = {f"Q: case-{i}": "ok" for i in range(cases)}
    fail_on = [f"Q: case-{i}" for i in fail_indices]
    config: dict[str, Any] = {
        "project": "T",
        "dataset": {"path": "cases.jsonl", "name": "t"},
        "repeats": repeats,
        "execution": {"backend": "mock"},
        "baseline": {
            "name": "sys",
            "version": "v1",
            "provider": provider,
            "model": "m",
            "prompt_template": "Q: ${input}",
            "parameters": {
                "mock": {"responses": responses, "default": "", "latency_ms": baseline_latency}
            },
        },
        "candidate": {
            "name": "sys",
            "version": "v2",
            "provider": provider,
            "model": "m",
            "prompt_template": "Q: ${input}",
            "parameters": {
                "mock": {
                    "responses": responses,
                    "default": "",
                    "latency_ms": candidate_latency,
                    "fail_on": fail_on,
                }
            },
        },
        "evaluators": [{"type": "contains"}],
        "release_policy": {"name": "p", "thresholds": thresholds},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def _json_run(cfg: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, Any]]:
    rc = main(["run", str(cfg), "--json", "-", "--quiet"])
    return rc, json.loads(capsys.readouterr().out)


# --- the four statistical outcomes at the CLI -------------------------


def test_statistically_confirmed_regression_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 8 comparable pairs, candidate fails every case -> success_rate 1.0 -> 0.0,
    # CI [-1, -1] is entirely past the 0% boundary -> a real BLOCK.
    cfg = _write(
        tmp_path,
        cases=8,
        fail_indices=tuple(range(8)),
        thresholds={"success_rate": 0.0},
    )
    rc, payload = _json_run(cfg, capsys)

    assert rc == 1
    assert payload["decision"] == "block"
    assert any("success_rate" in r for r in payload["reasons"])
    assert payload["advisories"] == []
    sr = next(m for m in payload["metrics"] if m["metric"] == "success_rate")
    assert sr["gate_outcome"] == "regression" and sr["regression"] is True


def test_threshold_breach_with_insufficient_evidence_exits_0_with_advisory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # only 2 pairs -> below MIN_PAIRS_TO_BLOCK -> advisory, PASS.
    cfg = _write(tmp_path, cases=2, fail_indices=(0, 1), thresholds={"success_rate": 0.0})
    rc, payload = _json_run(cfg, capsys)

    assert rc == 0
    assert payload["decision"] == "pass"
    assert payload["reasons"] == []
    assert any(
        "success_rate" in a and "insufficient evidence to block" in a for a in payload["advisories"]
    )
    sr = next(m for m in payload["metrics"] if m["metric"] == "success_rate")
    assert sr["gate_outcome"] == "regression_low_evidence" and sr["regression"] is False


def test_threshold_breach_with_inconclusive_evidence_exits_0_with_advisory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 8 pairs, 2 failures, 10% tolerance: point drop 25% breaches, but the 95%
    # CI does not clear the tolerated boundary -> inconclusive -> PASS + advisory.
    cfg = _write(tmp_path, cases=8, fail_indices=(0, 1), thresholds={"success_rate": 0.10})
    rc, payload = _json_run(cfg, capsys)

    assert rc == 0
    assert payload["decision"] == "pass"
    assert payload["reasons"] == []
    assert any("does not confirm a regression" in a for a in payload["advisories"])
    sr = next(m for m in payload["metrics"] if m["metric"] == "success_rate")
    assert sr["gate_outcome"] == "regression_inconclusive"


def test_clean_pass_exits_0_with_no_advisory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _write(tmp_path, cases=4, thresholds={"success_rate": 0.5})
    rc, payload = _json_run(cfg, capsys)

    assert rc == 0
    assert payload["decision"] == "pass"
    assert payload["reasons"] == [] and payload["advisories"] == []
    assert all(m["gate_outcome"] == "pass" for m in payload["metrics"])


def test_deterministic_only_metric_regression_still_blocks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # latency_ms.p95 has no paired-bootstrap evidence -> a threshold breach
    # BLOCKs exactly as before Phase 5.
    cfg = _write(
        tmp_path,
        cases=2,
        baseline_latency=40,
        candidate_latency=80,
        thresholds={"latency_ms.p95": 0.20},
    )
    rc, payload = _json_run(cfg, capsys)

    assert rc == 1
    assert any("latency_ms.p95" in r for r in payload["reasons"])
    p95 = next(m for m in payload["metrics"] if m["metric"] == "latency_ms.p95")
    assert p95["gate_outcome"] == "regression"


# --- CLI output surfaces PASS/BLOCK + advisories --------------------


def test_human_report_shows_advisory_section_on_a_weak_breach(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _write(tmp_path, cases=8, fail_indices=(0, 1), thresholds={"success_rate": 0.10})
    rc = main(["run", str(cfg)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Release decision: PASS" in out
    assert "Advisories" in out
    assert "still a PASS" in out
    # the per-metric STATUS column flags the inconclusive breach
    status_row = next(line for line in out.splitlines() if line.startswith("success_rate"))
    assert "ADVISORY" in status_row


# --- CLI == backend gate for equivalent data -----------------------


@pytest.mark.parametrize(
    ("cases", "fail_indices", "thresholds"),
    [
        (8, tuple(range(8)), {"success_rate": 0.0}),  # confirmed -> block
        (2, (0, 1), {"success_rate": 0.0}),  # insufficient -> pass
        (8, (0, 1), {"success_rate": 0.10}),  # inconclusive -> pass
        (4, (), {"success_rate": 0.5}),  # clean pass
    ],
)
def test_cli_gate_matches_run_evaluation_for_equivalent_data(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    cases: int,
    fail_indices: tuple[int, ...],
    thresholds: dict[str, float],
) -> None:
    cfg = _write(tmp_path, cases=cases, fail_indices=fail_indices, thresholds=thresholds)

    plan = load_run_plan(cfg)
    authoritative = run_evaluation(
        plan.experiment,
        plan.dataset,
        plan.baseline,
        plan.candidate,
        plan.policy,
        evaluators=plan.evaluators,
        providers=plan.providers,
    ).gate

    rc, payload = _json_run(cfg, capsys)

    assert rc == (1 if authoritative.decision is ReleaseDecision.BLOCK else 0)
    assert payload["decision"] == authoritative.decision.value
    assert payload["reasons"] == list(authoritative.reasons)
    assert payload["advisories"] == list(authoritative.advisories)
    outcomes = {m["metric"]: m["gate_outcome"] for m in payload["metrics"]}
    assert outcomes == {v.metric: v.outcome for v in authoritative.verdicts}


# --- CI safety ---------------------------------------------------


def test_hosted_backend_without_a_key_exits_2_not_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = _write(tmp_path, cases=2, thresholds={"success_rate": 0.0})
    # force the real hosted backend rather than mock
    config = yaml.safe_load(cfg.read_text())
    config["execution"] = {"backend": "openai"}
    cfg.write_text(yaml.safe_dump(config))

    rc = main(["run", str(cfg)])
    captured = capsys.readouterr()

    assert rc == 2  # config/provider error, never a release BLOCK
    assert captured.out == ""
    assert captured.err.startswith("error:")
    assert "OPENAI_API_KEY" in captured.err  # the name, never a value
    assert "sk-" not in captured.err
