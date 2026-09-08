"""The ``evalops`` command-line interface (stdlib argparse only).

    evalops run CONFIG [--json PATH|-] [--quiet]

Exit codes: 0 = PASS or ungated, 1 = release-policy BLOCK, 2 = any
CLI/config/dataset/execution-system error. An individual case ProviderError is
handled by the runner and never becomes exit 2.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from evalops.aggregate import aggregate_results
from evalops.config import load_run_plan
from evalops.domain.enums import ReleaseDecision
from evalops.domain.errors import EvalOpsError
from evalops.gate import evaluate_gate
from evalops.report import build_report, human_report, json_report
from evalops.runner import run_experiment


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evalops", description="CI/CD for nondeterministic AI systems."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run an evaluation from a YAML config")
    run_parser.add_argument("config", help="Path to the run config YAML file")
    run_parser.add_argument(
        "--json",
        dest="json_path",
        metavar="PATH",
        help="Write the machine-readable JSON result to PATH ('-' for stdout)",
    )
    run_parser.add_argument(
        "--quiet", action="store_true", help="Suppress the human-readable report"
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args.config, json_path=args.json_path, quiet=args.quiet)
    return 2  # pragma: no cover - subparsers are required


def _run(config: str, *, json_path: str | None, quiet: bool) -> int:
    json_to_stdout = json_path == "-"
    # Keep stdout single-purpose: '--json -' always implies no human report.
    show_human = not quiet and not json_to_stdout

    try:
        plan = load_run_plan(config)
        outcome = run_experiment(
            plan.experiment,
            plan.dataset,
            plan.baseline,
            plan.candidate,
            providers=plan.providers,
            evaluators=plan.evaluators,
        )
        result = aggregate_results(
            plan.experiment, outcome, evaluator_names=[e.name for e in plan.evaluators]
        )
        gate = evaluate_gate(result, plan.policy)
        report = build_report(plan, outcome, result, gate)
    except EvalOpsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # CLI boundary: exit 1 must only ever mean BLOCK
        print(f"error: unexpected failure: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if show_human:
        sys.stdout.write(human_report(report))
    if json_path is not None:
        payload = json_report(report)
        if json_to_stdout:
            sys.stdout.write(payload)
        else:
            Path(json_path).write_text(payload, encoding="utf-8")

    return 1 if gate.decision is ReleaseDecision.BLOCK else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
