.PHONY: install lint format typecheck test guard ci hero

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
	uv run lc checklist validate
	uv run lc guard --all

hero:  ## redraw the README banner, docs/hero.svg and docs/hero.png (needs Chromium + Pillow)
	uv run --with pillow python tools/hero.py
