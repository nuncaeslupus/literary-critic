import json
from pathlib import Path
from typing import Any

import pytest
from docgen import docx

from litcritic import corpus, dc, ingest, locate, query, rounds
from litcritic.cli import main


def _workspace(root: Path, source: Path, lang: str = "es") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "work.toml").write_text(f'slug = "ws"\nlanguage = "{lang}"\n', encoding="utf-8")
    assert main(["ingest", str(source), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    return root


@pytest.fixture(scope="module")
def ws(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _workspace(tmp_path_factory.mktemp("ws"), corpus.get("marianela").path)


def _locations(root: Path, lang: str = "es") -> tuple[query.Index, locate.Locations]:
    ix = query.load(root)
    return ix, locate.Locations.of_workspace(root, "v001", ix, lang)


def _document_texts(root: Path) -> list[str]:
    """Every paragraph of the draft's document, as doc-control reads it."""
    snapshot = next((root / "manuscript").glob("v001.*"))
    with ingest.readable(snapshot) as path, dc.open(path) as doc:
        return [str(p.get("text", "")) for p in doc.paragraphs()]


def _occurrences(haystack: str, needle: str) -> int:
    """Occurrences of ``needle``, overlapping ones included (as Word's Find counts them)."""
    count, at = 0, haystack.find(needle)
    while at >= 0:
        count += 1
        at = haystack.find(needle, at + 1)
    return count


def locators_not_unique(root: Path) -> dict[str, Any]:
    """Locators of every paragraph whose head … tail or Find string is not met once.

    A head … tail is met by a paragraph that starts with the head's words and ends
    with the tail's (ignoring case, as Word does); a Find string by each place the
    document's text holds it (paragraph marks included, any case).
    """
    ix, locs = _locations(root)
    texts = _document_texts(root)
    words = [ingest.clean(t).casefold().split() for t in texts]
    haystack = "\r".join(t.casefold() for t in texts)
    checked = phrases = finds = 0
    bad: list[str] = []
    for a in ix.anchors:
        loc = locs.locate(a)
        checked += 1
        if loc.unique:
            phrases += 1
            head, tail = loc.first_words.casefold().split(), loc.last_words.casefold().split()
            met = sum(
                1 for w in words if w[: len(head)] == head and w[len(w) - len(tail) :] == tail
            )
            if met != 1:
                bad.append(f"{a} phrase met {met} times")
        else:
            assert loc.after or a == ix.anchors[0]
        if loc.find:
            finds += 1
            met = _occurrences(haystack, loc.find.casefold())
            if met != 1:
                bad.append(f"{a} find met {met} times")
    return {
        "paragraphs": checked,
        "phrases": phrases,
        "finds": finds,
        "locators_not_unique": len(bad),
        "bad": bad,
    }


def test_locator_phrase_unique_in_document(tmp_path: Path) -> None:
    for name in ("jekyll-hyde", "marianela"):
        lang = "es" if name == "marianela" else "en"
        found = locators_not_unique(_workspace(tmp_path / name, corpus.get(name).path, lang))
        assert found["paragraphs"] > 300 and found["phrases"] > 0.95 * found["paragraphs"]
        assert found["finds"] > 0.95 * found["paragraphs"]
        assert found["locators_not_unique"] == 0, found["bad"][:5]


def test_locator_shows_at_least_four_words_a_side(ws: Path) -> None:
    ix, locs = _locations(ws)
    long = [a for a, p in zip(ix.anchors, ix.paragraphs, strict=True) if len(p.split()) >= 8]
    for a in long[::40]:
        loc = locs.locate(a)
        text = ix.paragraphs[ix.anchors.index(a)]
        assert loc.unique and text.startswith(loc.first_words) and text.endswith(loc.last_words)
        assert len(loc.first_words.split()) >= 4 and len(loc.last_words.split()) >= 4


def test_describe_and_pages(ws: Path) -> None:
    _, locs = _locations(ws)
    loc = locs.locate("c03.s1.p2")
    assert loc.chapter.startswith("3 (-III-") and loc.page > 1 and not loc.page_exact
    line = locate.describe(loc, "es")
    assert line.startswith("Capítulo 3") and "pág. ≈" in line and "«" in line
    assert locate.describe(loc, "en").startswith("Chapter 3")
    assert loc.find and locate.from_where(loc.as_where()).find == loc.find


def test_pages_word_laid_out_are_exact(tmp_path: Path) -> None:
    body = " ".join(["Palabra"] * 30) + "."
    paras: list[tuple[str, bool]] = []
    for n in ("I", "II", "III"):
        paras += [(f"Capítulo {n}", True)] + [(f"{body} Párrafo {n}{k}.", False) for k in range(3)]
    source = tmp_path / "novela.docx"
    source.write_bytes(docx(paras, seed=1))
    ix, locs = _locations(_workspace(tmp_path / "ws", source))
    heading = next(a for a, p in zip(ix.anchors, ix.paragraphs, strict=True) if p == "Capítulo III")
    loc = locs.locate(heading)
    assert loc.page_exact and loc.page == 3
    assert "pág. 3:" in locate.describe(loc, "es")


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


def test_cli_locate_needs_a_draft_read_by_doc_control(
    ws: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    other = tmp_path / "old"
    other.mkdir()
    for sub in ("text", "index"):
        (other / sub).symlink_to(ws / sub)
    (other / "work.toml").write_text((ws / "work.toml").read_text(encoding="utf-8"))
    assert main(["locate", "c02.s1.p3", "--workspace", str(other)]) == 2
    assert "snapshot" in capsys.readouterr().err


def test_repeated_paragraph_points_to_its_neighbour(tmp_path: Path) -> None:
    texts = ["Una frase larga y única para empezar aquí.", "—Sí.", "Otra cosa distinta.", "—Sí."]
    source = tmp_path / "novela.docx"
    source.write_bytes(docx([(t, False) for t in texts], seed=2))
    ix, locs = _locations(_workspace(tmp_path / "ws", source))
    loc = locs.locate(ix.anchors[3])
    assert not loc.unique and loc.after == "Otra cosa distinta." and loc.first_words == "—Sí."
    assert "justo después del que empieza «Otra cosa distinta.…»" in locate.describe(loc, "es")
    assert locs.locate(ix.anchors[2]).unique


def test_spanish_locator_labels(ws: Path) -> None:
    _, locs = _locations(ws)
    assert locs.locate("c00.s1.p1").chapter == "preliminares"
