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
    (root / "work.toml").write_text('slug = "ws"\nlanguage = "es"\n', encoding="utf-8")
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
        for action in actions:
            if f"[{action['id']}]" in body:
                target = ix.paragraphs[ix.anchors.index(str(action["where"]["anchor"]))]  # type: ignore[index]
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


def _docx(body: str, comments: str | None = None, prefix: str = "w") -> bytes:
    ns = f'xmlns:{prefix}="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "word/document.xml",
            f"<{prefix}:document {ns}><{prefix}:body>{body}</{prefix}:body></{prefix}:document>",
        )
        if comments is not None:
            zf.writestr("word/comments.xml", comments.replace("NS", ns))
        zf.writestr("word/_rels/document.xml.rels", "<Relationships></Relationships>")
        zf.writestr("[Content_Types].xml", "<Types></Types>")
    return buf.getvalue()


def test_existing_comments_and_odd_markup() -> None:
    body = (
        '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:t>Uno</w:t></w:r></w:p><w:p/>'
        "<w:p><w:pPr/><w:r><w:t>Dos</w:t><w:txbxContent><w:p><w:pPr><w:jc/></w:pPr></w:p>"
        "</w:txbxContent></w:r></w:p>"
    )
    kept = _docx(body, '<w:comments NS><w:comment w:id="4"><w:p/></w:comment></w:comments>')
    z = zipfile.ZipFile(io.BytesIO(docx_out.add_comments(kept, {0: ["a"], 2: ["b"]})))
    doc = z.read("word/document.xml").decode()
    assert '</w:pPr><w:commentRangeStart w:id="5"/>' in doc
    assert '<w:pPr/><w:commentRangeStart w:id="6"/>' in doc  # not inside the text box
    assert z.read("word/comments.xml").decode().count("<w:comment ") == 3
    ET.fromstring(doc)
    # An emptied comments part (self-closing) is extended, not ignored.
    emptied = _docx(body, "<w:comments NS/>")
    comments = zipfile.ZipFile(io.BytesIO(docx_out.add_comments(emptied, {0: ["a"]}))).read(
        "word/comments.xml"
    )
    assert ET.fromstring(comments).find(f"{W}comment") is not None
    # Another prefix for the main namespace.
    other = _docx("<x:p><x:r><x:t>Uno</x:t></x:r></x:p>", prefix="x")
    other_xml = zipfile.ZipFile(io.BytesIO(docx_out.add_comments(other, {0: ["a"]}))).read(
        "word/document.xml"
    )
    assert b'<x:commentRangeStart x:id="0"/>' in other_xml
    with pytest.raises(docx_out.DocxError, match="empty"):
        docx_out.add_comments(kept, {1: ["a"]})


def test_round_draft_and_statuses(ws: Path) -> None:
    ix = query.load(ws)
    anchors = [ix.anchors[i] for i in (40, 41, 300)]
    (ws / "analysis" / "findings.json").write_text(json.dumps(_findings(anchors)), encoding="utf-8")
    _, actions, _ = rounds.build(ws, level="scene")
    rounds.mark(ws, actions[1]["id"], "deferred")
    out_path, n = docx_out.build(ws)
    assert n == 2  # the deferred action is not commented
    assert docx_comment_anchor_accuracy(out_path.read_bytes(), ix, [actions[0], actions[2]]) == 1.0
    # A newer draft does not move the round's comments: they stay on its own draft.
    newer = ws.parent / "novela-v2.docx"
    newer.write_bytes(docgen.docx([("Texto nuevo al principio.", False)] * 3, seed=1))
    assert main(["ingest", str(newer), "--workspace", str(ws)]) == 0
    assert main(["anchor", "--workspace", str(ws)]) == 0
    assert docx_out.build(ws)[0].name == "v001-comments.docx"


def test_non_docx_draft_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "work.toml").write_text('slug = "ws"\n', encoding="utf-8")
    assert main(["ingest", str(corpus.get("jekyll-hyde").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    assert main(["docx-comments", "--workspace", str(root)]) == 1
