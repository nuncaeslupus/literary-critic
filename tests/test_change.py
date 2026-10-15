import json
import re
from pathlib import Path
from typing import Any

import pytest
from test_docx_cli import _members, _plain, _texts, _workspace

from litcritic import dc, docx_cli, plan
from litcritic.cli import main

P1 = "Era una tarde fria de otoño y nadie salía de casa."
P2 = "La calle seguía vacía cuando cayó la noche sobre el pueblo."


def _lc(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any]]:
    capsys.readouterr()
    code = main(["change", *argv])
    return code, json.loads(capsys.readouterr().out)


def _novel(tmp_path: Path) -> tuple[Path, Path]:
    return _workspace(tmp_path, _plain(P1, P2))


def _profile(ws: Path, prose: str) -> None:
    f = ws / "analysis" / "profile.toml"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        f'prose_suggestions = {prose}\nai_notice_ack = "2026-01-01T00:00:00Z"\n', encoding="utf-8"
    )


def _propose(
    capsys: pytest.CaptureFixture[str], ws: Path, quote: str, replace: str, *more: str
) -> tuple[int, dict[str, Any]]:
    return _lc(
        capsys, "propose", "--workspace", str(ws), "--quote", quote, "--replace", replace, *more
    )


def test_change_approve_writes_exactly_the_proposed_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, doc = _novel(tmp_path)
    before = doc.read_bytes()
    code, out = _propose(capsys, ws, "fria", "fría", "--by", "writer")
    assert code == 0 and out["change"] == "C1" and "fria" in out["card"]["text"]
    assert out["card"]["words_by"] == "tus palabras"
    assert doc.read_bytes() == before  # a proposal writes nothing
    code, out = _lc(capsys, "approve", "C1", "--workspace", str(ws))
    assert code == 0 and out["status"] == "applied"
    assert _texts(doc.read_bytes())[0] == P1.replace("fria", "fría")
    assert _texts(doc.read_bytes())[1] == P2
    log = [json.loads(x) for x in (ws / "log" / "edits.jsonl").read_text().splitlines()]
    assert log[-1]["edit_ids"] == ["C1"]
    events = [e["event"] for e in plan.read_log(ws)]
    assert events == ["change.proposed", "change.approved", "change.applied"]


