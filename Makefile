.PHONY: install lint format typecheck test guard ci

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy

test:
	uv run pytest

guard:
	uv run lc guard

ci: lint typecheck test
	uv run lc guard --all
