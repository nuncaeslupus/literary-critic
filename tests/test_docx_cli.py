import argparse
import io
import json
import os
import random
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest
from docgen import CT, docx

from litcritic import corpus, dc, docx_cli, ingest
from litcritic.cli import main

DOCX = Path("draft.docx")  # a name for bytes read through doc-control

AUTHOR = docx_cli.AUTHOR


def _corpus_docx(n: int | None = None) -> bytes:
    draft = ingest.read(corpus.get("marianela").path)
    paras = [(p.text, bool(re.fullmatch(r"-[IVXL]+-", p.text))) for p in draft.paragraphs]
    return docx(paras[:n] if n else paras, seed=4)


def _corpus_paragraphs(n: int = 80) -> list[tuple[str, bool]]:
    text = corpus.get("marianela").path.read_text(encoding="utf-8")
    paras = [ingest.clean(p) for p in text.split("\n\n") if len(ingest.clean(p)) > 60]
    return [(p, False) for p in paras[:n]]


def _plain(*paras: str) -> bytes:
    """A .docx with one plain run per paragraph (no markup quirks)."""
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{p}</w:t></w:r></w:p>' for p in paras)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", CT)
        zf.writestr("word/document.xml", f"<w:document {w}><w:body>{body}</w:body></w:document>")
    return buf.getvalue()


def _members(data: bytes) -> dict[str, bytes]:
    zf = zipfile.ZipFile(io.BytesIO(data))
    return {n: zf.read(n) for n in zf.namelist()}


def _texts(data: bytes) -> list[str]:
    """What the writer reads, paragraph by paragraph (tracked changes shown)."""
    return [p.text for p in ingest.read(DOCX, data).paragraphs]


def _paragraph_xml(data: bytes) -> list[str]:
    xml = _members(data)["word/document.xml"].decode("utf-8")
    return re.findall(r"<w:p>.*?</w:p>|<w:p/>|<w:p\s[^>]*>.*?</w:p>", xml, flags=re.S)


def _workspace(tmp_path: Path, data: bytes, anchor: bool = False) -> tuple[Path, Path]:
    folder = tmp_path / "MyNovel"
    ws = folder / "literary-critic"
    ws.mkdir(parents=True)
    (ws / "work.toml").write_text('slug = "mynovel"\nlanguage = "es"\n', encoding="utf-8")
    doc = folder / "MyNovel_v3.docx"
    doc.write_bytes(data)
    assert main(["ingest", str(doc), "--workspace", str(ws)]) == 0
    if anchor:
        assert main(["anchor", "--workspace", str(ws)]) == 0
    return ws, doc


@pytest.fixture()
def novel(tmp_path: Path) -> tuple[Path, Path]:
    return _workspace(tmp_path, _corpus_docx(120), anchor=True)


def _lc(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any]]:
    capsys.readouterr()
    code = main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def _edits(
    capsys: pytest.CaptureFixture[str], ws: Path, edits: list[dict[str, str]], *flags: str
) -> tuple[int, dict[str, Any]]:
    f = ws.parent / "edits.json"
    f.write_text(json.dumps({"edits": edits}), encoding="utf-8")
    return _lc(capsys, "docx", "edits", "--edits", str(f), "--workspace", str(ws), *flags)


def _once(doc: Path, quote: str) -> bool:
    req = {"doc": str(doc), "anchor": {"exact": quote}, "mode": "exact"}
    try:
        dc.run("anchor.resolve", req)
    except dc.DocError:
        return False
    return True


def _quote(doc: Path, min_words: int = 12) -> str:
    """A phrase found once in the document, from a long paragraph."""
    for t in _texts(doc.read_bytes()):
        words = t.split()
        if len(words) >= min_words:
            phrase = " ".join(words[3:9])
            if _once(doc, phrase):
                return phrase
    raise AssertionError("no unique phrase")


