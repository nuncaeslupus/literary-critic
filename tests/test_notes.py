import io
import json
import re
import time
import zipfile
from pathlib import Path
from typing import Any

import pytest
from docgen import docx

from litcritic import corpus, ingest, notes
from litcritic.cli import main

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
WHEN = 'w:author="Reviewer" w:date="2026-09-30T10:00:00Z"'
CT = (
    '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/'
    'package/2006/content-types"><Default Extension="rels" ContentType="application/'
    'vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType='
    '"application/xml"/><Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override '
    'PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.wordprocessingml.comments+xml"/></Types>'
)
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _run(text: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r>'


def _reviewed(paras: list[str], notes_at: dict[int, str]) -> bytes:
    """A reviewer's copy: paragraph ``i`` in ``notes_at`` gets its first word replaced by a
    tracked change and a comment reading ``notes_at[i]`` on its second word."""
    body: list[str] = []
    comments: list[str] = []
    for i, text in enumerate(paras):
        if i not in notes_at:
            body.append(f"<w:p>{_run(text)}</w:p>")
            continue
        first, second, rest = [*text.split(" ", 2), "", ""][:3]
        cid = len(comments)
        body.append(
            f'<w:p><w:del w:id="{1000 + i}" {WHEN}><w:r><w:delText xml:space="preserve">'
            f'{first}</w:delText></w:r></w:del><w:ins w:id="{5000 + i}" {WHEN}>'
            f'{_run(first.upper())}</w:ins>{_run(" ")}<w:commentRangeStart w:id="{cid}"/>'
            f'{_run(second)}<w:commentRangeEnd w:id="{cid}"/><w:r><w:commentReference '
            f'w:id="{cid}"/></w:r>{_run(" " + rest)}</w:p>'
        )
        comments.append(
            f'<w:comment w:id="{cid}" {WHEN} w:initials="R"><w:p>{_run(notes_at[i])}'
            "</w:p></w:comment>"
        )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", CT)
        zf.writestr(
            "_rels/.rels",
            f'<Relationships xmlns="{RELS}"><Relationship Id="rId1" Type="{OFFICE}/'
            'officeDocument" Target="word/document.xml"/></Relationships>',
        )
        zf.writestr(
            "word/_rels/document.xml.rels",
            f'<Relationships xmlns="{RELS}"><Relationship Id="rId1" Type="{OFFICE}/comments" '
            'Target="comments.xml"/></Relationships>',
        )
        zf.writestr(
            "word/document.xml", f"<w:document {W}><w:body>{''.join(body)}</w:body></w:document>"
        )
        zf.writestr("word/comments.xml", f"<w:comments {W}>{''.join(comments)}</w:comments>")
    return buf.getvalue()


@pytest.fixture()
def work(tmp_path: Path) -> tuple[Path, list[str]]:
    draft = ingest.read(corpus.get("marianela").path)
    rows = [(p.text, bool(re.fullmatch(r"-[IVXL]+-", p.text))) for p in draft.paragraphs[:120]]
    folder = tmp_path / "MyNovel"
    ws = folder / "literary-critic"
    ws.mkdir(parents=True)
    (ws / "work.toml").write_text('slug = "mynovel"\nlanguage = "es"\n', encoding="utf-8")
    doc = folder / "MyNovel_v3.docx"
    doc.write_bytes(docx(rows, seed=4))
    assert main(["ingest", str(doc), "--workspace", str(ws)]) == 0
    assert main(["anchor", "--workspace", str(ws)]) == 0
    return ws, [t for t, _ in rows]


def _lc(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any]]:
    capsys.readouterr()
    code = main(["notes", *argv])
    out = capsys.readouterr().out
    return code, json.loads(out) if code == 0 else {}


def test_notes_are_listed_placed_and_paged(
    work: tuple[Path, list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    ws, paras = work
    long = [i for i, p in enumerate(paras) if len(p.split()) > 20]
    marked = {i: f"Remark {k}" for k, i in enumerate(long[: notes.PAGE])}
    older = list(paras)
    older[long[0]] += " Una frase que el borrador actual ya no tiene."  # an earlier draft
    (ws.parent / "MyNovel-reviewed.docx").write_bytes(_reviewed(older, marked))

    code, listed = _lc(capsys, "--workspace", str(ws))
    assert code == 0 and listed == {"candidates": ["MyNovel-reviewed.docx"]}

    code, first = _lc(capsys, "MyNovel-reviewed.docx", "--workspace", str(ws))
    assert code == 0
    assert first["authors"] == {"Reviewer": {"comment": len(marked), "edit": len(marked)}}
    assert first["placed"] == 2 * len(marked)  # the changed paragraph is still found
    assert (first["pages"], first["next"], len(first["items"])) == (2, "--page 2", notes.PAGE)
    comment, edit = first["items"][:2]
    word = paras[long[0]].split()[0]
    assert comment["kind"] == "comment" and comment["text"] == "Remark 0"
    assert edit["changes"] == [f"{word} → {word.upper()}"]
    assert comment["at"] == edit["at"] and comment["starts"].startswith(word.upper())

    code, comments = _lc(
        capsys, "MyNovel-reviewed.docx", "--workspace", str(ws), "--kind", "comment"
    )
    assert [n["text"] for n in comments["items"]] == list(marked.values())
    assert "next" not in comments
    assert main(["notes", "x.docx", "--workspace", str(ws)]) == 2
    assert main(["notes", "MyNovel-reviewed.docx", "--workspace", str(ws), "--page", "3"]) == 2


def test_saved_notes_are_reused_until_the_file_changes(
    work: tuple[Path, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, paras = work
    path = ws.parent / "reviewed.docx"
    path.write_bytes(_reviewed(paras, {5: "one"}))
    assert notes.load(ws, path)["notes"][0]["text"] == "one"

    def no_read(*_: object) -> dict[str, Any]:
        raise AssertionError("read again")

    monkeypatch.setattr(notes, "extract", no_read)
    assert notes.load(ws, path)["notes"][0]["text"] == "one"  # a dropped chat picks up here
    monkeypatch.undo()
    time.sleep(0.01)
    path.write_bytes(_reviewed(paras, {5: "two"}))
    assert notes.load(ws, path)["notes"][0]["text"] == "two"
