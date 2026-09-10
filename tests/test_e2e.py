"""One true end-to-end test: YAML + JSONL -> runner -> aggregate -> gate -> report.

Offline and deterministic. Requires no network, API key, or Ollama.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from evalops.cli import main

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "support"
REGRESSION = EXAMPLES / "regression.yaml"
FIXED = EXAMPLES / "fixed.yaml"


def test_regression_example_blocks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "result.json"

    rc = main(["run", str(REGRESSION), "--json", str(out)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "EvalOps Evaluation" in captured.out
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["decision"] == "block"
    assert payload["counts"] == {"cases": 4, "runs": 8, "failures": 0}
    assert any("latency_ms.p95" in reason for reason in payload["reasons"])
    # candidate improved quality even though the release is blocked
    exact = next(m for m in payload["metrics"] if m["metric"] == "exact_match.pass_rate")
    assert exact["baseline_value"] == 0.75
    assert exact["candidate_value"] == 1.0
    assert exact["regression"] is False


def test_fixed_example_passes(tmp_path: Path) -> None:
    out = tmp_path / "result.json"

    rc = main(["run", str(FIXED), "--json", str(out)])

    assert rc == 0
    assert json.loads(out.read_text(encoding="utf-8"))["decision"] == "pass"


def test_json_output_is_byte_identical_across_runs(tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    main(["run", str(REGRESSION), "--json", str(first), "--quiet"])
    main(["run", str(REGRESSION), "--json", str(second), "--quiet"])

    assert first.read_bytes() == second.read_bytes()


def test_module_entry_point_runs_offline() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "evalops", "run", str(FIXED), "--json", "-", "--quiet"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "pass"