def _plan(
    capsys: pytest.CaptureFixture[str], ws: Path, doc: Path, rng: random.Random, k: int
) -> list[tuple[dict[str, str], int, str]]:
    """k edits on distinct paragraphs, each quote verbatim once in the document."""
    texts = _texts(doc.read_bytes())
    whole = "\n".join(texts)
    plans: list[tuple[dict[str, str], int, str]] = []
    for i in rng.sample(range(len(texts)), len(texts)):
        words = texts[i].split()
        if len(words) < 8:
            continue
        a = rng.randrange(0, len(words) - 4)
        quote = " ".join(words[a : a + 4])
        if whole.count(quote) != 1 or not _once(doc, quote):
            continue  # a quote across a soft hyphen is not verbatim in the document
        repl = quote.upper() + " <&> nuevo"
        edit = {"id": f"E{len(plans)}", "quote": quote, "replace": repl}
        code, _ = _edits(capsys, ws, [edit], "--dry-run")
        if code != 0:  # passages across a note mark or an old tracked change are refused
            continue
        plans.append((edit, i, texts[i].replace(quote, repl, 1)))
        if len(plans) == k:
            break
    return plans


def test_edits_change_only_target_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    unintended = 0
    for seed in range(6):
        ws, doc = _workspace(tmp_path / str(seed), docx(_corpus_paragraphs(), seed=seed))
        data = doc.read_bytes()
        before = _texts(data)
        plans = _plan(capsys, ws, doc, random.Random(seed), 6)
        assert len(plans) == 6
        code, out = _edits(capsys, ws, [e for e, _, _ in plans])
        assert code == 0 and out["status"] == "applied" and out["revisions"] == 6
        new = doc.read_bytes()
        after = _texts(new)
        assert len(after) == len(before)
        edited = {i: want for _, i, want in plans}
        for i, (old, now) in enumerate(zip(before, after, strict=True)):
            unintended += now != edited.get(i, old)
        a, b = _members(data), _members(new)
        assert a.keys() == b.keys()
        unintended += sum(a[n] != b[n] for n in a if n != "word/document.xml")
        # Outside the edited paragraphs, every paragraph's XML is byte-identical.
        xa, xb = _paragraph_xml(data), _paragraph_xml(new)
        assert len(xa) == len(xb)
        changed = {i for i, (x, y) in enumerate(zip(xa, xb, strict=True)) if x != y}
        unintended += len(changed) != len(edited)
    unintended_docx_changes = unintended
    assert unintended_docx_changes == 0


def _reject_all(data: bytes) -> list[str]:
    """What Word shows after "Reject all changes": insertions gone, deletions back."""
    xml = _members(data)["word/document.xml"].decode("utf-8")
    xml = re.sub(rf'<w:ins\b[^>]*\bw:author="{AUTHOR}"[^>]*>.*?</w:ins>', "", xml, flags=re.S)
    xml = re.sub(rf'<w:del\b[^>]*\bw:author="{AUTHOR}"[^>]*>(.*?)</w:del>', r"\1", xml, flags=re.S)
    xml = re.sub(r"<w:delText\b", "<w:t", xml).replace("</w:delText>", "</w:t>")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, payload in _members(data).items():
            zf.writestr(name, xml.encode("utf-8") if name == "word/document.xml" else payload)
    return _texts(out.getvalue())


def test_edits_are_plain_writes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ws, doc = _workspace(tmp_path, _plain(*(t for t, _ in _corpus_paragraphs(8))))
    data = doc.read_bytes()
    plans = _plan(capsys, ws, doc, random.Random(11), 5)
    code, out = _edits(capsys, ws, [e for e, _, _ in plans])
    assert code == 0 and out["author"] == AUTHOR
    xml = _members(doc.read_bytes())["word/document.xml"].decode()
    assert not re.findall(r"<w:(?:ins|del)[ >]", xml)  # no revision marks
    after = _texts(doc.read_bytes())
    for _, i, want in plans:
        assert after[i] == want
    listed = dc.run("revision.list", {"doc": str(doc), "author": AUTHOR})
    assert listed["revisions"] == []
    assert main(["docx", "undo", "--workspace", str(ws)]) == 0
    assert _texts(doc.read_bytes()) == _texts(data)


