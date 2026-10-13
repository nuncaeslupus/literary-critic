import json
import re
import time
from itertools import pairwise
from pathlib import Path

import docgen
import pytest

from litcritic import corpus, dc, ingest
from litcritic.cli import main

DOCX = Path("draft.docx")  # names for bytes read through doc-control
TXT = Path("draft.txt")
MD = Path("draft.md")

CHAPTER = re.compile(r"^-[IVXL]+-$")


def _twin() -> tuple[list[str], list[tuple[str, bool]]]:
    """Marianela as ingested from its .txt, and the same paragraphs for a .docx/.odt."""
    txt = ingest.read(corpus.get("marianela").path)
    texts = [p.text for p in txt.paragraphs]
    return texts, [(t, bool(CHAPTER.match(t))) for t in texts]


def _fidelity(expected: list[str], got: list[str]) -> float:
    same = sum(a == b for a, b in zip(expected, got, strict=False))
    return same / max(len(expected), len(got))


def test_docx_paragraphs_match_text() -> None:
    texts, paras = _twin()
    draft = ingest.read(DOCX, docgen.docx(paras, seed=1))
    got = [p.text for p in draft.paragraphs]
    assert _fidelity(texts, got) >= 0.999
    assert got == texts
    headings = [p for p in draft.paragraphs if p.heading]
    assert len(headings) == 22
    assert all(p.heading == 1 and p.centered and p.page_break_before for p in headings)
    # Pages are doc-control's estimate: rendered marks (here only the break
    # before each heading) and a word-count model between them, so every
    # heading opens a new page and pages never go back.
    pages = [p.page for p in draft.paragraphs]
    hpages = [p.page for p in headings]
    assert draft.pages_known and pages == sorted(pages)
    assert all(b > a for a, b in pairwise(hpages))
    assert hpages[-1] >= len(headings) + 1
    assert all(
        p.blank_before == 1
        for i, p in enumerate(draft.paragraphs[1:])
        if draft.paragraphs[i].heading
    )


def test_odt_paragraphs_match_text() -> None:
    texts, paras = _twin()
    draft = ingest.read(Path("x.odt"), docgen.odt(paras, seed=2))
    assert [p.text for p in draft.paragraphs] == texts
    headings = [p for p in draft.paragraphs if p.heading]
    assert len(headings) == 22 and all(p.centered for p in headings)
    assert draft.pages_known and headings[0].page == 2


def test_txt_modes() -> None:
    text = (
        b"One line that was wrapped by the editor at a fixed\nwidth.\n\n\n\n"
        b"Two lines that were also wrapped at that same\nwidth.\n"
    )
    wrapped = ingest.read(TXT, text)
    assert [p.text for p in wrapped.paragraphs] == [
        "One line that was wrapped by the editor at a fixed width.",
        "Two lines that were also wrapped at that same width.",
    ]
    assert wrapped.paragraphs[1].blank_before == 2
    assert wrapped.notes == ["hard-wrapped blocks"] and wrapped.source["mode"] == "blocks"
    # No empty line between two lines: every line is a paragraph (doc-control's lines mode).
    per_line = ingest.read(TXT, "Uno.\r\nDos.\r\nTres é.".encode("cp1252"))
    assert [(p.text, p.blank_before) for p in per_line.paragraphs] == [
        ("Uno.", 0),
        ("Dos.", 0),
        ("Tres é.", 0),
    ]
    assert per_line.source == {"format": "txt", "encoding": "cp1252", "mode": "lines"}
    assert per_line.notes == ["encoding: cp1252"]


def test_markdown() -> None:
    draft = ingest.read(
        MD,
        b"---\ntitle: x\n---\n# Chapter *One*\n\nShe said *no*\nand **left**.\n\n* * *\n\n"
        b"A \\*star\\*.",
    )
    assert [(p.text, p.heading) for p in draft.paragraphs] == [
        ("Chapter One", 1),
        ("She said no and left.", 0),
        ("* * *", 0),
        ("A *star*.", 0),
    ]


def test_clean_normalises() -> None:
    assert ingest.clean("Cafe\u0301\u00a0 con\u00adtigo\u200b\tya ") == "Caf\u00e9 contigo ya"


def test_bad_files(tmp_path: Path) -> None:
    with pytest.raises(ingest.IngestError):
        ingest.read(DOCX, b"not a zip")
    bad = tmp_path / "x.pdf"
    bad.write_bytes(b"%PDF")
    with pytest.raises(ingest.IngestError, match="unsupported"):
        ingest.read(bad)


