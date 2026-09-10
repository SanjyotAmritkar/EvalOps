"""Tests for evalops.ci -- the GitHub Step Summary renderer for `evalops run`.

The renderer is CI glue: it must format the CLI's schema-v2 JSON, never
re-derive a decision, keep PASS-with-advisories a PASS, keep BLOCK and ERROR
distinct, and tolerate a missing / malformed report. It also plumbs the CLI
exit code straight through so the workflow step's status is the gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from evalops.ci import load_report, main, render_pr_summary

_WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release-gate.yml"


def _metric(
    name: str,
    *,
    baseline: float = 1.0,
    candidate: float = 1.0,
    delta: float = 0.0,
    threshold: float | None = None,
    regression: bool = False,
    gate_outcome: str = "pass",
) -> dict[str, Any]:
    return {
        "metric": name,
        "baseline_value": baseline,
        "candidate_value": candidate,
        "delta": delta,
        "relative_delta": None if baseline == 0 else delta / baseline,
        "direction": "higher_is_better",
        "threshold": threshold,
        "adverse_change": 0.0,
        "regression": regression,
        "gate_outcome": gate_outcome,
    }


def _report(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": 2,
        "dataset": {"name": "support", "cases": 4},
        "baseline": {"name": "support-prompt", "version": "v1"},
        "candidate": {"name": "support-prompt", "version": "v2"},
        "repeats": 1,
        "counts": {"cases": 4, "runs": 8, "failures": 0},
        "metrics": [_metric("success_rate", threshold=0.0)],
        "gated": True,
        "decision": "pass",
        "reasons": [],
        "advisories": [],
    }
    base.update(overrides)
    return base


# --- PASS ------------------------------------------------------------


def test_clean_pass_summary() -> None:
    summary = render_pr_summary(_report(), 0, config="examples/support/fixed.yaml")

    assert summary.startswith("## ✅ EvalOps release gate: PASS")
    assert "BLOCK" not in summary
    assert "ERROR" not in summary
    assert "Advisories" not in summary
    assert "config `examples/support/fixed.yaml`" in summary
    assert "candidate **support-prompt v2** vs baseline **support-prompt v1**" in summary
    assert "| `success_rate` |" in summary
    assert "| pass |" in summary


# --- PASS with advisories -----------------------------------------


_ADVISORY = (
    "success_rate: observed higher-is-better regression of 25.0% exceeds the 10% "
    "limit, but the 95% CI [-0.625, 0] does not confirm a regression beyond the "
    "tolerated boundary -- not blocking"
)


def test_pass_with_advisories_is_still_a_pass() -> None:
    report = _report(
        advisories=[_ADVISORY],
        metrics=[
            _metric(
                "success_rate",
                baseline=1.0,
                candidate=0.75,
                delta=-0.25,
                threshold=0.10,
                regression=False,
                gate_outcome="regression_inconclusive",
            )
        ],
    )
    summary = render_pr_summary(report, 0)

    assert summary.startswith("## ✅ EvalOps release gate: PASS")
    assert "BLOCK" not in summary
    assert "Passed with advisories" in summary
    assert "still a PASS" in summary
    assert "### Advisories" in summary
    assert _ADVISORY in summary
    # the metric row flags the inconclusive breach, but it is not a blocker
    assert "| breach (inconclusive) |" in summary
    assert "**regression**" not in summary


# --- BLOCK ---------------------------------------------------------


def test_block_summary_distinct_from_pass_and_error() -> None:
    report = _report(
        decision="block",
        reasons=["latency_ms.p95: lower-is-better regression of 50.0% (limit 20%)"],
        metrics=[
            _metric("success_rate", threshold=0.0),
            _metric(
                "latency_ms.p95",
                baseline=40.0,
                candidate=60.0,
                delta=20.0,
                threshold=0.20,
                regression=True,
                gate_outcome="regression",
            ),
        ],
    )
    summary = render_pr_summary(report, 1)

    assert summary.startswith("## 🚫 EvalOps release gate: BLOCK")
    assert "PASS" not in summary
    assert "ERROR" not in summary
    assert "### Blocking reasons" in summary
    assert "latency_ms.p95: lower-is-better regression of 50.0% (limit 20%)" in summary
    assert "| `latency_ms.p95` |" in summary
    assert "| **regression** |" in summary
    assert "| +20 |" in summary  # delta rendered


def test_block_with_advisories_shows_both_sections() -> None:
    report = _report(
        decision="block",
        reasons=["latency_ms.p95: ..."],
        advisories=[_ADVISORY],
    )
    summary = render_pr_summary(report, 1)
    assert "### Blocking reasons" in summary
    assert "### Advisories" in summary


# --- ERROR (exit 2) ----------------------------------------------


def test_error_summary_has_no_release_decision_and_keeps_diagnostics() -> None:
    log = "error: release_policy.thresholds names metric(s) this run cannot produce: ['bogus']"
    summary = render_pr_summary(None, 2, log=log, config="examples/support/fixed.yaml")

    assert summary.startswith("## ⚠️ EvalOps release gate: ERROR")
    assert "No release decision was produced" in summary
    assert "not a release BLOCK" in summary
    # the CLI's own (secret-free) error text is preserved for the reviewer
    assert log in summary
    assert "<details><summary>Diagnostic output</summary>" in summary
    # never render a PASS/BLOCK heading for an error
    assert "release gate: PASS" not in summary
    assert "release gate: BLOCK" not in summary


def test_error_summary_truncates_long_diagnostics() -> None:
    summary = render_pr_summary(None, 2, log="x" * 10_000)
    assert "…(truncated)…" in summary
    assert len(summary) < 6000


def test_unknown_nonzero_exit_code_renders_error() -> None:
    assert render_pr_summary(None, 7, log="").startswith("## ⚠️ EvalOps release gate: ERROR")


# --- malformed / incomplete reports ----------------------------


def test_missing_report_on_pass_still_renders() -> None:
    summary = render_pr_summary(None, 0)
    assert summary.startswith("## ✅ EvalOps release gate: PASS")
    assert "no JSON report was found" in summary


def test_incomplete_report_dict_does_not_crash() -> None:
    summary = render_pr_summary({"schema_version": 2}, 1)
    assert summary.startswith("## 🚫 EvalOps release gate: BLOCK")
    assert "(no reasons recorded in the report)" in summary


def test_report_with_non_dict_metrics_is_skipped_safely() -> None:
    summary = render_pr_summary(_report(metrics=["not-a-dict", 5]), 0)
    assert summary.startswith("## ✅ EvalOps release gate: PASS")
    assert "| Metric | Baseline" not in summary  # no rows -> no table header


def test_load_report_tolerates_missing_and_bad_json(tmp_path: Path) -> None:
    assert load_report(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_report(bad) is None
    arr = tmp_path / "arr.json"
    arr.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_report(arr) is None
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps(_report()), encoding="utf-8")
    assert load_report(ok) == _report()


# --- main(): exit code + $GITHUB_STEP_SUMMARY -----------------


def test_main_returns_the_exit_code_verbatim(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    report = tmp_path / "r.json"
    report.write_text(json.dumps(_report(decision="block", reasons=["x"])), encoding="utf-8")

    assert main(["--exit-code", "0", "--report", str(report)]) == 0
    assert main(["--exit-code", "1", "--report", str(report)]) == 1
    assert main(["--exit-code", "2", "--report", str(report)]) == 2
    # nothing but the summary is printed
    assert "EvalOps release gate" in capsys.readouterr().out


def test_main_appends_to_github_step_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "r.json"
    report.write_text(json.dumps(_report()), encoding="utf-8")
    step_summary = tmp_path / "step-summary.md"
    step_summary.write_text("pre-existing\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary))

    rc = main(
        ["--exit-code", "0", "--report", str(report), "--config", "examples/support/fixed.yaml"]
    )

    assert rc == 0
    written = step_summary.read_text(encoding="utf-8")
    assert written.startswith("pre-existing\n")  # appended, not overwritten
    assert "## ✅ EvalOps release gate: PASS" in written


def test_main_includes_diagnostic_log_only_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "run.log"
    log.write_text("error: something broke\n", encoding="utf-8")
    step = tmp_path / "s.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step))
    # no report file exists -> exit 2 path
    main(["--exit-code", "2", "--report", str(tmp_path / "missing.json"), "--log", str(log)])
    assert "error: something broke" in step.read_text(encoding="utf-8")

    step.write_text("", encoding="utf-8")
    main(["--exit-code", "0", "--report", str(tmp_path / "missing.json"), "--log", str(log)])
    assert "error: something broke" not in step.read_text(encoding="utf-8")


# --- workflow YAML: structural checks (pyyaml is already a dep) ---


def _workflow() -> dict[Any, Any]:
    parsed: Any = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def test_workflow_triggers_on_pull_request_and_dispatch() -> None:
    wf = _workflow()
    # PyYAML 1.1 parses the `on:` key as the boolean True.
    triggers = wf.get(True, wf.get("on"))
    assert isinstance(triggers, dict)
    assert "pull_request" in triggers
    assert "workflow_dispatch" in triggers


def test_workflow_is_pinned_offline_and_uv_based() -> None:
    wf = _workflow()
    assert wf["permissions"]["contents"] == "read"
    job = wf["jobs"]["release-gate"]
    assert job["runs-on"] == "ubuntu-latest"
    steps = job["steps"]
    uses = [s.get("uses", "") for s in steps]
    assert any(u.startswith("astral-sh/setup-uv@") for u in uses)
    assert any(u.startswith("actions/upload-artifact@") for u in uses)

    setup = next(s for s in steps if str(s.get("uses", "")).startswith("astral-sh/setup-uv@"))
    assert setup["with"]["python-version"] == "3.11"

    run_scripts = "\n".join(s.get("run", "") for s in steps)
    assert "uv sync --locked" in run_scripts
    assert "evalops run" in run_scripts and "--json" in run_scripts
    assert "python -m evalops.ci" in run_scripts
    assert "--exit-code" in run_scripts
    # no hosted-provider secrets referenced anywhere
    assert "OPENAI_API_KEY" not in _WORKFLOW.read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" not in _WORKFLOW.read_text(encoding="utf-8")


def test_workflow_run_step_never_fails_the_job_itself() -> None:
    steps = _workflow()["jobs"]["release-gate"]["steps"]
    gate = next(s for s in steps if s.get("id") == "gate")
    assert "set +e" in gate["run"]
    assert "exit 0" in gate["run"]
    assert 'echo "exit_code=$code"' in gate["run"]
    # the artifact upload and the enforcing summary both run unconditionally
    for name in ("Upload evaluation report", "Render PR summary and enforce gate"):
        step = next(s for s in steps if s.get("name") == name)
        assert step.get("if") == "always()"
