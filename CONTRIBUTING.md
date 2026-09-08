# Contributing to EvalOps

[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) is the source of truth for scope,
architecture, the phased roadmap, and acceptance criteria. [`CLAUDE.md`](CLAUDE.md)
captures the working conventions for this repository. Read both before proposing
a change.

## Principles

- Build strictly by the phases in `docs/ARCHITECTURE.md`; implement only the
  current phase unless explicitly told otherwise.
- Prefer one complete vertical slice over broad scaffolding. Do not create
  directories or stubs for future phases.
- Keep evaluation/domain logic independent of API and UI infrastructure.
- Add tests for every implemented behavior. Do not fabricate tests for coverage.
- Type-hint everything; keep interfaces explicit.
- Avoid unnecessary dependencies. Never commit secrets. Never fabricate metrics
  or benchmark results.
- Keep the README's SHIPPED / COMMITTED / ROADMAP / VISION sections accurate.

## Environment

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pre-commit install
```

## Checks (must pass before a PR)

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

or `make check`. CI runs the same checks on Python 3.11 and 3.12.

## Branch & commit workflow

- Branch from `main`: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`,
  `ci/<slug>`, `refactor/<slug>`, `test/<slug>`.
- Use [Conventional Commits](https://www.conventionalcommits.org/):
  `type(scope): summary`. Types: `feat`, `fix`, `docs`, `chore`, `ci`,
  `refactor`, `test`, `build`, `perf`.
- Keep commits small and independently reviewable — one logically complete unit
  of work each. A feature branch is typically 1–3 such commits.
- Flow: branch -> checks pass -> review the final diff -> commit(s) -> push ->
  open a PR -> CI green -> merge to `main`.
- `main` must always be in a working state.

## Commit checkpoints

A commit marks a logically complete, independently testable unit of work — for
example "define core domain models and their invariant tests" or "add dataset
loader + validation tests". Not: a single file, one helper function, a rename, a
formatting-only change, or several unrelated features squashed together.

## Tests evolve with the architecture

Add the testing level appropriate to what a change introduces — unit, contract,
integration, end-to-end, failure/recovery, or load/performance — as those
components come into existence. Coverage thresholds are introduced later, once
there is meaningful application logic; they are not chased early.
