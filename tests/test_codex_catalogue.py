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


# Answers the fixture can check exactly (it has characters, dialogue, threads,
# setups and issues; no scene cards, facts or places with scenes).
def _rows(v: view.View, qid: str) -> list[tuple[object, ...]]:
    q = next(e for e in load() if e["id"] == qid)
    return v.run(q["sql"])[1]


def test_catalogue_answers_on_fixture(fixture_view: view.View) -> None:
    v = fixture_view
    total = v.run("SELECT SUM(words) FROM paragraphs")[1][0][0]
    assert sum(int(str(r[2])) for r in _rows(v, "structure-03")) == total
    openers = dict(_rows(v, "mechanics-02"))
    assert max(openers, key=lambda k: int(str(openers[k]))) == "--" and len(openers) <= 3
    lone = {r[0] for r in _rows(v, "threads-06")}
    named = {r[0] for r in v.run(questions.load()["setups-without-payoff"].sql)[1]}
    assert lone == named and lone
    flagged = _rows(v, "dialogue-03")
    covered = v.run("SELECT COUNT(*) FROM v_dialogue")[1][0][0]
    assert 0 < len(flagged) < 900 - int(str(covered)) and all(
        ".s0." not in str(r[0]) for r in flagged
    )
    by_chapter = {r[0]: r[1] for r in _rows(v, "issues_progress-06")}
    assert sum(int(str(n)) for n in by_chapter.values()) == 2  # rejected issue left out
    assert all(int(str(r[1])) <= 2 for r in _rows(v, "characters-04"))
