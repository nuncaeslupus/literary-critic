import io
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import docgen
import pytest

from litcritic import corpus, docx_out, ingest, query, rounds
from litcritic.cli import main

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@pytest.fixture(scope="module")
def ws(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("ws")
    (root / "workspace.toml").write_text('slug = "ws"\nlanguage = "es"\n', encoding="utf-8")
    text = [p.text for p in ingest.read_txt(corpus.get("marianela").path.read_bytes()).paragraphs]
    paras = [(t, bool(re.fullmatch(r"-[IVXL]+-", t))) for t in text]
    draft = root.parent / "novela.docx"
    draft.write_bytes(docgen.docx(paras, seed=5))
    assert main(["ingest", str(draft), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    return root


def _findings(anchors: list[str]) -> list[dict[str, object]]:
    return [
        {
            "schema_version": 1,
            "id": f"F{k}",
            "check_id": "scene-craft.purpose",
            "anchors": [a],
            "evidence": [{"anchor": a, "quote": "x"}],
            "explanation": f"Motivo {k} & <detalle>.",
            "severity": "medium",
            "confidence": 0.9,
            "effort": "S",
            "kind": "problem",
            "status": "open",
        }
        for k, a in enumerate(anchors, 1)
    ]


def docx_comment_anchor_accuracy(
    out: bytes, ix: query.Index, actions: list[dict[str, object]]
) -> float:
    """Share of comments whose range sits in the paragraph the action targets."""
    root = ET.fromstring(zipfile.ZipFile(io.BytesIO(out)).read("word/document.xml"))
    draft = ingest.read_docx(out)
    by_src = {p.src: p.text for p in draft.paragraphs}
    ordinal_of = {}
    for k, p in enumerate(root.iter(f"{W}p")):
        for start in p.iter(f"{W}commentRangeStart"):
            ordinal_of[start.get(f"{W}id")] = k
    comments = ET.fromstring(zipfile.ZipFile(io.BytesIO(out)).read("word/comments.xml"))
    hits = 0
    for c in comments.iter(f"{W}comment"):
        body = "".join(t.text or "" for t in c.iter(f"{W}t"))
        action = next(a for a in actions if body.startswith(f"[{a['id']}]"))
        target = ix.paragraphs[ix.anchors.index(action["where"]["anchor"])]  # type: ignore[index]
        hits += by_src.get(ordinal_of[c.get(f"{W}id")]) == target
    return hits / len(actions)


def test_comments_attach_to_target_paragraphs(ws: Path) -> None:
    ix = query.load(ws)
    anchors = [ix.anchors[i] for i in range(5, len(ix.anchors), 97) if ".s0." not in ix.anchors[i]]
    (ws / "analysis").mkdir(exist_ok=True)
    (ws / "analysis" / "findings.json").write_text(json.dumps(_findings(anchors)), encoding="utf-8")
    _, actions, _ = rounds.build(ws, level="scene")
    original = (ws / "manuscript" / "v001.docx").read_bytes()
    out_path, n = docx_out.build(ws)
    assert n == len(actions) >= 10
    assert (ws / "manuscript" / "v001.docx").read_bytes() == original  # never touched
    out = out_path.read_bytes()
    assert docx_comment_anchor_accuracy(out, ix, actions) == 1.0
    # The text is unchanged and the package is well formed.
    assert [p.text for p in ingest.read_docx(out).paragraphs] == ix.paragraphs
    z = zipfile.ZipFile(io.BytesIO(out))
    assert "comments.xml" in z.read("word/_rels/document.xml.rels").decode()
    assert "/word/comments.xml" in z.read("[Content_Types].xml").decode()
    assert "Motivo 1 &amp; &lt;detalle&gt;." in z.read("word/comments.xml").decode()


def test_existing_comments_are_kept() -> None:
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "word/document.xml",
            f'<w:document {w}><w:body><w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
            "<w:r><w:t>Uno</w:t></w:r></w:p><w:p/><w:p><w:r><w:t>Dos</w:t></w:r></w:p></w:body></w:document>",
        )
        zf.writestr(
            "word/comments.xml",
            f'<w:comments {w}><w:comment w:id="4"><w:p/></w:comment></w:comments>',
        )
        zf.writestr("word/_rels/document.xml.rels", "<Relationships/>")
        zf.writestr("[Content_Types].xml", "<Types></Types>")
    out, placed = docx_out.add_comments(buf.getvalue(), {0: ["a"], 2: ["b"]})
    assert placed == {5: 0, 6: 2}
    z = zipfile.ZipFile(io.BytesIO(out))
    doc = z.read("word/document.xml").decode()
    assert '</w:pPr><w:commentRangeStart w:id="5"/>' in doc
    assert z.read("word/comments.xml").decode().count("<w:comment ") == 3
    ET.fromstring(doc)


def test_non_docx_draft_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "workspace.toml").write_text('slug = "ws"\n', encoding="utf-8")
    assert main(["ingest", str(corpus.get("jekyll-hyde").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    assert main(["docx-comments", "--workspace", str(root)]) == 1
