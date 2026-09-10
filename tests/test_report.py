"""Tests for evalops.report (build_report, human_report, json_report)."""

from __future__ import annotations

import json
import re

from evalops.domain.enums import ReleaseDecision
from evalops.report import MetricLine, RunReport, human_report, json_report


def _line(
    metric: str,
    *,
    baseline: float,
    candidate: float,
    direction: str = "higher_is_better",
    threshold: float | None = None,
    adverse: float | None = 0.0,
    regression: bool = False,
    relative_delta: float | None = 0.0,
) -> MetricLine:
    return MetricLine(
        metric=metric,
        baseline_value=baseline,
        candidate_value=candidate,
        delta=candidate - baseline,
        relative_delta=relative_delta,
        direction=direction,
        threshold=threshold,
        adverse_change=adverse,
        regression=regression,
    )


def _report(
    *lines: MetricLine, decision: ReleaseDecision, reasons: tuple[str, ...] = ()
) -> RunReport:
    return RunReport(
        dataset_name="support",
        baseline_name="p",
        baseline_version="v1",
        candidate_name="p",
        candidate_version="v2",
        repeats=1,
        case_count=4,
        run_count=8,
        failure_count=0,
        metrics=lines,
        gated=decision is not ReleaseDecision.PASS or bool(reasons),
        decision=decision,
        reasons=reasons,
    )


def test_human_report_pass() -> None:
    text = human_report(
        _report(
            _line("success_rate", baseline=1.0, candidate=1.0, threshold=0.0),
            decision=ReleaseDecision.PASS,
        )
    )

    assert "EvalOps Evaluation" in text
    assert "Release decision: PASS" in text
    assert "Reasons:" not in text


def test_human_report_block_includes_reason() -> None:
    reason = "latency_ms.p95: lower-is-better regression of 50.0% (limit 20%)"
    text = human_report(
        _report(
            _line(
                "latency_ms.p95",
                baseline=40.0,
                candidate=60.0,
                direction="lower_is_better",
                threshold=0.20,
                adverse=0.5,
                regression=True,
                relative_delta=0.5,
            ),
            decision=ReleaseDecision.BLOCK,
            reasons=(reason,),
        )
    )

    assert "Release decision: BLOCK" in text
    assert "Reasons:" in text
    assert reason in text


def test_human_report_shows_na_for_zero_baseline() -> None:
    text = human_report(
        _report(
            _line(
                "cost_usd.total", baseline=0.0, candidate=0.0, threshold=0.1, relative_delta=None
            ),
            decision=ReleaseDecision.PASS,
        )
    )

    assert "n/a" in text


def test_human_report_marks_ungated_metric_with_a_dash() -> None:
    text = human_report(
        _report(
            _line("latency_ms.mean", baseline=40.0, candidate=60.0, direction="lower_is_better"),
            decision=ReleaseDecision.PASS,
        )
    )
    row = next(line for line in text.splitlines() if line.startswith("latency_ms.mean"))

    assert row.rstrip().endswith("-")  # STATUS column is '-' when not gated


def test_human_report_does_not_call_an_adverse_change_an_improvement() -> None:
    text = human_report(
        _report(
            _line(
                "latency_ms.p95",
                baseline=40.0,
                candidate=60.0,
                direction="lower_is_better",
                threshold=0.20,
                adverse=0.5,
                regression=True,
                relative_delta=0.5,
            ),
            decision=ReleaseDecision.BLOCK,
            reasons=("latency_ms.p95 regressed",),
        )
    )

    assert "improvement" not in text.lower()
    assert "+50.0%" in text


def test_json_report_shape() -> None:
    payload = json.loads(
        json_report(
            _report(
                _line("success_rate", baseline=1.0, candidate=1.0, threshold=0.0),
                decision=ReleaseDecision.PASS,
            )
        )
    )

    assert payload["schema_version"] == 2
    assert set(payload) == {
        "schema_version",
        "dataset",
        "baseline",
        "candidate",
        "repeats",
        "counts",
        "metrics",
        "gated",
        "decision",
        "reasons",
        "advisories",
    }
    assert payload["decision"] == "pass"
    assert payload["advisories"] == []
    assert set(payload["metrics"][0]) == {
        "metric",
        "baseline_value",
        "candidate_value",
        "delta",
        "relative_delta",
        "direction",
        "threshold",
        "adverse_change",
        "regression",
        "gate_outcome",
    }


def test_json_report_metric_order_is_stable() -> None:
    report = _report(
        _line("success_rate", baseline=1.0, candidate=1.0),
        _line("exact_match.pass_rate", baseline=1.0, candidate=1.0),
        _line("latency_ms.p95", baseline=1.0, candidate=1.0, direction="lower_is_better"),
        decision=ReleaseDecision.PASS,
    )
    payload = json.loads(json_report(report))

    assert [m["metric"] for m in payload["metrics"]] == [
        "success_rate",
        "exact_match.pass_rate",
        "latency_ms.p95",
    ]


def test_json_report_excludes_ids_and_timestamps() -> None:
    payload = json_report(
        _report(
            _line("success_rate", baseline=1.0, candidate=1.0, threshold=0.0),
            decision=ReleaseDecision.PASS,
        )
    )

    assert re.search(r"[0-9a-f]{32}", payload) is None
    assert "created_at" not in payload
    assert '"id"' not in payload


def test_json_report_is_deterministic() -> None:
    def make() -> RunReport:
        return _report(
            _line("success_rate", baseline=1.0, candidate=0.5, threshold=0.0, regression=True),
            decision=ReleaseDecision.BLOCK,
            reasons=("success_rate regressed",),
        )

    assert json_report(make()) == json_report(make())
