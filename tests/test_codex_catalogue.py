import tomllib
from typing import Any

import pytest
from codex_fixture import build

from litcritic import questions, view
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


@pytest.fixture(scope="module")
def fixture_view(tmp_path_factory: pytest.TempPathFactory) -> view.View:
    root = tmp_path_factory.mktemp("marianela")
    build(root)
    return view.View(root)


def test_catalogue_sql_runs_on_fixture(fixture_view: view.View) -> None:
    named = questions.load()
    entries = load()
    expressible = 0
    for q in entries:
        if "missing" in q:
            assert q["missing"].strip() and "sql" not in q and "question" not in q, q["id"]
            continue
        if "question" in q:
            cols, _ = questions.ask(fixture_view, named[q["question"]], dict(q.get("params", {})))
        else:
            cols, _ = fixture_view.run(q["sql"])
        assert cols, q["id"]
        expressible += 1
    assert expressible / len(entries) >= 0.9, expressible
