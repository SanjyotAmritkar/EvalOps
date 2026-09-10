"""Render a GitHub Actions PR summary from an ``evalops run`` schema-v2 report.

CI glue, nothing more. It does **not** re-derive a release decision: the CLI
already computed ``decision`` / ``reasons`` / ``advisories`` / per-metric
``gate_outcome`` through the shared ``run_evaluation`` path (CP 7.1). This
module only formats that JSON for ``$GITHUB_STEP_SUMMARY`` and re-raises the
CLI's exit code so the workflow fails on a real BLOCK (1) or an execution
error (2) -- and never conflates the two.

    python -m evalops.ci --exit-code N --report PATH [--log PATH] [--config STR]

Exit code (returned verbatim, so the calling step's status is the gate):
``0`` PASS (incl. PASS with advisories), ``1`` BLOCK, ``2`` execution/config error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

#: How ``gate_outcome`` reads in the metric table.
_OUTCOME_LABEL = {
    "pass": "pass",
    "regression": "**regression**",
    "regression_inconclusive": "breach (inconclusive)",
    "regression_low_evidence": "breach (low evidence)",
}

#: Diagnostic text from a failed run is bounded before it reaches the summary.
_MAX_LOG_CHARS = 4000


# --- report loading --------------------------------------------------------


def load_report(path: Path) -> dict[str, Any] | None:
    """Parse a schema-v2 report file, or return ``None`` if it is missing or
    not a JSON object. Never raises on bad input."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _bound(text: str) -> str:
    text = text.strip()
    if len(text) > _MAX_LOG_CHARS:
        return "…(truncated)…\n" + text[-_MAX_LOG_CHARS:]
    return text


