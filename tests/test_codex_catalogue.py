import tomllib
from typing import Any

from litcritic.workspace import repo_root

CATALOGUE = repo_root() / "docs" / "codex" / "question-catalogue.toml"
# Families the Codex spec requires (criterion question_catalogue_expressible).
REQUIRED_FAMILIES = {
    "structure",
    "characters",
    "relationships",
    "threads",
    "time",
    "dialogue",
    "style",
    "lexicon",
    "rhythm_density",
    "mechanics",
}


def load() -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = tomllib.loads(CATALOGUE.read_text(encoding="utf-8"))[
        "question"
    ]
    return questions


def test_catalogue_loads_and_covers_families() -> None:
    questions = load()
    assert len(questions) >= 60
    assert {q["family"] for q in questions} >= REQUIRED_FAMILIES
    ids = [q["id"] for q in questions]
    assert len(ids) == len(set(ids))
    for q in questions:
        assert q["text"].strip() and q["needs"], q["id"]
