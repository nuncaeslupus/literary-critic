import json
from pathlib import Path

import pytest

from litcritic import corpus, locate, query, rounds
from litcritic.cli import main


@pytest.fixture(scope="module")
def ws(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("ws")
    (root / "work.toml").write_text('slug = "ws"\nlanguage = "es"\n', encoding="utf-8")
    assert main(["ingest", str(corpus.get("marianela").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    return root


def writer_locators_complete(ix: query.Index) -> float:
    builder = locate.LocatorBuilder(ix)
    text = "\n".join(ix.paragraphs)
    complete = 0
    sample = [a for a in ix.anchors if len(ix.paragraphs[ix.anchors.index(a)].split()) >= 8][::5]
    for a in sample:
        loc = builder.locate(a)
        ok = (
            loc.chapter
            and loc.page > 0
            and text.count(loc.first_words) == 1
            and text.count(loc.last_words) == 1
            and ix.paragraphs[ix.anchors.index(a)].startswith(loc.first_words)
            and ix.paragraphs[ix.anchors.index(a)].endswith(loc.last_words)
        )
        complete += bool(ok)
    return complete / len(sample)


def test_locator_first_last_words_unique(ws: Path) -> None:
    assert writer_locators_complete(query.load(ws)) == 1.0


def test_describe_and_pages(ws: Path) -> None:
    ix = query.load(ws)
    loc = locate.LocatorBuilder(ix).locate("c03.s1.p2")
    assert loc.chapter.startswith("3 (-III-") and loc.page > 1 and not loc.page_exact
    line = locate.describe(loc, "es")
    assert line.startswith("Capítulo 3") and "pág. ≈" in line and "«" in line
    assert locate.describe(loc, "en").startswith("Chapter 3")
    meta = [{"page": 7} for _ in ix.paragraphs]
    assert locate.LocatorBuilder(ix, meta).locate("c03.s1.p2").page == 7


def test_prose_in_actions_is_flagged() -> None:
    long_quote = "«" + " ".join(["palabra"] * 20) + "»"
    action = {"id": "A1", "what": "x", "why": f"Write it like {long_quote}", "options": []}
    assert rounds.prose_flags(action, "texto del libro")
    assert not rounds.prose_flags(action, " ".join(["palabra"] * 20))


def test_cli_locate(ws: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["locate", "c02.s1.p3", "--workspace", str(ws)]) == 0
    assert capsys.readouterr().out.startswith("Capítulo 2")
    assert main(["locate", "c02.s1.p3", "--workspace", str(ws), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["anchor"] == "c02.s1.p3"


def test_short_paragraph_points_to_its_neighbour() -> None:
    ix = query.Index(
        ["Una frase larga y única para empezar aquí.", "—Sí.", "Otra cosa distinta.", "—Sí."],
        ["c01.s1.p1", "c01.s1.p2", "c01.s1.p3", "c01.s1.p4"],
        ["a", "b", "c", "d"],
        [],
        {},
        {},
    )
    loc = locate.LocatorBuilder(ix).locate("c01.s1.p4")
    assert not loc.unique and loc.after == "Otra cosa distinta."
    assert "justo después del que empieza «Otra cosa distinta.…»" in locate.describe(loc, "es")


def test_spanish_locator_labels(ws: Path) -> None:
    ix = query.load(ws)
    assert locate.LocatorBuilder(ix, lang="es").locate("c00.s1.p1").chapter == "preliminares"
