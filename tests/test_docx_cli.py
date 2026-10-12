import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from docgen import docx

from litcritic import corpus, docx_cli, docx_edit, ingest
from litcritic.cli import main


def _corpus_docx(n: int | None = None) -> bytes:
    draft = ingest.read(corpus.get("marianela").path)
    paras = [(p.text, bool(p.heading)) for p in draft.paragraphs]
    return docx(paras[:n] if n else paras, seed=4)


@pytest.fixture()
def novel(tmp_path: Path) -> tuple[Path, Path]:
    folder = tmp_path / "MyNovel"
    ws = folder / "literary-critic"
    ws.mkdir(parents=True)
    (ws / "work.toml").write_text('slug = "mynovel"\nlanguage = "es"\n', encoding="utf-8")
    doc = folder / "MyNovel_v3.docx"
    doc.write_bytes(_corpus_docx(120))
    assert main(["ingest", str(doc), "--workspace", str(ws)]) == 0
    assert main(["anchor", "--workspace", str(ws)]) == 0
    return ws, doc


def _lc(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any]]:
    capsys.readouterr()
    code = main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def _quote(doc: Path, min_words: int = 12) -> str:
    """A phrase found once in the document, from a long paragraph."""
    texts = docx_edit.texts(doc.read_bytes())
    for t in texts:
        words = t.split()
        if len(words) >= min_words:
            phrase = " ".join(words[3:9])
            if len(docx_edit.find(doc.read_bytes(), phrase)) == 1:
                return phrase
    raise AssertionError("no unique phrase")


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
    code, out = _lc(capsys, "docx", "locate", "c01.s0.p2", *w)
    ck(code == 0 and out["unique"] and len(out["find"]) <= 255)
    ck(out["locator"] is not None and loc_keys <= out["locator"].keys())
    quote = _quote(doc)
    code, out = _lc(capsys, "docx", "locate", quote, *w)
    ck(code == 0 and out["find"].startswith(quote) and out["locator"]["chapter"] != "")
    # edits: dry run, apply, then refused once the quote is gone
    edits = ws.parent / "edits.json"
    req = {"edits": [{"id": "A1", "quote": quote, "replace": quote.upper(), "reason": "test"}]}
    edits.write_text(json.dumps(req), encoding="utf-8")
    before = doc.read_bytes()
    code, out = _lc(capsys, "docx", "edits", "--edits", str(edits), "--dry-run", *w)
    ck(code == 0 and out["status"] == "dry_run" and doc.read_bytes() == before)
    code, out = _lc(capsys, "docx", "edits", "--edits", str(edits), *w)
    keys = {"status", "applied", "skipped", "backup", "revisions", "author"}
    ck(code == 0 and keys <= out.keys() and out["applied"] == ["A1"])
    ck((ws.parent / out["backup"]).read_bytes() == before and out["revisions"] == 1)
    ck(any(quote.upper() in t for t in docx_edit.texts(doc.read_bytes())))
    code, out = _lc(capsys, "docx", "edits", "--edits", str(edits), *w)
    ck(code == 1 and out["status"] == "refused" and out["skipped"][0]["reason"] == "not found")
    # the document no longer matches the ingested draft: no anchor locate, quotes still work
    code, out = _lc(capsys, "docx", "locate", "c01.s0.p2", *w)
    ck(code == 1 and out["reason"] == "changed")
    code, out = _lc(capsys, "docx", "locate", quote.upper(), *w)
    ck(code == 0 and out["locator"] is None)
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
    text = "\n".join(docx_edit.texts(doc.read_bytes()))
    ck(not re.search(r"\bChoto\b", text))
    # usage errors exit 2
    edits.write_text("not json", encoding="utf-8")
    code, out = _lc(capsys, "docx", "edits", "--edits", str(edits), *w)
    ck(code == 2 and out["status"] == "error")
    code, out = _lc(capsys, "docx", "status", "--document", "missing.docx", *w)
    ck(code == 1 and out["reason"] == "missing")
    docx_cli_contract_ok = int(checks == 20 and not failed)
    assert docx_cli_contract_ok == 1, f"failed checks at lines {failed}"


def _unescape(find: str) -> str:
    return find.replace("^^", "\0").replace("^p", "\n").replace("\0", "^")


def test_locate_find_string_is_unique() -> None:
    texts = docx_edit.texts(_corpus_docx())
    whole = "\n".join(texts)
    checked = unique = 0
    for k, t in enumerate(texts):
        if not t.strip():
            continue
        find, ok = docx_cli.find_string(texts, k)
        needle = _unescape(find)
        first = whole.find(needle)
        once = first >= 0 and whole.find(needle, first + 1) < 0
        checked += 1
        unique += ok and once and len(find) <= 255
    assert checked > 1000
    assert unique / checked == 1.0


def test_find_string_escapes_and_spans_paragraphs() -> None:
    texts = ["***", "Uno ^ dos.", "***", "Fin."]
    find, ok = docx_cli.find_string(texts, 2)
    assert ok and find == "***^pFin."
    find, ok = docx_cli.find_string(texts, 1)
    assert ok and find == "Uno"
    assert docx_cli.find_string(texts, 1, 4, 5) == ("^^", True)
    find, ok = docx_cli.find_string(["Fin.", "Fin."], 1)
    assert ok and find == "Fin.^pFin."
