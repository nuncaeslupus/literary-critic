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


def test_spot_is_the_old_wording_before_approval_and_the_new_after(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from litcritic import change

    ws, _doc = _novel(tmp_path)
    code, out = _propose(capsys, ws, "fria", "fría", "--by", "writer", "--prefix", "tarde ")
    assert code == 0 and out["card"]["buttons"]["go"] == "Ver en Word"
    assert change.card({"quote": "a", "replace": "b"}, "xx")["buttons"]["go"] == "Show in Word"
    spot = change.spot(ws, "C1")
    # the quote between the words pinned around it: all of this short paragraph
    assert spot["text"] == P1 and spot["status"] == "proposed"
    assert spot["document"] == "MyNovel_v3.docx"
    assert _lc(capsys, "approve", "C1", "--workspace", str(ws))[0] == 0
    assert change.spot(ws, "C1")["text"] == P1.replace("fria", "fría")
    with pytest.raises(change.ChangeRefused):
        change.spot(ws, "C9")


def test_a_change_is_pinned_by_whole_words_around_it() -> None:
    text = "Uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce."
    start = text.index("siete")
    before, after = docx_cli._around(text, start, start + len("siete"), 12)
    assert (before, after) == ("cinco seis ", " ocho nueve")  # cut at spaces, never mid-word
    tabbed = "Antes\tuno dos siete tres\vfin"
    start = tabbed.index("siete")
    assert docx_cli._around(tabbed, start, start + 5, 40) == ("uno dos ", " tres")


def test_change_approve_refuses_when_the_place_was_edited_since_the_card(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The quote is still in the document, but not between the words it had when the card
    was shown: nothing is written, at that place or any other."""
    ws, doc = _novel(tmp_path)
    assert _propose(capsys, ws, "fria", "fría", "--by", "writer")[0] == 0
    doc.write_bytes(_plain("Era una mañana gris y nadie salía.", "Llegó la noche fria."))
    edited = doc.read_bytes()
    code, out = _lc(capsys, "approve", "C1", "--workspace", str(ws))
    assert code == 1 and out["reason"] == "moved" and "Pide el cambio de nuevo" in out["message"]
    assert doc.read_bytes() == edited


# --- cleanups: one change, one Approve, every place --------------------------

SPACED = ("Era  una tarde  fria de otoño.", "La calle   seguía vacía.")


def _cleanup(
    capsys: pytest.CaptureFixture[str], ws: Path, recipe: str = "collapse-spaces", *more: str
) -> tuple[int, dict[str, Any]]:
    return _lc(capsys, "cleanup", "--workspace", str(ws), "--recipe", recipe, *more)


def test_a_cleanup_is_one_change_that_fixes_every_place(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, doc = _workspace(tmp_path, _plain(*SPACED))
    before = doc.read_bytes()
    code, out = _cleanup(capsys, ws, "collapse-spaces", "--why", "espacios dobles")
    assert code == 0 and out["change"] == "C1", out
    card = out["card"]
    assert card["count"] == 3 and card["text"].startswith("¿Corregir 3 sitios?")
    assert card["buttons"]["approve"] == "Corregir los 3"
    assert card["examples"][0] == {
        "before": "Era··una tarde  fria de otoño.",
        "after": "Era·una tarde  fria de otoño.",
    }
    assert len(card["examples"]) == 2  # one per paragraph
    assert doc.read_bytes() == before  # a proposal writes nothing
    code, out = _lc(capsys, "approve", "C1", "--workspace", str(ws))
    assert code == 0 and out["status"] == "applied" and out["count"] == 3, out
    xml = _members(doc.read_bytes())["word/document.xml"].decode("utf-8")
    shown = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))
    assert shown == "Era una tarde fria de otoño.La calle seguía vacía."
    log = [json.loads(x) for x in (ws / "log" / "edits.jsonl").read_text().splitlines()]
    assert log[-1]["edit_ids"] == ["C1"] and log[-1]["command"] == "cleanup"
    # one undo takes the whole cleanup back
    capsys.readouterr()
    assert main(["docx", "undo", "--workspace", str(ws)]) == 0
    undone = json.loads(capsys.readouterr().out)
    assert undone["change"] == "C1", undone
    assert _members(doc.read_bytes())["word/document.xml"] == _members(before)["word/document.xml"]


def test_a_cleanup_needs_a_known_fix_with_places_and_is_offered_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, _doc = _workspace(tmp_path, _plain(*SPACED))
    code, out = _cleanup(capsys, ws, "no-such-fix")
    assert code == 1 and out["reason"] == "invalid"
    code, out = _cleanup(capsys, ws, "ellipsis-char")
    assert code == 1 and out["reason"] == "nothing"
    assert _cleanup(capsys, ws)[0] == 0
    code, out = _cleanup(capsys, ws)
    assert code == 1 and out["reason"] == "repeat"
    _profile(ws, "false")  # typography, not wording: offered whoever writes
    assert _cleanup(capsys, ws, "collapse-spaces", "--again")[0] == 0


def test_a_cleanup_with_nothing_left_settles_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws, doc = _workspace(tmp_path, _plain(*SPACED))
    _cleanup(capsys, ws)
    doc.write_bytes(_plain("Era una tarde.", "La calle."))  # the writer fixed them
    code, out = _lc(capsys, "approve", "C1", "--workspace", str(ws))
    assert code == 0 and out["count"] == 0 and "nada" in out["message"]
    assert not (ws / "log" / "edits.jsonl").exists()


def test_a_cleanup_in_word_waits_for_unsaved_changes_then_goes_into_word(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from litcritic import word_live

    ws, doc = _workspace(tmp_path, _plain(*SPACED))
    _cleanup(capsys, ws)
    before = doc.read_bytes()
    dirty = {"now": True}
    real = dc.run

    def run(name: str, request: dict[str, Any]) -> dict[str, Any]:
        if name == "live.status":
            return {"dirty": dirty["now"], "open_in": {"app": "word"}}
        return real(name, request)

    written: list[dict[str, Any]] = []

    def write(req: dict[str, Any]) -> dict[str, Any]:
        written.append(req)
        return {}

    monkeypatch.setattr(dc, "run", run)
    monkeypatch.setattr(word_live, "is_open", lambda d: True)
    monkeypatch.setattr(word_live, "write", write)
    code, out = _lc(capsys, "approve", "C1", "--workspace", str(ws))
    assert code == 1 and out["reason"] == "unsaved" and "Guárdalo" in out["message"]
    assert not written and doc.read_bytes() == before
    dirty["now"] = False  # the writer saved: the same click works now
    code, out = _lc(capsys, "approve", "C1", "--workspace", str(ws))
    assert code == 0 and out["how"] == "live" and out["count"] == 3, out
    assert len(written[0]["ops"]) == 3 and written[0]["tracked"] is False
    assert doc.read_bytes() == before  # in Word, not the file: the writer saves


def _held_in_word(monkeypatch: pytest.MonkeyPatch, doc: Path) -> list[dict[str, Any]]:
    """Word has ``doc`` open and keeps its file to itself (as a document opened from
    OneDrive): nothing can read the file, and Word answers for its text. Returns the
    batches written into Word."""
    from litcritic import word_live

    paras = {t: docx_cli._resolve(doc, t).rsplit(":", 1)[0] for t in _texts(doc.read_bytes())}
    real_run, real_read = dc.run, Path.read_bytes

    def held() -> PermissionError:
        return PermissionError(13, "Permission denied", str(doc))

    def run(name: str, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("doc") == str(doc):
            raise held()
        return real_run(name, request)

    def read_bytes(self: Path) -> bytes:
        if self == doc:
            raise held()
        return real_read(self)

    def live_paragraph(_doc: Path, phrase: str) -> tuple[str, str]:
        hits = [text for text in paras if phrase in text]
        if len(hits) != 1:
            raise docx_cli.NotOnce(len(hits))
        return hits[0], paras[hits[0]]

    written: list[dict[str, Any]] = []

    def write(request: dict[str, Any]) -> dict[str, Any]:
        written.append(request)
        return {}

    monkeypatch.setattr(dc, "run", run)
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(word_live, "is_open", lambda d: True)
    monkeypatch.setattr(word_live, "run", lambda name, request: {})
    monkeypatch.setattr(word_live, "write", write)
    monkeypatch.setattr(docx_cli, "_live_paragraph", live_paragraph)
    return written


def test_a_change_is_proposed_and_applied_while_word_holds_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, doc = _novel(tmp_path)
    written = _held_in_word(monkeypatch, doc)
    code, out = _propose(capsys, ws, "fria", "fría", "--by", "writer")
    assert code == 0 and out["change"] == "C1" and "fria" in out["card"]["text"], out
    code, out = _lc(capsys, "approve", "C1", "--workspace", str(ws))
    assert code == 0 and out["status"] == "applied", out
    assert [op["text"] for op in written[0]["ops"]] == ["fría"]


def test_a_cleanup_says_why_it_waits_while_word_holds_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, doc = _workspace(tmp_path, _plain(*SPACED))
    _held_in_word(monkeypatch, doc)
    code, out = _cleanup(capsys, ws)
    assert code == 1 and out["reason"] == "held" and "OneDrive" in out["message"], out
