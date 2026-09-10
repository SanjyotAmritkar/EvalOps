"""Build and render an evaluation report.

An explicit output representation (``RunReport``) is assembled from the plan,
the runner outcome, the aggregated result, and the gate report -- domain
objects are never serialized directly. Two renderers: a compact human report
and a stable machine-readable JSON string (no UUIDs, timestamps, or reprs;
byte-identical for a deterministic config).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from evalops.config import RunPlan
from evalops.domain.entities import EvaluationResult
from evalops.domain.enums import ReleaseDecision
from evalops.gate import GateReport
from evalops.runner import RunOutcome

#: Bumped to 2 in CP 7.1: the CLI now uses the same statistically-aware gate as
#: the API, so each metric line carries a ``gate_outcome`` and the report a
#: top-level ``advisories`` list.
SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class MetricLine:
    metric: str
    baseline_value: float
    candidate_value: float
    delta: float
    relative_delta: float | None
    direction: str
    threshold: float | None
    adverse_change: float | None
    regression: bool  # drives BLOCK; True iff gate_outcome == "regression"
    #: CP 7.1: "pass" | "regression" | "regression_inconclusive" |
    #: "regression_low_evidence" -- the same per-metric outcome the API returns.
    gate_outcome: str = "pass"


@dataclass(frozen=True, slots=True)
class RunReport:
    dataset_name: str
    baseline_name: str
    baseline_version: str
    candidate_name: str
    candidate_version: str
    repeats: int
    case_count: int
    run_count: int
    failure_count: int
    metrics: tuple[MetricLine, ...]
    gated: bool
    decision: ReleaseDecision
    reasons: tuple[str, ...]
    #: CP 7.1: threshold breaches the statistical guard did not block. A run
    #: with advisories still PASSes (exit 0).
    advisories: tuple[str, ...] = ()


def build_report(
    plan: RunPlan,
    outcome: RunOutcome,
    result: EvaluationResult,
    gate: GateReport,
) -> RunReport:
    verdicts = {v.metric: v for v in gate.verdicts}
    lines = tuple(
        MetricLine(
            metric=mc.metric,
            baseline_value=mc.baseline_value,
            candidate_value=mc.candidate_value,
            delta=mc.delta,
            relative_delta=mc.relative_delta,
            direction=verdicts[mc.metric].direction,
            threshold=verdicts[mc.metric].threshold,
            adverse_change=verdicts[mc.metric].adverse_change,
            regression=verdicts[mc.metric].regression,
            gate_outcome=verdicts[mc.metric].outcome,
        )
        for mc in result.metrics
    )
    return RunReport(
        dataset_name=plan.dataset.name,
        baseline_name=plan.baseline.name,
        baseline_version=plan.baseline.version,
        candidate_name=plan.candidate.name,
        candidate_version=plan.candidate.version,
        repeats=plan.experiment.repeats,
        case_count=len(plan.dataset.cases),
        run_count=len(outcome.runs),
        failure_count=sum(1 for run in outcome.runs if run.error is not None),
        metrics=lines,
        gated=gate.gated,
        decision=gate.decision,
        reasons=gate.reasons,
        advisories=gate.advisories,
    )


def human_report(report: RunReport) -> str:
    lines = [
        "EvalOps Evaluation",
        f"Dataset: {report.dataset_name}",
        f"Baseline: {report.baseline_name} {report.baseline_version}  |  "
        f"Candidate: {report.candidate_name} {report.candidate_version}",
        f"Cases: {report.case_count} | Repeats: {report.repeats} | "
        f"Runs: {report.run_count} | Failures: {report.failure_count}",
        "",
    ]

    name_width = max((len(m.metric) for m in report.metrics), default=6)
    name_width = max(name_width, len("METRIC"))
    header = (
        f"{'METRIC':<{name_width}}  {'BASELINE':>10}  {'CANDIDATE':>10}  "
        f"{'CHANGE':>9}  {'THRESHOLD':>9}  STATUS"
    )
    lines.append(header)
    for m in report.metrics:
        lines.append(
            f"{m.metric:<{name_width}}  {m.baseline_value:>10.3f}  {m.candidate_value:>10.3f}  "
            f"{_change(m):>9}  {_threshold(m):>9}  {_status(m)}"
        )

    lines += ["", f"Release decision: {report.decision.value.upper()}"]
    if report.reasons:
        lines.append("")
        lines.append("Reasons:")
        lines += [f"- {reason}" for reason in report.reasons]
    if report.advisories:
        lines.append("")
        lines.append(
            "Advisories (threshold breached, but the evidence is too weak to block "
            "-- this is still a PASS):"
        )
        lines += [f"- {advisory}" for advisory in report.advisories]
    return "\n".join(lines) + "\n"


def json_report(report: RunReport) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "dataset": {"name": report.dataset_name, "cases": report.case_count},
        "baseline": {"name": report.baseline_name, "version": report.baseline_version},
        "candidate": {"name": report.candidate_name, "version": report.candidate_version},
        "repeats": report.repeats,
        "counts": {
            "cases": report.case_count,
            "runs": report.run_count,
            "failures": report.failure_count,
        },
        "metrics": [
            {
                "metric": m.metric,
                "baseline_value": m.baseline_value,
                "candidate_value": m.candidate_value,
                "delta": m.delta,
                "relative_delta": m.relative_delta,
                "direction": m.direction,
                "threshold": m.threshold,
                "adverse_change": m.adverse_change,
                "regression": m.regression,
                "gate_outcome": m.gate_outcome,
            }
            for m in report.metrics
        ],
        "gated": report.gated,
        "decision": report.decision.value,
        "reasons": list(report.reasons),
        "advisories": list(report.advisories),
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def _change(line: MetricLine) -> str:
    if line.relative_delta is None:
        return "n/a"
    if line.relative_delta == 0:
        return "0.0%"
    return f"{line.relative_delta:+.1%}"


def _threshold(line: MetricLine) -> str:
    return "-" if line.threshold is None else f"{line.threshold:.1%}"


def _status(line: MetricLine) -> str:
    if line.threshold is None:
        return "-"
    if line.regression or line.gate_outcome == "regression":
        return "BLOCK"
    if line.gate_outcome in ("regression_inconclusive", "regression_low_evidence"):
        return "ADVISORY"
    return "OK"