def test_change_propose_refuses_assistant_wording_when_prose_off(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, _doc = _novel(tmp_path)
    code, out = _propose(capsys, ws, "fria", "fría", "--by", "assistant")
    assert code == 1 and out["reason"] == "prose_off"
    assert plan.read_log(ws) == []
    assert _propose(capsys, ws, "fria", "fría", "--by", "writer")[0] == 0


def test_change_propose_minor_over_twelve_words_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, _doc = _novel(tmp_path)
    _profile(ws, '"minor"')
    long = "una tarde muy fría y gris de otoño cuando nadie salía de casa por miedo al viento"
    code, out = _propose(capsys, ws, "Era una tarde fria de otoño", long, "--by", "assistant")
    assert code == 1 and out["reason"] == "too_long"
    code, out = _propose(capsys, ws, "fria", "fría", "--by", "assistant")
    assert code == 0 and out["card"]["suggested"] is True


def test_change_approve_twice_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ws, doc = _novel(tmp_path)
    _propose(capsys, ws, "fria", "fría", "--by", "writer")
    assert _lc(capsys, "approve", "C1", "--workspace", str(ws))[0] == 0
    after, log = doc.read_bytes(), (ws / "plan" / "log.jsonl").read_bytes()
    code, out = _lc(capsys, "approve", "C1", "--workspace", str(ws))
    assert code == 1 and out["reason"] == "not_proposed" and "not proposed" in out["message"]
    assert doc.read_bytes() == after and (ws / "plan" / "log.jsonl").read_bytes() == log


def test_change_dismiss_logs_reason(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ws, doc = _novel(tmp_path)
    before = doc.read_bytes()
    _propose(capsys, ws, "fria", "fría", "--by", "writer")
    code, out = _lc(capsys, "dismiss", "C1", "--workspace", str(ws))
    assert code == 0 and out["reason"] == "dismissed in the chat"
    dismissed = [e for e in plan.read_log(ws) if e["event"] == "change.dismissed"]
    assert len(dismissed) == 1 and dismissed[0]["change"] == "C1"
    assert dismissed[0]["reason"] == "dismissed in the chat"
    assert doc.read_bytes() == before
    # the same change is not proposed again unless the writer asks
    code, out = _propose(capsys, ws, "fria", "fría", "--by", "writer")
    assert code == 1 and out["reason"] == "repeat"
    assert _propose(capsys, ws, "fria", "fría", "--by", "writer", "--again")[0] == 0


def test_change_propose_needs_the_quote_once_and_approve_can_stay_with_the_writer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, doc = _novel(tmp_path)
    before = doc.read_bytes()
    assert _propose(capsys, ws, "de", "el", "--by", "writer")[1]["reason"] == "not_once"
    assert _propose(capsys, ws, "nada", "algo", "--by", "writer")[1]["reason"] == "not_once"
    (ws / "analysis").mkdir(exist_ok=True)
    (ws / "analysis" / "profile.toml").write_text("edit_in_place = false\n", encoding="utf-8")
    _propose(capsys, ws, "fria", "fría", "--by", "writer")
    code, out = _lc(capsys, "approve", "C1", "--workspace", str(ws))
    assert code == 0 and out["typed_by"] == "writer"
    assert doc.read_bytes() == before
    assert docx_cli.AUTHOR  # the write path is shared with `lc docx edits`


def test_docx_undo_of_change_logs_change_undone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, doc = _novel(tmp_path)
    before = doc.read_bytes()
    _propose(capsys, ws, "fria", "fría", "--by", "writer")
    _lc(capsys, "approve", "C1", "--workspace", str(ws))
    capsys.readouterr()
    assert main(["docx", "undo", "--workspace", str(ws)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "undone" and out["change"] == "C1"
    assert _texts(doc.read_bytes()) == _texts(before)
    events = [e["event"] for e in plan.read_log(ws)]
    assert events[-1] == "change.undone"
    # nothing left to undo: refused, and nothing more is logged
    assert main(["docx", "undo", "--workspace", str(ws)]) == 1
    capsys.readouterr()
    assert [e["event"] for e in plan.read_log(ws)] == events


def test_docx_undo_of_plain_edit_has_no_change(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, doc = _novel(tmp_path)
    code, _ = docx_cli.apply_edits(ws, doc, [("A1", "fria", "fría", "", "")], {})
    assert code is not None
    capsys.readouterr()
    assert main(["docx", "undo", "--workspace", str(ws)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "change" not in out and plan.read_log(ws) == []


def _marks(data: bytes) -> int:
    xml = _members(data)["word/document.xml"].decode("utf-8")
    return len(re.findall(r"<w:(?:ins|del)[ >]", xml))


def test_change_approve_leaves_no_revision_marks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, doc = _novel(tmp_path)
    _propose(capsys, ws, "fria", "fría", "--by", "writer")
    code, out = _lc(capsys, "approve", "C1", "--workspace", str(ws))
    assert code == 0 and out["status"] == "applied"
    approved_change_revision_marks = _marks(doc.read_bytes())
    assert approved_change_revision_marks == 0
    assert _texts(doc.read_bytes())[0] == P1.replace("fria", "fría")
    capsys.readouterr()
    assert main(["docx", "undo", "--workspace", str(ws)]) == 0  # the backup takes it back
    assert _texts(doc.read_bytes())[0] == P1


def test_overlap_with_tracked_revision_gives_marked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, doc = _novel(tmp_path)
    at = dc.run("anchor.resolve", {"doc": str(doc), "anchor": {"exact": "tarde"}, "mode": "exact"})
    dc.run(
        "doc.batch",
        {
            "doc": str(doc),
            "ops": [{"op": "text.replace", "at": at["at"], "text": "noche"}],
            "author": "someone",
            "tracked": True,
        },
    )
    main(["ingest", str(doc), "--workspace", str(ws)])
    assert _marks(doc.read_bytes()) > 0
    before = doc.read_bytes()
    _propose(capsys, ws, "fria", "fría", "--by", "writer")
    code, out = _lc(capsys, "approve", "C1", "--workspace", str(ws))
    assert code == 1 and out["status"] == "refused" and out["reason"] == "marked"
    assert "accept or reject" in out["message"] or "marked" in out["message"]
    assert doc.read_bytes() == before


def test_old_doc_control_refused_not_tracked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, doc = _novel(tmp_path)
    before = doc.read_bytes()
    sent: list[dict[str, Any]] = []
    real = dc.run

    def old(op: str, request: dict[str, Any]) -> dict[str, Any]:
        if op == "doc.batch":
            sent.append(request)
            if request.get("tracked") is False:
                raise dc.DocError("SCHEMA_INVALID", "unknown field 'tracked'")
        return real(op, request)

    monkeypatch.setattr(dc, "run", old)
    _propose(capsys, ws, "fria", "fría", "--by", "writer")
    code, out = _lc(capsys, "approve", "C1", "--workspace", str(ws))
    assert code == 1 and out["status"] == "refused" and out["reason"] == "doc_control_too_old"
    assert sent and all(r["tracked"] is False for r in sent)  # never silently tracked
    assert doc.read_bytes() == before