def test_edit_refused_when_ambiguous_missing_or_overlapping(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, doc = _workspace(tmp_path, _plain("Pablo dijo hola. Pablo dijo adiós.", "Otra cosa."))
    data = doc.read_bytes()

    def refused(edits: list[dict[str, str]]) -> dict[str, str]:
        code, out = _edits(capsys, ws, edits)
        assert code == 1 and out["status"] == "refused" and out["reason"] == "edit"
        assert doc.read_bytes() == data and out["backup"] is None
        return {s["id"]: s["reason"] for s in out["skipped"]}

    assert "2 times" in refused([{"id": "A", "quote": "Pablo dijo", "replace": "Él dijo"}])["A"]
    assert refused([{"id": "B", "quote": "nada de esto", "replace": "x"}])["B"] == "not found"
    overlap = [
        {"id": "C", "quote": "dijo hola", "replace": "x"},
        {"id": "D", "quote": "hola. Pablo", "replace": "y"},
    ]
    assert refused(overlap)["D"] == "overlaps C"
    # Every problem is reported at once, the empty quote included.
    both = refused(
        [{"id": "e", "quote": " ", "replace": "x"}, {"id": "f", "quote": "zz", "replace": "x"}]
    )
    assert both == {"e": "empty quote", "f": "not found"}
    # Context picks the occurrence.
    edit = {"id": "E", "quote": "Pablo dijo", "replace": "Él dijo"}
    code, out = _edits(capsys, ws, [edit | {"prefix": "hola.", "suffix": "adiós"}])
    assert code == 0 and out["applied"] == ["E"]
    assert _texts(doc.read_bytes())[0] == "Pablo dijo hola. Él dijo adiós."


def test_edit_refused_across_a_link_or_note_mark(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = (
        '<w:p><w:r><w:t>end.</w:t></w:r><w:r><w:footnoteReference w:id="1"/></w:r>'
        '<w:r><w:t xml:space="preserve"> Next one.</w:t></w:r></w:p>'
        '<w:p><w:r><w:t xml:space="preserve">Ver </w:t></w:r><w:hyperlink><w:r><w:t>la web'
        '</w:t></w:r></w:hyperlink><w:r><w:t xml:space="preserve"> del autor.</w:t></w:r></w:p>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", CT)
        zf.writestr("word/document.xml", f"<w:document {w}><w:body>{body}</w:body></w:document>")
    ws, doc = _workspace(tmp_path, buf.getvalue())
    data = doc.read_bytes()
    for quote in ("end. Next", "la web", "web del"):
        code, out = _edits(capsys, ws, [{"id": "H", "quote": quote, "replace": "x"}])
        assert code == 1 and out["reason"] == "edit" and "by hand" in out["skipped"][0]["reason"]
        assert doc.read_bytes() == data
    code, out = _edits(capsys, ws, [{"id": "A", "quote": "autor", "replace": "autora"}])
    assert code == 0 and _texts(doc.read_bytes())[1] == "Ver la web del autora."


def test_edit_refused_when_word_has_file_open(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, doc = _workspace(tmp_path, _plain("Ya voy —dijo Pablo con voz cansada.", "Fin."))
    w = ["--workspace", str(ws)]
    assert _edits(capsys, ws, [{"id": "A0", "quote": "Fin.", "replace": "Final."}])[0] == 0
    data = doc.read_bytes()  # an edit that undo could take back
    edit = [{"id": "A1", "quote": "dijo Pablo", "replace": "susurró Pablo"}]
    backups = _lc(capsys, "docx", "status", *w)[1]["backups"]
    refused = 0
    locks = ("~$" + doc.name[2:], "~$" + doc.name)
    for lock in locks:
        (doc.parent / lock).write_text("x")
        assert _lc(capsys, "docx", "status", *w)[1]["locked"]
        for code, out in (
            _edits(capsys, ws, edit),
            _lc(capsys, "docx", "rename", "Pablo", "Pedro", *w),
            _lc(capsys, "docx", "undo", *w),
        ):
            refused += code == 1 and out["status"] == "refused" and out["reason"] == "locked"
        refused += doc.read_bytes() == data
        (doc.parent / lock).unlink()
    assert refused == 4 * len(locks)
    status = _lc(capsys, "docx", "status", *w)[1]
    assert not status["locked"] and status["backups"] == backups
    # Another document's owner file does not lock this one.
    (doc.parent / "~$herNovel.docx").write_text("x")
    assert not _lc(capsys, "docx", "status", *w)[1]["locked"]


def test_edit_applies_after_a_save_in_word_and_refuses_a_never_read_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, doc = _workspace(tmp_path, _plain("Ya voy —dijo Pablo con voz cansada.", "Fin."))
    edit = [{"id": "A1", "quote": "dijo Pablo", "replace": "susurró Pablo"}]
    theirs = _plain("Ya voy —dijo Pablo con voz cansada.", "Lo que el escritor guardó.")
    doc.write_bytes(theirs)  # the writer saved in Word meanwhile
    code, out = _lc(capsys, "docx", "status", "--workspace", str(ws))
    assert code == 0 and out["changed_on_disk"]
    code, out = _edits(capsys, ws, edit)  # the quote is still there once: applied
    assert code == 0 and (ws.parent / out["backup"]).read_bytes() == theirs
    texts = _texts(doc.read_bytes())
    assert any("susurró Pablo" in t for t in texts)
    assert any("Lo que el escritor guardó." in t for t in texts)  # their save is kept
    doc.write_bytes(theirs)
    other = doc.with_name("Other.docx")
    other.write_bytes(theirs)
    code, out = _edits(capsys, ws, edit, "--document", str(other))
    assert code == 1 and out["reason"] == "unread" and other.read_bytes() == theirs


def test_undo_restores_previous_bytes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ws, doc = _workspace(tmp_path, docx(_corpus_paragraphs(30), seed=3))
    data = doc.read_bytes()
    w = ["--workspace", str(ws)]
    quote = _quote(doc)
    code, out = _edits(capsys, ws, [{"id": "A1", "quote": quote, "replace": "otra cosa"}])
    assert code == 0 and doc.read_bytes() != data
    log = [json.loads(x) for x in (ws / "log" / "edits.jsonl").read_text().splitlines()]
    assert log[-1]["edit_ids"] == ["A1"] and log[-1]["op_id"]
    code, out = _lc(capsys, "docx", "undo", "--dry-run", *w)
    assert code == 0 and out["status"] == "dry_run" and doc.read_bytes() != data
    code, out = _lc(capsys, "docx", "undo", *w)
    assert code == 0 and out["status"] == "undone" and out["undid"] == log[-1]["op_id"]
    assert doc.read_bytes() == data and _texts(doc.read_bytes()) == _texts(data)
    code, out = _lc(capsys, "docx", "status", *w)
    assert not out["changed_on_disk"]
    code, out = _lc(capsys, "docx", "undo", *w)
    assert code == 1 and out["reason"] == "nothing" and doc.read_bytes() == data


def test_rename_whole_words_keeps_case_and_lists_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, doc = _workspace(
        tmp_path, _plain("Pablo y Pablito vieron a PABLO.", "pablo no vino; Pablo sí.")
    )
    w = ["--workspace", str(ws)]
    code, out = _lc(capsys, "docx", "rename", "Pablo", "Pedro", "--dry-run", *w)
    assert code == 0 and out["count"] == 2 and [h["text"] for h in out["hits"]] == ["Pablo"] * 2
    code, out = _lc(capsys, "docx", "rename", "pablo", "pedro", "--ignore-case", *w)
    assert code == 0 and out["count"] == 4 and out["skipped"] == []
    assert _texts(doc.read_bytes()) == [
        "Pedro y Pablito vieron a PEDRO.",
        "pedro no vino; Pedro sí.",
    ]
    code, out = _lc(capsys, "docx", "rename", "Ana", "Eva", *w)
    assert code == 1 and "does not appear" in out["message"]
    code, out = _lc(capsys, "docx", "rename", "  ", "x", *w)
    assert code == 1 and "empty" in out["message"]
    # Occurrences inside a link are left alone and listed for the writer.
    linked = (
        '<w:p><w:r><w:t xml:space="preserve">Nela y </w:t></w:r><w:hyperlink><w:r><w:t>Nela'
        '</w:t></w:r></w:hyperlink><w:r><w:t xml:space="preserve"> y Nela.</w:t></w:r></w:p>'
    )
    w_ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", CT)
        zf.writestr(
            "word/document.xml", f"<w:document {w_ns}><w:body>{linked}</w:body></w:document>"
        )
    ws2, doc2 = _workspace(tmp_path / "two", buf.getvalue())
    code, out = _lc(capsys, "docx", "rename", "Nela", "Marta", "--workspace", str(ws2))
    assert code == 0 and out["count"] == 2 and len(out["skipped"]) == 1
    assert "by hand" in out["skipped"][0]["reason"] and out["skipped"][0]["find"]
    assert _texts(doc2.read_bytes()) == ["Marta y Nela y Marta."]


def test_docx_cli_contracts(novel: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    ws, doc = novel
    w = ["--workspace", str(ws)]
    failed: list[int] = []
    checks = 0

    def ck(cond: object) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            failed.append(sys._getframe(1).f_lineno)

    # status
    code, out = _lc(capsys, "docx", "status", *w)
    keys = {"document", "locked", "changed_on_disk", "last_read_sha256", "backups"}
    ck(code == 0 and keys <= out.keys() and out["document"] == doc.name)
    ck(not out["changed_on_disk"] and out["last_read_sha256"] != "")
    # locate, by anchor and by quote
    loc_keys = {"chapter", "page", "first_words", "last_words"}
    code, out = _lc(capsys, "docx", "locate", "c01.s1.p1", *w)
    # a title word found elsewhere too: a Find phrase across its paragraph mark
    ck(code == 0 and len(out["find"]) <= 255 and out["unique"] and "paragraphs_after" not in out)
    ck(out["locator"] is not None and loc_keys <= out["locator"].keys())
    quote = _quote(doc)
    code, out = _lc(capsys, "docx", "locate", quote, *w)
    ck(code == 0 and out["find"].startswith(quote) and out["locator"]["chapter"] != "")
    # a chapter or scene ("take me to chapter 2") lands on its first paragraph
    code, chapter = _lc(capsys, "docx", "locate", "c02", *w)
    code2, scene = _lc(capsys, "docx", "locate", "c02.s1", *w)
    _, first = _lc(capsys, "docx", "locate", "c02.s1.p1", *w)
    n = [int(x["at"][1:].split("#")[0]) for x in (chapter, scene, first)]
    ck(code == code2 == 0 and n[0] <= n[1] <= n[2])  # the chapter's heading comes first
    ck(chapter["locator"]["chapter"] == first["locator"]["chapter"])
    # "take me to chapter 2": the number in its heading, arabic or roman, without `lc show`
    for number in ("2", "II"):
        code, out = _lc(capsys, "docx", "locate", number, *w)
        ck(code == 0 and out["at"] == chapter["at"])
    code, out = _lc(capsys, "docx", "locate", "999", *w)
    ck(code == 1 and out["reason"] == "chapter" and "lc show" in out["message"])
    # edits: dry run, apply, then refused once the quote is gone
    edits = [{"id": "A1", "quote": quote, "replace": quote.upper(), "reason": "test"}]
    before = doc.read_bytes()
    code, out = _edits(capsys, ws, edits, "--dry-run")
    ck(code == 0 and out["status"] == "dry_run" and doc.read_bytes() == before)
    code, out = _edits(capsys, ws, edits)
    keys = {"status", "applied", "skipped", "backup", "revisions", "author"}
    ck(code == 0 and keys <= out.keys() and out["applied"] == ["A1"])
    ck((ws.parent / out["backup"]).read_bytes() == before and out["revisions"] == 1)
    ck(any(quote.upper() in t for t in _texts(doc.read_bytes())))
    code, out = _edits(capsys, ws, edits)
    ck(code == 1 and out["status"] == "refused" and out["skipped"][0]["reason"] == "not found")
    # the tool's own edit leaves the paragraphs one for one: anchors and locators still work
    code, out = _lc(capsys, "docx", "locate", "c01.s1.p1", *w)
    ck(code == 0 and out["locator"] is not None)
    code, out = _lc(capsys, "docx", "locate", quote.upper(), *w)
    ck(code == 0 and out["locator"] is not None)
    # a rename over a paragraph with an old tracked change is refused as `marked`
    code, out = _lc(capsys, "docx", "rename", "Choto", "Perro", "--dry-run", *w)
    ck(code == 1 and out["reason"] == "marked")
    dc.run("doc.batch", {"doc": str(doc), "ops": [{"op": "revision.accept", "all": True}]})
    # a document open in Word is never written
    lock = doc.parent / ("~$" + doc.name[2:])
    lock.write_text("x")
    code, out = _lc(capsys, "docx", "rename", "Choto", "Perro", *w)
    ck(code == 1 and out["reason"] == "locked")
    code, out = _lc(capsys, "docx", "status", *w)
    ck(code == 0 and out["locked"])
    lock.unlink()
    # rename: dry run lists the first hits with locators, then applies
    main(["ingest", str(doc), "--workspace", str(ws)])
    main(["anchor", "--workspace", str(ws)])
    code, out = _lc(capsys, "docx", "rename", "Choto", "Perro", "--dry-run", *w)
    hits = out["hits"]
    ck(code == 0 and out["count"] > 0 and 0 < len(hits) <= 20 and out["backup"] is None)
    ck(all(bool(h["locator"]) and h["text"] == "Choto" for h in hits))
    count = out["count"]
    code, out = _lc(capsys, "docx", "rename", "Choto", "Perro", *w)
    ck(code == 0 and out["count"] == count and bool(out["backup"]))
    text = "\n".join(_texts(doc.read_bytes()))
    ck(not re.search(r"\bChoto\b", text))
    # usage errors exit 2
    (ws.parent / "edits.json").write_text("not json", encoding="utf-8")
    code, out = _lc(capsys, "docx", "edits", "--edits", str(ws.parent / "edits.json"), *w)
    ck(code == 2 and out["status"] == "error")
    code, out = _lc(capsys, "docx", "status", "--document", "missing.docx", *w)
    ck(code == 1 and out["reason"] == "missing")
    (ws.parent / "broken.docx").write_bytes(b"not a zip")
    code, out = _lc(capsys, "docx", "locate", "--document", "broken.docx", "x", *w)
    ck(code == 1 and out["reason"] == "unreadable")
    docx_cli_contract_ok = int(checks == 27 and not failed)
    assert docx_cli_contract_ok == 1, f"failed checks at lines {failed}"


def test_find_string_from_doc_control(tmp_path: Path) -> None:
    ws, doc = _workspace(
        tmp_path, _plain("***", "Uno ^ dos.", "***", "Fin.", "Rose said.", "rose said it.")
    )
    places = docx_cli._Places(ws, doc, doc.read_bytes())
    ats = list(places.rows)
    # A passage met once is typed in the Find box's own ^ codes (doc-control's query_word).
    assert places.find(ats[1] + ":4-5", "^") == {"find": "^^", "unique": True}
    # Otherwise the paragraph's Find phrase from doc-control's locate.
    assert places.find(ats[3], "") == {"find": "Fin.", "unique": True}
    found = places.find(ats[5], "said")  # Word's Find ignores case
    assert found["unique"] and found["find"].lower() not in ("said", "rose said")
    # A paragraph that repeats another gets a phrase across the paragraph mark before it.
    assert places.find(ats[2], "") == {"find": "^p***", "unique": True}


def test_quotes_typed_in_find_box_codes(tmp_path: Path) -> None:
    ws, doc = _workspace(tmp_path, _plain("Uno dos\ttres.", "Rose said it.", "Fin."))
    places = docx_cli._Places(ws, doc, doc.read_bytes())
    ats = list(places.rows)
    assert places.find(ats[0], "Uno dos\ttres") == {"find": "Uno^sdos^ttres", "unique": True}
    assert places.find(ats[1], "Rose said it.") == {"find": "Rose said it.", "unique": True}
    assert places.find(ats[1], "x" * 300)["find"] != "x" * 300  # past the Find box's limit


def test_places_one_by_one_match_whole_document(novel: tuple[Path, Path]) -> None:
    """`lc docx locate` asks for one paragraph and skips reading the document again
    (its bytes are the ingested ones): the same Find string and locator."""
    ws, doc = novel
    data = doc.read_bytes()
    batch = docx_cli._Places(ws, doc, data, "es")
    alone = docx_cli._Places(ws, doc, data, "es", few=True)
    assert alone.ix is not None and batch.ix is not None
    assert alone.locations.ats == batch.locations.ats and alone.by_ordinal == batch.by_ordinal
    for i in range(0, len(alone.ix.anchors), 7):
        at = alone.locations.ats[i]
        assert alone.find(at) == batch.find(at), at
        assert alone.locator(alone.ordinal_of[i]) == batch.locator(batch.ordinal_of[i]), at
    assert alone._rows is None


def test_locators_survive_small_edits_but_not_a_new_draft(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paras = [f"Paragraph number {i} of the story." for i in range(10)]
    assert docx_cli._same_paragraphs(paras, paras)
    edited = [*paras[:8], "Edited one.", "Edited two."]
    assert docx_cli._same_paragraphs(edited, paras)  # 8 of 10 the same
    assert not docx_cli._same_paragraphs([*paras[:7], "a", "b", "c"], paras)
    assert not docx_cli._same_paragraphs([*paras, "added"], paras)

    ws, doc = _workspace(tmp_path, _plain(*paras), anchor=True)
    w = ("--workspace", str(ws))
    doc.write_bytes(_plain(*paras[:9], "A paragraph the writer rewrote."))
    code, out = _lc(capsys, "docx", "locate", "Paragraph number 3", *w)
    assert code == 0 and out["locator"] is not None
    doc.write_bytes(_plain("A new opening.", *paras))  # a paragraph added: a new draft
    code, out = _lc(capsys, "docx", "locate", "Paragraph number 3", *w)
    assert code == 0 and out["locator"] is None


def test_a_read_refused_for_a_moment_is_tried_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = tmp_path / "N.docx"
    doc.write_bytes(b"data")
    monkeypatch.setattr(docx_cli, "READ_PAUSE", 0)
    real, refusals = Path.read_bytes, [PermissionError("saving"), PermissionError("syncing")]

    def flaky(self: Path) -> bytes:
        if refusals:
            raise refusals.pop()
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", flaky)
    assert docx_cli._read(doc) == b"data" and not refusals
    refusals.extend(PermissionError("locked") for _ in range(docx_cli.READ_TRIES))
    with pytest.raises(PermissionError):
        docx_cli._read(doc)


def test_apply_closed_document_opens_word_no_file_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from litcritic import change, folders, mcp, word_live

    p1 = "It was a cold afternoon and nobody left the house."
    ws, doc = _workspace(tmp_path, _plain(p1, "The street stayed empty."))
    before = {p: p.stat().st_mtime_ns for p in doc.parent.iterdir() if p.is_file()}
    opened: list[Path] = []
    batches: list[dict[str, Any]] = []
    monkeypatch.setattr(word_live, "is_open", lambda d: d in opened)

    def open_if_closed(d: Path) -> bool:
        opened.append(d)
        return True

    def run(op: str, request: dict[str, Any]) -> dict[str, Any]:
        assert op == "live.select"
        written = [o["text"] for b in batches for o in b["ops"]]  # read back after the write
        return {"text": p1.replace("cold", written[0]) if written else p1, "at": "p1"}

    read = dc.run

    def file_engine(op: str, request: dict[str, Any]) -> dict[str, Any]:
        assert op != "doc.batch", "the file engine wrote the manuscript"
        return read(op, request)

    monkeypatch.setattr(word_live, "open_if_closed", open_if_closed)
    monkeypatch.setattr(word_live, "run", run)
    monkeypatch.setattr(word_live, "write", batches.append)
    monkeypatch.setattr(dc, "run", file_engine)

    change.propose(ws, "cold", "bitter", by="writer", why="stronger word")
    out, code = change.approve(ws, "C1", word_only=True)
    assert code == 0 and out["status"] == "applied", out
    assert opened == [doc]  # closed: Word opened it, then the edit went in there
    assert batches[0]["ops"] == [{"op": "text.replace", "at": "p1:9-13", "text": "bitter"}]
    after = {p: p.stat().st_mtime_ns for p in doc.parent.iterdir() if p.is_file()}
    assert after == before  # manuscript_file_writes_by_server == 0: nothing beside it

    # Without Word, the card describes the change; the file engine is never the fallback.
    opened.clear()
    monkeypatch.setattr(word_live, "open_if_closed", lambda d: False)
    change.propose(ws, "street", "road", by="writer", why="plainer")
    out, code = change.approve(ws, "C2", word_only=True)
    assert code == 0 and out["status"] == "typed_by_writer" and out["locate"]
    edit = ("E1", "street", "road", "", "")
    refused, code = docx_cli.apply_edits(ws, doc, [edit], word_only=True)
    assert code == 1 and refused["reason"] == "word_needed"

    # The server runs word-only, with doc-control's backups in the app's data folder.
    for name in mcp.SERVER_ENV:  # set first, so teardown removes what _cmd sets
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    monkeypatch.setenv(folders.FOLDERS_ENV, str(tmp_path / "folders.json"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert mcp._cmd(argparse.Namespace(folders=[])) == 0
    assert os.environ["DOC_CONTROL_STORE"] == "appdata"
    assert docx_cli.word_only_env()