def test_ingest_snapshots_and_skips_unchanged(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    _, paras = _twin()
    src = tmp_path / "draft.docx"
    src.write_bytes(docgen.docx(paras[:50]))
    first = ingest.ingest(src, ws)
    assert (first.version, first.unchanged, first.paragraphs) == ("v001", False, 50)
    assert (ws / "manuscript" / "v001.docx").read_bytes() == src.read_bytes()
    meta = json.loads((ws / "text" / "v001.meta.json").read_text(encoding="utf-8"))
    assert meta["format"] == "docx" and len(meta["paragraphs"]) == 50
    assert ingest.ingest(src, ws).unchanged
    src.write_bytes(docgen.docx(paras[:60]))
    assert ingest.ingest(src, ws).version == "v002"
    lines = (ws / "text" / "v002.txt").read_text(encoding="utf-8").split("\n")
    assert lines[-1] == "" and len(lines) == 61


def test_cli_ingest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ws = tmp_path / "ws"
    (ws).mkdir()
    (ws / "work.toml").write_text('slug = "ws"\n', encoding="utf-8")
    assert main(["ingest", str(corpus.get("jekyll-hyde").path), "--workspace", str(ws)]) == 0
    assert "v001" in capsys.readouterr().out
    assert main(["ingest", str(tmp_path / "missing.txt"), "--workspace", str(ws)]) == 2


def test_docx_explicit_and_rendered_page_breaks() -> None:
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = (
        '<w:p><w:r><w:t>Uno.</w:t></w:r><w:r><w:br w:type="page"/></w:r></w:p>'
        "<w:p><w:r><w:lastRenderedPageBreak/><w:t>Dos.</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Tres</w:t></w:r>"
        "<w:r><w:lastRenderedPageBreak/><w:t> sigue.</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Cuatro.</w:t></w:r></w:p>"
    )
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", docgen.CT)
        zf.writestr("word/document.xml", f"<w:document {w}><w:body>{body}</w:body></w:document>")
    paras = ingest.read(DOCX, buf.getvalue()).paragraphs
    assert [(p.page, p.page_break_before) for p in paras] == [
        (1, False),
        (2, True),  # explicit break: marked, counted once
        (2, False),  # page turns mid-paragraph: it starts on page 2
        (3, False),  # natural page flow is not a "break"
    ]


def test_review_regressions(tmp_path: Path) -> None:
    # UTF-16 with BOM decodes; without BOM it is refused rather than garbled.
    assert [p.text for p in ingest.read(TXT, "Hola mundo.\n".encode("utf-16")).paragraphs] == [
        "Hola mundo."
    ]
    with pytest.raises(ingest.IngestError, match="UTF-16"):
        ingest.read(TXT, "Hola mundo.".encode("utf-16-le"))
    # A Markdown heading directly followed by text keeps its level.
    md = ingest.read(MD, b"# Chapter One\nShe left.\n\nThen more.")
    assert [(p.text, p.heading) for p in md.paragraphs] == [
        ("Chapter One", 1),
        ("She left.", 0),
        ("Then more.", 0),
    ]
    # Hard-wrapped, dialogue-heavy text stays in block mode.
    lines = ["Short line.\n\n"] * 7 + [
        "A wrapped line that goes on and on, cut at a fixed\nwidth by the editor.\n\n"
    ] * 3
    assert len(ingest.read(TXT, "".join(lines).encode()).paragraphs) == 10
    # A gap in version numbers never overwrites an existing snapshot.
    ws = tmp_path / "ws"
    (ws / "manuscript").mkdir(parents=True)
    (ws / "manuscript" / "v001.txt").write_text("old one", encoding="utf-8")
    (ws / "manuscript" / "v003.txt").write_text("old three", encoding="utf-8")
    src = tmp_path / "new.txt"
    src.write_text("New text.", encoding="utf-8")
    assert ingest.ingest(src, ws).version == "v004"
    assert (ws / "manuscript" / "v003.txt").read_text(encoding="utf-8") == "old three"
    # A run interrupted after the snapshot is completed next time.
    (ws / "text" / "v004.meta.json").unlink()
    again = ingest.ingest(src, ws)
    assert (again.version, again.unchanged) == ("v004", False)
    assert (ws / "text" / "v004.meta.json").is_file()
    # Corrupt XML inside a docx is a readable error, not a traceback.
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<w:document")
    bad = tmp_path / "bad.docx"
    bad.write_bytes(buf.getvalue())
    with pytest.raises(ingest.IngestError):
        ingest.read(bad)


def test_workspace_inside_repo_is_refused(tmp_path: Path) -> None:
    from litcritic import workspace
    from litcritic.workspace import repo_root

    inside = repo_root() / "tmp" / "ws-test-inside"
    inside.mkdir(parents=True, exist_ok=True)
    (inside / "work.toml").write_text('slug = "x"\n', encoding="utf-8")
    try:
        with pytest.raises(workspace.WorkspaceError):
            workspace.resolve(str(inside))
    finally:
        (inside / "work.toml").unlink()
        inside.rmdir()


def _novel_docx(words: int) -> bytes:
    """A generated .docx of at least ``words`` words: Marianela's paragraphs, repeated."""
    _, paras = _twin()
    out: list[tuple[str, bool]] = []
    count = 0
    while count < words:
        for text, heading in paras:
            out.append((text, heading))
            count += len(text.split())
            if count >= words:
                break
    return docgen.docx(out, seed=9)


def test_ingest_100k_words_under_budget(tmp_path: Path) -> None:
    src = tmp_path / "novel.docx"
    src.write_bytes(_novel_docx(100_000))
    dc.check()  # doc-control's import and version check are paid once per process
    start = time.perf_counter()
    result = ingest.ingest(src, tmp_path / "ws")
    elapsed = time.perf_counter() - start
    meta = json.loads((tmp_path / "ws" / "text" / "v001.meta.json").read_text(encoding="utf-8"))
    assert meta["words"] >= 100_000 and result.paragraphs == len(meta["paragraphs"])
    assert elapsed <= 3.0, f"ingest_100k_words_s = {elapsed:.2f}"


def test_meta_paragraphs_carry_addresses(tmp_path: Path) -> None:
    _, paras = _twin()
    src = tmp_path / "draft.docx"
    src.write_bytes(docgen.docx(paras[:120], seed=3))
    ingest.ingest(src, tmp_path / "ws")
    meta = json.loads((tmp_path / "ws" / "text" / "v001.meta.json").read_text(encoding="utf-8"))
    lines = (tmp_path / "ws" / "text" / "v001.txt").read_text(encoding="utf-8").split("\n")[:-1]
    assert meta["schema_version"] == 2 and len(meta["paragraphs"]) == len(lines) == 120
    assert all("src" not in m for m in meta["paragraphs"])
    for m, line in zip(meta["paragraphs"], lines, strict=True):
        got = dc.run("para.get", {"doc": str(src), "at": m["at"]})
        assert got["at"] == m["at"] and ingest.clean(got["text"]) == line
