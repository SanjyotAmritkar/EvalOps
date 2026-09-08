# EvalOps — Claude Code Instructions

## Source of Truth

Before making architectural or implementation decisions, read:

`docs/ARCHITECTURE.md`

That document defines the product scope, architecture, phased roadmap,
non-goals, domain model, and acceptance criteria.

If implementation and documentation conflict, flag the discrepancy
before changing architecture.

## Product

EvalOps is continuous reliability engineering for AI systems.

Tagline:

> CI/CD for nondeterministic AI systems.

The core workflow is:

AI change
→ evaluate baseline vs candidate
→ measure quality/cost/latency/reliability
→ detect regressions
→ apply release policy
→ PASS or BLOCK

Do not turn EvalOps into a generic model benchmark, chatbot, prompt
playground, or model leaderboard.

## Development Rules

- Work according to the phases in `docs/ARCHITECTURE.md`.
- Implement only the current phase unless explicitly instructed otherwise.
- Do not scaffold future features merely for appearance.
- Prefer complete vertical functionality over breadth.
- Keep evaluation/domain logic independent of API/UI infrastructure.
- Add tests for implemented behavior.
- Use type hints and clear interfaces.
- Avoid unnecessary dependencies.
- Never commit secrets.
- Never fabricate metrics or benchmark results.
- Keep README SHIPPED/COMMITTED/ROADMAP/VISION sections accurate.

## Deferred Infrastructure

Do not introduce these until their architecture phase requires them:

- Celery
- Redis
- pgvector
- OpenTelemetry
- Prometheus
- Grafana
- Kubernetes
- Kafka
- cloud deployment infrastructure

## Git

Do not commit or push unless explicitly requested.

For each completed unit of work:
1. summarize changed files
2. explain implementation decisions
3. provide verification commands
4. suggest a Conventional Commit message

Prefer small, logically scoped commits.

## Before Significant Changes

1. Inspect the existing implementation.
2. Read the relevant section of `docs/ARCHITECTURE.md`.
3. State the proposed change.
4. Identify affected files.
5. Implement only the requested scope.
6. Run relevant tests/checks.
7. Report results and remaining issues.