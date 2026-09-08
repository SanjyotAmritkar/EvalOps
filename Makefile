.PHONY: install lint fmt fmt-check type test check

install:
	uv sync

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

fmt-check:
	uv run ruff format --check .

type:
	uv run mypy

test:
	uv run pytest

check: lint fmt-check type test
