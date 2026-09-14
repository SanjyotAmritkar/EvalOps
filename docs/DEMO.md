# EvalOps demo walkthrough (3–5 minutes)

A guided tour through one seeded, deterministic scenario — **"EvalOps Demo —
Support Assistant"** — that shows every shipped capability without prior
product knowledge. Everything below except the last two steps runs entirely
on the built-in `MockProvider`: no network call, no API key, nothing to
configure.

## Setup (once)

```bash
cp .env.example .env
echo "EVALOPS_API_KEY=$(openssl rand -hex 32)" >> .env
docker compose up --build          # or the non-containerized flow in the README
make seed-demo                     # idempotent — safe to run again
open http://localhost:3000/projects
```

Open the **"EvalOps Demo — Support Assistant"** project. Everything referenced
below is a real, persisted resource created by `scripts/seed_demo.py` through
the ordinary public API — nothing on the page is demo-specific UI, and
nothing here required a paid provider.

---

## 1. PASS — a safe candidate update

Open **Experiments → "support-prompt v1 (production) → support-prompt v2
(safe update)"** on the *Support replies — full suite* dataset.

The decision hero reads **PASS · Ready to release**: the candidate keeps every
answer correct and its latency rise stays inside the release policy's budget.
Point out the comparison header (baseline → candidate, dataset, policy) and
that every number here — the metrics, the decision — comes from the backend;
the dashboard never computes a verdict.

## 2. BLOCK — a genuine, confirmed regression

Back to Experiments, open **"... → support-prompt v2 (risky update)"** on the
same *full suite* dataset.

**BLOCK · Release blocked.** This candidate is both slower (past the p95
latency budget — an unconditional block, no statistics needed for that
metric) *and* wrong on two support-policy questions it used to answer
correctly. Scroll to:

- **What changed, metric by metric** — every metric side by side, not just
  the ones that blocked.
- **Statistical evidence** — expand one entry to show the paired-bootstrap
  confidence interval behind the confirmed metrics.
- **Why was this blocked?** (regression diagnostics) — the two regressing
  cases, each expandable to a side-by-side baseline vs candidate run,
  including the exact answer the candidate hallucinated. This is explanatory
  only: diagnostics never change the decision above it.

## 3. PASS with advisory — the same regression, a smaller sample

Open **"... → support-prompt v2 (risky update)"** again, this time on the
*Support replies — quick check* dataset (a 4-case subset of the same
questions, under a policy that intentionally doesn't gate latency).

This is the same risky build, the same quality drop — but with too few paired
samples to statistically confirm a regression, so it reads **PASS · Passed
with unverified concerns**, with the breach surfaced as an advisory rather
than silently passing *or* blocking on noise. This pair (step 2 vs step 3) is
the cleanest way to show why EvalOps has a minimum-evidence threshold at all.

## 4. RAG evaluation

Open **"support-kb-retrieval v1 (production) → v2 (dropped chunk)"** on
*Support KB retrieval*. The candidate answers by retrieving only one of two
relevant knowledge-base chunks. **BLOCK** on `retrieval_recall.pass_rate`.
Expand a run's **Retrieved context** to show the retrieval evidence itself —
explicitly labelled as *what the system reported retrieving*, not ground
truth EvalOps computed.

## 5. Agent evaluation

Open **"ticket-triage-agent v1 (production) → v2 (regressed tool use)"** on
*Support ticket triage (agent)*. The candidate calls a tool with the wrong
argument and makes an unnecessary extra call. Point out two things at once:
`tool_arguments.pass_rate` collapses (a hard pass/fail regression), **and**
`tool_selection.mean_score` shows a graded drop while
`tool_selection.pass_rate` stays unchanged — the generic mean-score metric
that makes a "still technically passing but clearly worse" regression visible
to the release policy.

## 6. Production trace → regression dataset

Open **Production Traces**. Four captured interactions are listed; select the
three that have a recorded reference (the fourth deliberately has none —
point out the non-blocking "cases without references can still be replayed"
note) and note they're already promoted into **"Support replies — promoted
from production."** Open that dataset, then the experiment run against it
(baseline vs the safe candidate) — a clean **PASS**, closing the loop:
production traffic → captured trace → promoted regression case → ordinary
experiment → release decision.

## 7. CI release gate

Outside the dashboard: [`.github/workflows/release-gate.yml`](../.github/workflows/release-gate.yml)
runs `evalops run` on every pull request against a checked-in deterministic
config and fails the GitHub check only on a real BLOCK — the same decision
logic as every step above, byte-identical between the CLI, the API, and the
dashboard. Show it locally:

```bash
uv run evalops run examples/support/regression.yaml   # -> BLOCK, exit 1
uv run evalops run examples/support/fixed.yaml         # -> PASS,  exit 0
```

## 8. Deployed architecture

The same stack (dashboard, API, worker, PostgreSQL, Redis) runs on Azure
Container Apps, provisioned by reproducible `az` CLI scripts and deployed by a
manually-triggered, OIDC-authenticated GitHub Actions workflow — no stored
Azure password anywhere. Point at `deploy/azure/README.md` and
[ARCHITECTURE.md §7.11](ARCHITECTURE.md#711-implemented-api-security--azure-production-deployment-phase-10-cp-105)
rather than re-deploying live.

---

## Optional: judge calibration (needs a real provider)

Everything above needs **no credential**. Judge calibration is the one
exception — `LLMJudge` has no mock adapter, so measuring one requires a real
provider: set **either** `OPENAI_API_KEY` **or** `ANTHROPIC_API_KEY` (not
both) before running `make seed-demo`, and it seeds one small calibration
automatically; otherwise it's skipped with a clear message. To run it by hand
from the dashboard instead, open **Judge Calibration → New calibration**,
pick whichever provider you configured, and supply 3–5 labeled examples. The
result — agreement rate, precision/recall/F1 — is explicitly **measurement
only**: a low agreement rate never blocks a release or disables the judge.

## Re-running the demo

`make seed-demo` is idempotent: it looks up the demo project by name and, if
found, does nothing further. To see it seed from scratch, drop the database
(or just its rows) and re-run it.
