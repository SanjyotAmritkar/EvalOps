#!/usr/bin/env python3
"""Deterministic, idempotent demo data for EvalOps (Phase 10, CP 10.6).

Populates one project -- "EvalOps Demo -- Support Assistant" -- through the
**public HTTP API only** (the same contracts a real client uses; no backend
internals, no direct database access). Every provider call is the built-in
deterministic ``MockProvider`` (``execution.backend: "mock"``): no network, no
API key, no Ollama. Every response/latency/tool-call value below is a
synthetic test value, clearly not output from a real model -- exactly the
existing convention in examples/support/*.yaml.

One coherent scenario -- a customer-support reply assistant -- demonstrates,
through the *existing* Dataset -> Experiment -> Eval Runner -> statistical
evidence -> release gate pipeline (no new evaluation semantics):

* a clean PASS (a safe candidate update)
* a genuine, statistically-unconditional BLOCK (a risky candidate update that
  is both slower, past the latency budget, and wrong on two support policy
  questions) -- with real regression-diagnostics findings
* the *same* risky candidate re-evaluated against a smaller 4-case subset,
  landing as an advisory (``regression_low_evidence``) instead of a BLOCK --
  demonstrating why ``MIN_PAIRS_TO_BLOCK`` exists
* RAG retrieval evaluation (a dropped context chunk regresses recall)
* agent/tool evaluation (wrong tool arguments and an extra call regress
  tool_arguments and reveal the tool_selection.mean_score blind spot)
* production traces, three promoted into a replayable regression dataset,
  replayed through a clean PASS -- closing the trace -> dataset -> experiment
  loop end to end

Idempotent: re-running against a database that already has the demo project
prints its current state and exits without creating anything new -- there is
no update/delete endpoint for a project, so "safe to re-run" means "detect and
skip", the same idiom used by deploy/azure/*.sh.

Usage::

    uv run uvicorn evalops.api.main:app &   # or point --base-url at any
                                             # running instance (Compose,
                                             # an already-deployed Azure app)
    uv run python scripts/seed_demo.py

See docs/DEMO.md for the guided walkthrough this data supports.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from string import Template
from typing import Any, TextIO

import httpx

PROJECT_NAME = "EvalOps Demo — Support Assistant"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"

SUPPORT_TEMPLATE = "You are a support assistant.\nQ: ${input}\nA:"
RAG_TEMPLATE = "Answer using the retrieved context.\nQ: ${input}\nA:"
AGENT_TEMPLATE = "Handle this support ticket.\nQ: ${input}\nA:"

# --- text scenario: 8 support-policy questions, reused across the PASS,
# BLOCK, and quick-check experiments (a subset of the same 8) ---------------

CASES: tuple[tuple[str, str], ...] = (
    ("What is your refund policy?", "Refunds are available within 30 days of purchase."),
    ("How do I reset my password?", "Use the Forgot Password link on the sign-in page."),
    ("Do you offer phone support?", "We offer email and chat support only."),
    ("How do I cancel my subscription?", "Go to Billing settings and click Cancel subscription."),
    ("What payment methods do you accept?", "We accept all major credit cards and PayPal."),
    ("How long does shipping take?", "Standard shipping takes 3 to 5 business days."),
    ("Can I change my email address?", "Yes, update it in Account settings."),
    ("Is there a free trial?", "Yes, a 14 day free trial is available."),
)
QUICK_CHECK_CASES = CASES[:4]

# The risky candidate hallucinates on these two support-policy questions
# (a realistic regression, not a typo) while also answering everything 80%
# slower -- two independent, genuine regression signals in one build.
_WRONG_ANSWERS = {
    "Do you offer phone support?": "Yes, call our 24/7 phone line any time.",
    "Can I change my email address?": "Email addresses cannot be changed once set.",
}


def _render(template: str, case_input: str) -> str:
    """Mirror ``evalops.prompt.render_prompt`` (stdlib ``string.Template``,
    ``${input}`` only) so a mock ``responses`` map keys on the exact string
    the runner will render and look up."""
    return Template(template).substitute(input=case_input)


def _support_mock(*, wrong_on: frozenset[str] = frozenset(), latency_ms: float) -> dict[str, Any]:
    responses = {
        _render(SUPPORT_TEMPLATE, q): (_WRONG_ANSWERS[q] if q in wrong_on else a) for q, a in CASES
    }
    return {"mock": {"responses": responses, "default": "I don't know.", "latency_ms": latency_ms}}


# --- RAG scenario: a knowledge-base article split into two chunks; the
# candidate drops the second chunk, regressing recall (and groundedness) ----

_RAG_CASES: tuple[tuple[str, str, str, str], ...] = (
    (
        "What is your refund policy?",
        "Refunds are available within 30 days of purchase.",
        "Refund requests must include the original order number.",
        "Refunds are available within 30 days of purchase, and refund requests "
        "must include the original order number.",
    ),
    (
        "How do I reset my password?",
        "Use the Forgot Password link on the sign-in page.",
        "Password reset links expire after 1 hour.",
        "Use the Forgot Password link on the sign-in page; reset links expire after 1 hour.",
    ),
    (
        "What payment methods do you accept?",
        "We accept all major credit cards.",
        "We also accept PayPal in most regions.",
        "We accept all major credit cards, and we also accept PayPal in most regions.",
    ),
    (
        "How long does shipping take?",
        "Standard shipping takes 3 to 5 business days.",
        "Expedited shipping is available at checkout for 1 to 2 business days.",
        "Standard shipping takes 3 to 5 business days; expedited shipping is "
        "available at checkout for 1 to 2 business days.",
    ),
)


def _rag_mock(*, drop_second_chunk: bool) -> dict[str, Any]:
    responses: dict[str, str] = {}
    retrieval: dict[str, list[dict[str, Any]]] = {}
    for question, chunk_a, chunk_b, answer in _RAG_CASES:
        prompt = _render(RAG_TEMPLATE, question)
        responses[prompt] = answer
        items = [{"doc_id": f"{question}::a", "content": chunk_a, "rank": 0}]
        if not drop_second_chunk:
            items.append({"doc_id": f"{question}::b", "content": chunk_b, "rank": 1})
        retrieval[prompt] = items
    return {"mock": {"responses": responses, "retrieval": retrieval, "latency_ms": 150}}


# --- Agent scenario: a ticket-triage agent that looks up the account then
# issues a refund; the candidate sends the wrong account id and adds an
# unnecessary escalation call -----------------------------------------------

_AGENT_TOPICS = (
    "a duplicate charge",
    "a missing refund",
    "a failed password reset",
    "a late shipment",
)


def _agent_mock(*, misbehave: bool) -> dict[str, Any]:
    tool_calls: dict[str, list[dict[str, Any]]] = {}
    for topic in _AGENT_TOPICS:
        prompt = _render(AGENT_TEMPLATE, topic)
        if misbehave:
            tool_calls[prompt] = [
                {"name": "lookup_account", "arguments": {"query": "WRONG-ACCOUNT"}},
                {"name": "issue_refund", "arguments": {"topic": topic}},
                {"name": "escalate_ticket", "arguments": {}},  # unnecessary extra call
            ]
        else:
            tool_calls[prompt] = [
                {"name": "lookup_account", "arguments": {"query": topic}},
                {"name": "issue_refund", "arguments": {"topic": topic}},
            ]
    responses = {_render(AGENT_TEMPLATE, t): "Resolved." for t in _AGENT_TOPICS}
    return {"mock": {"responses": responses, "tool_calls": tool_calls, "latency_ms": 150}}


class SeedError(RuntimeError):
    """The API rejected a seed request; carries the response body verbatim."""


@dataclass
class SeedResult:
    created: bool
    project_id: str
    experiments: dict[str, dict[str, Any]] = field(default_factory=dict)
    trace_ids: list[str] = field(default_factory=list)
    promoted_dataset_id: str | None = None
    judge_calibration_id: str | None = None


def _get(client: httpx.Client, path: str) -> Any:
    resp = client.get(path)
    if resp.status_code >= 400:
        raise SeedError(f"GET {path} -> {resp.status_code}: {resp.text}")
    return resp.json()


def _post(client: httpx.Client, path: str, json: dict[str, Any]) -> Any:
    resp = client.post(path, json=json)
    if resp.status_code >= 400:
        raise SeedError(f"POST {path} -> {resp.status_code}: {resp.text}")
    return resp.json()


def _system_version(
    client: httpx.Client,
    project_id: str,
    *,
    name: str,
    version: str,
    prompt_template: str,
    parameters: dict[str, Any],
) -> str:
    body = _post(
        client,
        f"/projects/{project_id}/system-versions",
        {
            "name": name,
            "version": version,
            "provider": "openai",  # never actually called: execution.backend="mock"
            "model": "demo-model",
            "prompt_template": prompt_template,
            "parameters": parameters,
        },
    )
    return str(body["id"])


def _dataset(
    client: httpx.Client, project_id: str, *, name: str, cases: list[dict[str, Any]]
) -> str:
    body = _post(
        client,
        f"/projects/{project_id}/datasets",
        {"name": name, "version": 1, "cases": cases},
    )
    return str(body["id"])


def _policy(client: httpx.Client, *, name: str, thresholds: dict[str, float]) -> str:
    body = _post(client, "/release-policies", {"name": name, "thresholds": thresholds})
    return str(body["id"])


def _experiment(
    client: httpx.Client,
    project_id: str,
    *,
    dataset_id: str,
    baseline_id: str,
    candidate_id: str,
    repeats: int,
    policy_id: str,
) -> str:
    body = _post(
        client,
        f"/projects/{project_id}/experiments",
        {
            "dataset_id": dataset_id,
            "baseline_version_id": baseline_id,
            "candidate_version_id": candidate_id,
            "repeats": repeats,
            "release_policy_id": policy_id,
        },
    )
    return str(body["id"])


def _run(
    client: httpx.Client, experiment_id: str, *, evaluators: list[dict[str, Any]]
) -> dict[str, Any]:
    return dict(
        _post(
            client,
            f"/experiments/{experiment_id}/run",
            {"execution": {"backend": "mock"}, "evaluators": evaluators},
        )
    )


def _find_existing_project(client: httpx.Client) -> dict[str, Any] | None:
    for project in _get(client, "/projects"):
        if project["name"] == PROJECT_NAME:
            return dict(project)
    return None


def _text_evaluators() -> list[dict[str, Any]]:
    return [{"type": "exact_match"}, {"type": "contains", "case_sensitive": False}]


def _rag_evaluators() -> list[dict[str, Any]]:
    return [
        {"type": "retrieval_recall", "min_recall": 1.0},
        {"type": "context_precision", "min_precision": 1.0},
        {"type": "groundedness", "min_groundedness": 0.7},
    ]


def _agent_evaluators() -> list[dict[str, Any]]:
    return [
        {"type": "tool_selection", "min_score": 0.5},
        {"type": "tool_arguments", "min_score": 1.0},
        {"type": "tool_success", "min_score": 1.0},
    ]


def seed(client: httpx.Client, *, out: TextIO = sys.stdout) -> SeedResult:
    """Create the demo project and its full scenario, or report it already exists.

    ``client`` is any ``httpx.Client``-compatible object (a real
    ``httpx.Client`` against a running server, or a ``TestClient`` in tests) --
    already carrying whatever ``base_url`` / auth header it needs.
    """
    existing = _find_existing_project(client)
    if existing is not None:
        project_id = str(existing["id"])
        existing_experiments = _get(client, f"/projects/{project_id}/experiments")
        print(
            f"Demo project already exists ({PROJECT_NAME!r}, id={project_id}) with "
            f"{len(existing_experiments)} experiment(s) -- not re-seeding. Delete the database "
            "(or its 'evalops_demo' rows) to reseed from scratch.",
            file=out,
        )
        return SeedResult(created=False, project_id=project_id)

    print(f"Creating {PROJECT_NAME!r} ...", file=out)
    project_id = str(_post(client, "/projects", {"name": PROJECT_NAME})["id"])

    # --- text scenario: shared baseline, a safe candidate, a risky candidate
    baseline_id = _system_version(
        client,
        project_id,
        name="support-prompt",
        version="v1 (production)",
        prompt_template=SUPPORT_TEMPLATE,
        parameters=_support_mock(latency_ms=200),
    )
    safe_candidate_id = _system_version(
        client,
        project_id,
        name="support-prompt",
        version="v2 (safe update)",
        prompt_template=SUPPORT_TEMPLATE,
        parameters=_support_mock(latency_ms=210),
    )
    risky_candidate_id = _system_version(
        client,
        project_id,
        name="support-prompt",
        version="v2 (risky update)",
        prompt_template=SUPPORT_TEMPLATE,
        parameters=_support_mock(wrong_on=frozenset(_WRONG_ANSWERS), latency_ms=360),
    )

    full_suite_id = _dataset(
        client,
        project_id,
        name="Support replies — full suite",
        cases=[{"input": q, "expected_output": a} for q, a in CASES],
    )
    quick_check_id = _dataset(
        client,
        project_id,
        name="Support replies — quick check",
        cases=[{"input": q, "expected_output": a} for q, a in QUICK_CHECK_CASES],
    )

    standard_policy_id = _policy(
        client,
        name="Quality & latency (standard, demo)",
        thresholds={
            "success_rate": 0.0,
            "exact_match.pass_rate": 0.05,
            "contains.pass_rate": 0.05,
            "latency_ms.p95": 0.20,
        },
    )
    # Deliberately excludes latency_ms.p95 (no evidence needed, unconditional
    # BLOCK) so this policy isolates the quality signal at a smaller sample.
    quick_check_policy_id = _policy(
        client,
        name="Quality only, quick check (demo)",
        thresholds={"exact_match.pass_rate": 0.05, "contains.pass_rate": 0.05},
    )

    experiments: dict[str, dict[str, Any]] = {}

    pass_experiment_id = _experiment(
        client,
        project_id,
        dataset_id=full_suite_id,
        baseline_id=baseline_id,
        candidate_id=safe_candidate_id,
        repeats=1,
        policy_id=standard_policy_id,
    )
    experiments["pass_clean"] = _run(client, pass_experiment_id, evaluators=_text_evaluators())

    block_experiment_id = _experiment(
        client,
        project_id,
        dataset_id=full_suite_id,
        baseline_id=baseline_id,
        candidate_id=risky_candidate_id,
        repeats=1,
        policy_id=standard_policy_id,
    )
    experiments["block_full_suite"] = _run(
        client, block_experiment_id, evaluators=_text_evaluators()
    )

    advisory_experiment_id = _experiment(
        client,
        project_id,
        dataset_id=quick_check_id,
        baseline_id=baseline_id,
        candidate_id=risky_candidate_id,
        repeats=1,
        policy_id=quick_check_policy_id,
    )
    experiments["advisory_quick_check"] = _run(
        client, advisory_experiment_id, evaluators=_text_evaluators()
    )

    # --- RAG scenario ---
    rag_baseline_id = _system_version(
        client,
        project_id,
        name="support-kb-retrieval",
        version="v1 (production)",
        prompt_template=RAG_TEMPLATE,
        parameters=_rag_mock(drop_second_chunk=False),
    )
    rag_candidate_id = _system_version(
        client,
        project_id,
        name="support-kb-retrieval",
        version="v2 (dropped chunk)",
        prompt_template=RAG_TEMPLATE,
        parameters=_rag_mock(drop_second_chunk=True),
    )
    rag_dataset_id = _dataset(
        client,
        project_id,
        name="Support KB retrieval",
        cases=[
            {
                "input": question,
                "expected_output": answer,
                "expected_retrieval_ids": [f"{question}::a", f"{question}::b"],
            }
            for question, _a, _b, answer in _RAG_CASES
        ],
    )
    rag_policy_id = _policy(
        client, name="RAG retrieval quality (demo)", thresholds={"retrieval_recall.pass_rate": 0.10}
    )
    rag_experiment_id = _experiment(
        client,
        project_id,
        dataset_id=rag_dataset_id,
        baseline_id=rag_baseline_id,
        candidate_id=rag_candidate_id,
        repeats=2,
        policy_id=rag_policy_id,
    )
    experiments["block_rag"] = _run(client, rag_experiment_id, evaluators=_rag_evaluators())

    # --- Agent scenario ---
    agent_baseline_id = _system_version(
        client,
        project_id,
        name="ticket-triage-agent",
        version="v1 (production)",
        prompt_template=AGENT_TEMPLATE,
        parameters=_agent_mock(misbehave=False),
    )
    agent_candidate_id = _system_version(
        client,
        project_id,
        name="ticket-triage-agent",
        version="v2 (regressed tool use)",
        prompt_template=AGENT_TEMPLATE,
        parameters=_agent_mock(misbehave=True),
    )
    agent_dataset_id = _dataset(
        client,
        project_id,
        name="Support ticket triage (agent)",
        cases=[
            {
                "input": topic,
                "expected_output": "Resolved.",
                "expected_tool_calls": [
                    {"name": "lookup_account", "arguments": {"query": topic}},
                    {"name": "issue_refund", "arguments": {"topic": topic}},
                ],
            }
            for topic in _AGENT_TOPICS
        ],
    )
    agent_policy_id = _policy(
        client,
        name="Agent tool policy (demo)",
        thresholds={"tool_selection.mean_score": 0.10, "tool_arguments.pass_rate": 0.10},
    )
    agent_experiment_id = _experiment(
        client,
        project_id,
        dataset_id=agent_dataset_id,
        baseline_id=agent_baseline_id,
        candidate_id=agent_candidate_id,
        repeats=2,
        policy_id=agent_policy_id,
    )
    experiments["block_agent"] = _run(client, agent_experiment_id, evaluators=_agent_evaluators())

    # --- Production traces -> promote -> replay -------------------------
    trace_cases = (CASES[0], CASES[1], CASES[3], CASES[4])
    trace_ids: list[str] = []
    for index, (question, answer) in enumerate(trace_cases):
        has_reference = index != 3  # the 4th trace deliberately has no reference
        trace = _post(
            client,
            f"/projects/{project_id}/traces",
            {
                "system_version_id": baseline_id,
                "input": question,
                "output": answer,
                "reference_output": answer if has_reference else None,
                "metadata": {
                    "channel": "email" if index % 2 == 0 else "chat",
                    "ticket_id": f"T-100{index + 1}",
                },
                "latency_ms": 200,
                "cost_usd": 0.0,
            },
        )
        trace_ids.append(str(trace["id"]))

    promoted_dataset = _post(
        client,
        f"/projects/{project_id}/trace-datasets",
        {
            "name": "Support replies — promoted from production",
            "trace_ids": trace_ids[:3],  # only the three with a reference
        },
    )
    promoted_dataset_id = str(promoted_dataset["id"])

    replay_experiment_id = _experiment(
        client,
        project_id,
        dataset_id=promoted_dataset_id,
        baseline_id=baseline_id,
        candidate_id=safe_candidate_id,
        repeats=1,
        policy_id=standard_policy_id,
    )
    experiments["pass_promoted_traces"] = _run(
        client, replay_experiment_id, evaluators=_text_evaluators()
    )

    result = SeedResult(
        created=True,
        project_id=project_id,
        experiments=experiments,
        trace_ids=trace_ids,
        promoted_dataset_id=promoted_dataset_id,
    )

    # --- Judge calibration: best-effort only. LLMJudge requires a real
    # ProviderName adapter (openai/anthropic/ollama) -- there is no mock
    # judge provider (see evalops.provider_registry), so this step needs a
    # real credential or a reachable local Ollama. It is never required for
    # any of the scenario above, which stays 100% offline.
    result.judge_calibration_id = _maybe_seed_judge_calibration(client, out=out)

    print(f"Seeded {PROJECT_NAME!r} (project id={project_id}):", file=out)
    for key, run in experiments.items():
        print(f"  - {key}: {run['decision']} ({run['dataset']})", file=out)
    return result


def _maybe_seed_judge_calibration(client: httpx.Client, *, out: TextIO) -> str | None:
    """Seed one small judge calibration, only when a real judge provider is
    actually usable -- never fabricated, never attempted with MockProvider
    (LLMJudge has no mock adapter). Skips cleanly and says why otherwise."""
    if os.environ.get("OPENAI_API_KEY"):
        provider, model = "openai", "gpt-4o-mini"
    elif os.environ.get("ANTHROPIC_API_KEY"):
        provider, model = "anthropic", "claude-3-5-haiku-latest"
    else:
        print(
            "Skipping judge calibration demo: no OPENAI_API_KEY / ANTHROPIC_API_KEY set. "
            "LLMJudge has no mock provider (by design -- see evalops.provider_registry), so "
            "this step needs a real credential. See docs/DEMO.md for how to run it manually.",
            file=out,
        )
        return None

    examples = [
        {
            "input": "What is your refund policy?",
            "output": "Refunds are available within 30 days of purchase.",
            "reference": "Refunds are available within 30 days of purchase.",
            "human_pass": True,
        },
        {
            "input": "Do you offer phone support?",
            "output": "Yes, call our 24/7 phone line any time.",
            "reference": "We offer email and chat support only.",
            "human_pass": False,
        },
        {
            "input": "How do I reset my password?",
            "output": "Use the Forgot Password link on the sign-in page.",
            "reference": "Use the Forgot Password link on the sign-in page.",
            "human_pass": True,
        },
        {
            "input": "Is there a free trial?",
            "output": "No trials are offered.",
            "reference": "Yes, a 14 day free trial is available.",
            "human_pass": False,
        },
    ]
    print(f"Running a judge calibration demo with the real {provider}/{model} ...", file=out)
    calibration = _post(
        client,
        "/judge-calibrations",
        {
            "provider": provider,
            "model": model,
            "name": "support-assistant-demo",
            "examples": examples,
        },
    )
    return str(calibration["id"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--base-url",
        default=os.environ.get("EVALOPS_API_BASE_URL", DEFAULT_BASE_URL),
        help=f"Running EvalOps API to seed (default: {DEFAULT_BASE_URL}, or $EVALOPS_API_BASE_URL)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("EVALOPS_API_KEY"),
        help="Sent as 'Authorization: Bearer <key>' if the target API requires it "
        "(default: $EVALOPS_API_KEY)",
    )
    args = parser.parse_args(argv)

    headers = {"Authorization": f"Bearer {args.api_key}"} if args.api_key else {}
    try:
        with httpx.Client(base_url=args.base_url, headers=headers, timeout=30.0) as client:
            seed(client)
    except httpx.ConnectError as exc:
        print(
            f"error: could not reach {args.base_url} -- is the API running? ({exc})",
            file=sys.stderr,
        )
        return 1
    except SeedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
