import json
import re
import shutil
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


WORD_CODES = {"^p": "\r", "^t": "\t", "^s": "\u00a0", "^~": "\u2011", "^-": "\u00ad", "^^": "^"}


def _typed(find: str) -> str:
    """A Find-box string back to the document's characters (``^p`` a paragraph mark)."""
    return re.sub(r"\^[pts~\-^]", lambda m: WORD_CODES[m.group()], find)


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
    checked = phrases = finds = no_find_unrepeated = 0
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
        if not loc.find and ix.paragraphs.count(ix.paragraphs[ix.anchors.index(a)]) == 1:
            no_find_unrepeated += 1
        if loc.find:
            finds += 1
            met = _occurrences(haystack, _typed(loc.find).casefold())
            if met != 1:
                bad.append(f"{a} find met {met} times")
    return {
        "paragraphs": checked,
        "phrases": phrases,
        "finds": finds,
        "no_find_phrase": checked - finds,
        "no_find_phrase_unrepeated": no_find_unrepeated,
        "locators_not_unique": len(bad),
        "bad": bad,
    }


NO_FIND_PHRASE = {"jekyll-hyde": 0, "marianela": 11}  # 11 short repeated replies


def test_locator_phrase_unique_in_document(tmp_path: Path) -> None:
    for name in ("jekyll-hyde", "marianela"):
        lang = "es" if name == "marianela" else "en"
        found = locators_not_unique(_workspace(tmp_path / name, corpus.get(name).path, lang))
        assert found["paragraphs"] > 300 and found["phrases"] > 0.95 * found["paragraphs"]
        # Only paragraphs that repeat another word for word lack a Find phrase (doc-control
        # tries no phrase across a paragraph mark for them).
        assert found["no_find_phrase_unrepeated"] == 0, name
        assert found["no_find_phrase"] == NO_FIND_PHRASE[name], found["no_find_phrase"]
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


def test_cli_prints_utf8_whatever_the_platform(ws: Path) -> None:
    """A pipe on Windows defaults to the ANSI code page; `lc` prints UTF-8 anyway."""
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    run = "import sys; from litcritic.cli import main; sys.exit(main(sys.argv[1:]))"
    done = subprocess.run(
        [sys.executable, "-c", run, "locate", "c02.s1.p3", "--workspace", str(ws)],
        capture_output=True,
        env=env,
        check=True,
    )
    assert done.stdout.decode("utf-8").startswith("Capítulo 2")


def test_cli_locate_needs_a_draft_read_by_doc_control(
    ws: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    other = tmp_path / "old"
    other.mkdir()
    for sub in ("text", "index"):
        shutil.copytree(ws / sub, other / sub)
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


def test_one_by_one_locators_match_whole_document(ws: Path) -> None:
    """A single-anchor command asks doc-control for its paragraph alone: same locator."""
    ix, batch = _locations(ws)
    for a in ix.anchors[::25] + ix.anchors[:3]:
        alone = locate.Locations.of_workspace(ws, "v001", ix, "es", few=True)
        assert alone.locate(a) == batch.locate(a), a
        assert alone._rows is None  # the whole document's rows were never read


def test_single_anchor_locate_is_fast_on_a_long_novel(tmp_path: Path) -> None:
    """`lc docx locate` and `lc locate` on a ~100k-word .docx, as a cold process."""
    import os
    import subprocess
    import sys
    import time

    import test_ingest

    folder = tmp_path / "Novel"
    source = folder / "novel.docx"
    folder.mkdir()
    source.write_bytes(test_ingest._novel_docx(100_000))
    root = _workspace(folder / "literary-critic", source)
    ix = query.load(root)
    anchor = ix.anchors[len(ix.anchors) // 2]
    expected = locate.Locations.of_workspace(root, "v001", ix, "es").locate(anchor)
    run = "import sys; from litcritic.cli import main; sys.exit(main(sys.argv[1:]))"
    for cmd in (["docx", "locate", anchor], ["locate", anchor, "--json"]):
        start = time.perf_counter()
        done = subprocess.run(
            [sys.executable, "-c", run, *cmd, "--workspace", str(root)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        elapsed = time.perf_counter() - start
        out = json.loads(done.stdout)
        where = out["locator"] if cmd[0] == "docx" else out
        assert where["anchor"] == anchor and where["first_words"] == expected.first_words
        limit = 2.5 * float(os.environ.get("LITCRITIC_PERF_FACTOR", "1"))
        assert elapsed <= limit, f"single_anchor_locate_s = {elapsed:.2f} ({cmd[0]})"