def _read_tail(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return _bound(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""


# --- formatting helpers --------------------------------------------------


def _num(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "—"
    return f"{value:.4g}"


def _signed(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "—"
    return f"{value:+.4g}"


def _pct(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "—"
    return f"{value:.0%}"


def _outcome_label(outcome: Any) -> str:
    return _OUTCOME_LABEL.get(outcome, str(outcome)) if isinstance(outcome, str) else "—"


def _context_line(report: dict[str, Any] | None, config: str | None) -> str:
    parts: list[str] = []
    if config:
        parts.append(f"config `{config}`")
    if isinstance(report, dict):
        cand = report.get("candidate") or {}
        base = report.get("baseline") or {}
        if isinstance(cand, dict) and isinstance(base, dict) and cand.get("name"):
            parts.append(
                f"candidate **{cand.get('name')} {cand.get('version', '')}**".rstrip()
                + f" vs baseline **{base.get('name')} {base.get('version', '')}**".rstrip()
            )
        counts = report.get("counts") or {}
        if isinstance(counts, dict) and "runs" in counts:
            parts.append(
                f"{counts.get('cases', '?')} cases / {counts.get('runs', '?')} runs / "
                f"{counts.get('failures', '?')} failures"
            )
    return " · ".join(parts)


def _metric_table(report: dict[str, Any] | None) -> list[str]:
    metrics = report.get("metrics") if isinstance(report, dict) else None
    if not isinstance(metrics, list):
        return []
    data = [
        f"| `{m.get('metric', '?')}` "
        f"| {_num(m.get('baseline_value'))} "
        f"| {_num(m.get('candidate_value'))} "
        f"| {_signed(m.get('delta'))} "
        f"| {'—' if m.get('threshold') is None else _pct(m.get('threshold'))} "
        f"| {_outcome_label(m.get('gate_outcome'))} |"
        for m in metrics
        if isinstance(m, dict)
    ]
    if not data:
        return []
    return [
        "| Metric | Baseline | Candidate | Δ | Allowed | Outcome |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
        *data,
    ]


def _bullets(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [f"- {item}" for item in items if isinstance(item, str)]


# --- section renderers -------------------------------------------------


def _render_pass(report: dict[str, Any] | None, config: str | None) -> str:
    advisories = report.get("advisories") if isinstance(report, dict) else None
    has_advisories = isinstance(advisories, list) and len(advisories) > 0

    lines = ["## ✅ EvalOps release gate: PASS", ""]
    context = _context_line(report, config)
    if context:
        lines += [context, ""]
    if report is None:
        lines += ["_The run exited 0 but no JSON report was found._", ""]
    if has_advisories:
        lines += [
            "> **Passed with advisories.** A policy threshold was breached at the "
            "point estimate, but the statistical evidence is too weak to block. "
            "**This is still a PASS** — nothing to fix to merge.",
            "",
            "### Advisories",
            *_bullets(advisories),
            "",
        ]
    table = _metric_table(report)
    if table:
        lines += ["### Metrics", *table, ""]
    return "\n".join(lines).rstrip() + "\n"


def _render_block(report: dict[str, Any] | None, config: str | None) -> str:
    lines = ["## 🚫 EvalOps release gate: BLOCK", ""]
    context = _context_line(report, config)
    if context:
        lines += [context, ""]
    reasons = _bullets(report.get("reasons")) if isinstance(report, dict) else []
    lines += ["### Blocking reasons", *(reasons or ["- (no reasons recorded in the report)"]), ""]

    advisories = report.get("advisories") if isinstance(report, dict) else None
    if isinstance(advisories, list) and advisories:
        lines += ["### Advisories", *_bullets(advisories), ""]

    table = _metric_table(report)
    if table:
        lines += ["### Metrics", *table, ""]
    return "\n".join(lines).rstrip() + "\n"


def _render_error(exit_code: int, log: str, config: str | None) -> str:
    lines = [
        "## ⚠️ EvalOps release gate: ERROR",
        "",
        f"EvalOps could not complete the evaluation (exit code {exit_code} — a "
        "configuration, execution, dataset, or provider/judge error). "
        "**No release decision was produced.** This is not a release BLOCK; fix "
        "the error and re-run.",
        "",
    ]
    if config:
        lines += [f"config `{config}`", ""]
    diagnostic = _bound(log)
    if diagnostic:
        lines += [
            "<details><summary>Diagnostic output</summary>",
            "",
            "```",
            diagnostic,
            "```",
            "",
            "</details>",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def render_pr_summary(
    report: dict[str, Any] | None,
    exit_code: int,
    *,
    log: str = "",
    config: str | None = None,
) -> str:
    """Markdown for ``$GITHUB_STEP_SUMMARY``. ``exit_code`` is authoritative:
    0 → PASS section, 1 → BLOCK section, anything else → ERROR section. A
    non-empty ``advisories`` list on a PASS stays a PASS."""
    if exit_code == 0:
        return _render_pass(report, config)
    if exit_code == 1:
        return _render_block(report, config)
    return _render_error(exit_code, log, config)


# --- entry point -----------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evalops-ci-summary",
        description="Render a GitHub Step Summary from an evalops run schema-v2 report.",
    )
    parser.add_argument("--exit-code", type=int, required=True, help="The `evalops run` exit code")
    parser.add_argument("--report", type=Path, required=True, help="Path to the --json report file")
    parser.add_argument("--log", type=Path, default=None, help="Optional captured stderr log")
    parser.add_argument("--config", default=None, help="Config path, for context only")
    args = parser.parse_args(argv)

    exit_code: int = args.exit_code
    report = load_report(args.report)
    log = _read_tail(args.log) if exit_code not in (0, 1) else ""
    summary = render_pr_summary(report, exit_code, log=log, config=args.config)

    destination = os.environ.get("GITHUB_STEP_SUMMARY")
    if destination:
        with open(destination, "a", encoding="utf-8") as handle:
            handle.write(summary + "\n")
    else:
        sys.stdout.write(summary + "\n")

    # Return the CLI's code verbatim so this step's status IS the release gate.
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
