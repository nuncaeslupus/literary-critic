import re
import shutil
from pathlib import Path

import docgen
import pytest

from litcritic import codex, corpus, dc, docx_out, ingest, query, rounds
from litcritic import spans as spanlib
from litcritic.cli import main

DOCX = Path("draft.docx")  # a name for bytes read through doc-control


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("ws")
    (root / "work.toml").write_text('slug = "ws"\nlanguage = "es"\n', encoding="utf-8")
    text = [p.text for p in ingest.read(corpus.get("marianela").path).paragraphs]
    paras = [(t, bool(re.fullmatch(r"-[IVXL]+-", t))) for t in text]
    draft = root.parent / "novela.docx"
    draft.write_bytes(docgen.docx(paras, seed=5))
    assert main(["ingest", str(draft), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    codex.Codex.init(root, "v001")
    return root


@pytest.fixture
def ws(base: Path, tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    shutil.copytree(base, root)
    return root


def _issues(root: Path, anchors: list[str]) -> None:
    cx = codex.Codex(root)
    ix = query.load(root)
    text = spanlib.Text(ix.paragraphs, ix.anchors, "v001")
    for k, a in enumerate(anchors, 1):
        n = len(ix.paragraphs[ix.anchors.index(a)])
        fields = {
            "level": "scene",
            "severity": "medium",
            "check": "scene-craft.purpose",
            "confidence": 0.9,
            "effort": "S",
            "why": f"Motivo {k} & <detalle>.",
        }
        cx.add("issue", f"Punto {k}", fields, [spanlib.make(text, "v001", a, 0, a, n)])


def _comments(path: Path) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    request: dict[str, object] = {"doc": str(path), "limit": 1000}
    while True:
        result = dc.run("comment.list", request)
        out += result["comments"]
        if "_next" not in result:
            return out
        request["cursor"] = result["_next"]


def comments_on_wrong_paragraph(
    out: Path, ix: query.Index, actions: list[dict[str, object]]
) -> int:
    """Actions whose comment is missing or sits on a paragraph other than the one they name."""
    texts = {c["at"].split("#")[0]: c["text"] for c in _comments(out)}
    draft = ingest.read(DOCX, out.read_bytes())
    wrong = 0
    for action in actions:
        k = ix.anchors.index(str(action["where"]["anchor"]))  # type: ignore[index]
        wrong += f"[{action['id']}]" not in texts.get(f"p{draft.paragraphs[k].ordinal + 1}", "")
    return wrong


def test_comments_land_on_target_paragraph(ws: Path) -> None:
    ix = query.load(ws)
    anchors = [ix.anchors[i] for i in range(5, len(ix.anchors), 97) if ".s0." not in ix.anchors[i]]
    _issues(ws, anchors)
    _, actions, _ = rounds.build(ws, level="scene")
    original = (ws / "manuscript" / "v001.docx").read_bytes()
    out_path, n = docx_out.build(ws)
    assert n == len(actions) >= 10
    assert (ws / "manuscript" / "v001.docx").read_bytes() == original  # never touched
    assert comments_on_wrong_paragraph(out_path, ix, actions) == 0
    # The text is unchanged and nothing but the copy is left beside it.
    assert [p.text for p in ingest.read(DOCX, out_path.read_bytes()).paragraphs] == ix.paragraphs
    assert not (out_path.parent / ".doc-control").exists()
    comments = _comments(out_path)
    assert {c["author"] for c in comments} == {"literary-critic"}
    assert any("Motivo 1 & <detalle>." in c["text"] for c in comments)


def test_add_comments_errors(tmp_path: Path) -> None:
    path = tmp_path / "d.docx"
    path.write_bytes(docgen.docx([("Uno dos tres.", False), ("", False), ("Tres cuatro.", False)]))
    first, second = (p.at for p in ingest.read(path).paragraphs)
    assert docx_out.add_comments(path, {second: ["c"], first: ["a", "b"]}) == 2
    texts = [c["text"] for c in dc.run("comment.list", {"doc": str(path)})["comments"]]
    assert texts == ["a\nb", "c"]
    with pytest.raises(docx_out.DocxError):  # an address the document does not have
        docx_out.add_comments(path, {"p9#00000000": ["x"]})


def test_round_draft_and_statuses(ws: Path) -> None:
    ix = query.load(ws)
    anchors = [ix.anchors[i] for i in (40, 41, 300)]
    _issues(ws, anchors)
    _, actions, _ = rounds.build(ws, level="scene")
    rounds.mark(ws, actions[1]["id"], "deferred")
    out_path, n = docx_out.build(ws)
    assert n == 2  # the deferred action is not commented
    assert comments_on_wrong_paragraph(out_path, ix, [actions[0], actions[2]]) == 0
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
