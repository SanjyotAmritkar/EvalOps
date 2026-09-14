"""Validates scripts/seed_demo.py (Phase 10, CP 10.6) end to end through the
same in-process FastAPI TestClient every API test uses -- no real HTTP, no
network, no real provider. Asserts the demo produces exactly the PASS / BLOCK
/ advisory / RAG / agent states it claims, that trace promotion actually
closes the loop, and that a second run is a true no-op (idempotent).
"""

from __future__ import annotations

import io

import seed_demo
from fastapi.testclient import TestClient


def test_seed_creates_the_full_demo_scenario(client: TestClient) -> None:
    out = io.StringIO()
    result = seed_demo.seed(client, out=out)

    assert result.created is True
    assert len(result.trace_ids) == 4
    assert result.promoted_dataset_id is not None
    # No OPENAI_API_KEY / ANTHROPIC_API_KEY in the test environment -- the
    # judge-calibration step must skip cleanly, never fabricate a result.
    assert result.judge_calibration_id is None

    decisions = {key: run["decision"] for key, run in result.experiments.items()}
    assert decisions == {
        "pass_clean": "pass",
        "block_full_suite": "block",
        "advisory_quick_check": "pass",
        "block_rag": "block",
        "block_agent": "block",
        "pass_promoted_traces": "pass",
    }

    # The advisory run is a PASS that still carries an advisory -- the whole
    # point of the regression_low_evidence distinction.
    assert result.experiments["advisory_quick_check"]["advisories"], (
        "the quick-check experiment should surface an advisory, not a silent pass"
    )
    assert result.experiments["pass_clean"]["advisories"] == []

    # The full-suite BLOCK has real, non-trivial regression diagnostics.
    block_experiment_id = result.experiments["block_full_suite"]["experiment_id"]
    diagnostics = client.get(f"/experiments/{block_experiment_id}/diagnostics").json()
    assert diagnostics["regressing_pairs"] > 0
    assert diagnostics["regressing_cases"], "expected at least one regressing case surfaced"

    # RAG/agent evidence actually flowed through the ordinary run/metric path.
    rag_metrics = {m["metric"] for m in result.experiments["block_rag"]["metrics"]}
    assert "retrieval_recall.pass_rate" in rag_metrics
    agent_metrics = {m["metric"] for m in result.experiments["block_agent"]["metrics"]}
    assert "tool_arguments.pass_rate" in agent_metrics
    assert "tool_selection.mean_score" in agent_metrics

    # Traces: three promoted (had a reference), one deliberately without.
    traces = client.get(f"/projects/{result.project_id}/traces").json()
    with_reference = [t for t in traces if t["reference_output"] is not None]
    without_reference = [t for t in traces if t["reference_output"] is None]
    assert len(with_reference) == 3
    assert len(without_reference) == 1

    promoted = client.get(f"/datasets/{result.promoted_dataset_id}").json()
    assert len(promoted["cases"]) == 3
    assert all(case["origin"] == "promoted_trace" for case in promoted["cases"])


def test_seed_is_idempotent(client: TestClient) -> None:
    first = seed_demo.seed(client, out=io.StringIO())
    assert first.created is True

    second = seed_demo.seed(client, out=io.StringIO())
    assert second.created is False
    assert second.project_id == first.project_id

    # No duplicate project and no duplicate experiments were created.
    projects = client.get("/projects").json()
    assert sum(1 for p in projects if p["name"] == seed_demo.PROJECT_NAME) == 1
    experiments = client.get(f"/projects/{first.project_id}/experiments").json()
    assert len(experiments) == 6
