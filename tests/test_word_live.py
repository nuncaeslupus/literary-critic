import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from doc_control.model.address import Address, fingerprint
from test_docx_cli import _corpus_docx, _plain, _workspace

from litcritic import dc, plan, word_live
from litcritic.cli import main

LOC = {"chapter": "7", "page": 112, "first_words": "Ya voy", "last_words": "cansada."}
LIVE = word_live._live  # the real call, for the tests that stand in for doc-control
PAYLOADS: dict[str, dict[str, Any]] = {
    "locate": {"document": "N/N.docx", "find": "Ya voy^pdijo", "locator": LOC},
    "apply_edits": {"document": "N/N.docx", "edits": []},
    "rename": {"document": "N/N.docx", "old": "A", "new": "B", "case_sensitive": True},
    "save": {"document": "N/N.docx"},
    "close": {"document": "N/N.docx", "save": True},
    "reopen": {"document": "N/N.docx"},
    "selection": {"document": "N/N.docx"},
}


@pytest.fixture(autouse=True)
def _no_live_word(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reaches a real Word: the live engine is out of reach unless a test says."""

    def unreachable(op: str, request: dict[str, Any]) -> dict[str, Any]:
        raise dc.DocError("LIVE_UNAVAILABLE", "no live app")

    monkeypatch.setattr(word_live, "_live", unreachable)


def test_every_operation_answers_with_computer_use_steps() -> None:
    for op in word_live.OPERATIONS:
        out = word_live.call(op, PAYLOADS[op])
        assert out["status"] == "manual" and out["how"] == "computer-use"
        assert set(word_live.MANUAL_KEYS) == out.keys()
        assert all(isinstance(s, str) and s for s in out["steps"]) and out["writer"]


def test_manual_steps_follow_the_system_and_the_locator() -> None:
    mac = word_live.manual("locate", PAYLOADS["locate"], "darwin")
    win = word_live.manual("locate", PAYLOADS["locate"], "win32")
    assert "Cmd+F" in " ".join(mac["steps"])
    # Word for Windows translates its shortcuts: Find is named by the language of its menus
    assert "Ctrl+F in English, Ctrl+B in Spanish" in " ".join(win["steps"])
    # ...and its search pane searches by itself: an early Enter lands on the previous result
    assert "Wait until the result count" in " ".join(win["steps"])
    assert "Wait until" not in " ".join(mac["steps"])
    assert "Ya voy^pdijo" in " ".join(win["steps"]) and "Chapter 7" in win["writer"]
    no_loc = word_live.manual("locate", {"document": "N.docx", "find": "Ya voy"})
    assert "Ya voy" in no_loc["writer"]
    loc = {"chapter": "7", "page": 112, "first_words": "Ya voy", "last_words": "cansada."}
    es = word_live.manual("locate", {**PAYLOADS["locate"], "locator": loc, "language": "es"})
    assert es["writer"].startswith("En N.docx: Capítulo 7, pág. ≈112"), es["writer"]
    empty = {"chapter": None, "first_words": "", "last_words": ""}
    assert (
        "None" not in word_live.manual("locate", {**PAYLOADS["locate"], "locator": empty})["writer"]
    )
    with pytest.raises(word_live.WordLiveError, match="locator"):
        word_live.call("locate", {**PAYLOADS["locate"], "locator": "c07.s2.p4"})
    discard = word_live.manual("close", {"document": "N.docx", "save": False})
    assert "not to save" in discard["writer"]
    with pytest.raises(word_live.WordLiveError, match="needs find"):
        word_live.call("locate", {"document": "N.docx"})
    with pytest.raises(word_live.WordLiveError, match="unknown"):
        word_live.call("print", {})


def test_windows_steps_use_keys_that_mean_the_same_in_every_word() -> None:
    """In a Spanish Word, Ctrl+S underlines and Ctrl+W resets the paragraph's formatting."""
    for op in ("apply_edits", "save", "close"):
        out = word_live.manual(op, PAYLOADS[op], "win32")
        said = " ".join(out["steps"]) + out["writer"]
        assert "Ctrl+S" not in said and "Ctrl+W" not in said, op
    close = " ".join(word_live.manual("close", PAYLOADS["close"], "win32")["steps"])
    assert "Shift+F12, then Ctrl+F4" in close
    mac = " ".join(word_live.manual("close", PAYLOADS["close"], "darwin")["steps"])
    assert "Cmd+S, then Cmd+W" in mac


def test_locate_is_fed_by_the_find_string_of_lc_docx_locate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`lc docx locate` prints a request `lc word locate` takes as it is: the steps type
    its Find string, move down when Find lands above the passage, and the writer line
    is its locator."""
    ws, _ = _workspace(tmp_path, _corpus_docx(120), anchor=True)
    for target in ("c01.s1.p1", "c01.s1.p5"):
        capsys.readouterr()
        assert main(["docx", "locate", target, "--workspace", str(ws)]) == 0
        located = json.loads(capsys.readouterr().out)
        request = tmp_path / "locate.json"
        request.write_text(json.dumps(located, ensure_ascii=False), encoding="utf-8")
        assert main(["word", "locate", "--payload", str(request)]) == 0
        out = json.loads(capsys.readouterr().out)
        steps = " ".join(out["steps"])
        assert f"type exactly: {located['find']}" in steps
        assert ("move down" in steps) == (not located["unique"])
        assert located["locator"]["first_words"] in out["writer"]
    # the locator's own Find string stands in when `find` is left out
    loc = {**LOC, "find": "Ya voy^pdijo"}
    out = word_live.call("locate", {"document": "N.docx", "locator": loc})
    assert "type exactly: Ya voy^pdijo" in " ".join(out["steps"])
    below = word_live.call("locate", {**PAYLOADS["locate"], "unique": False, "paragraphs_after": 2})
    assert "move down 2 paragraph" in " ".join(below["steps"])


def test_locate_without_a_find_string_answers_with_the_plain_location() -> None:
    """A paragraph with no phrase the Find box can type still gets its writer line."""
    for find in ("", None):
        out = word_live.call("locate", {"document": "N.docx", "find": find, "locator": LOC})
        assert set(word_live.MANUAL_KEYS) == out.keys() and out["status"] == "manual"
        assert len(out["steps"]) == 1 and "plain words" in out["steps"][0]
        assert out["writer"].startswith("In N.docx: Chapter 7") and "cansada." in out["writer"]
    es = word_live.call("locate", {"document": "N.docx", "locator": LOC, "language": "es"})
    assert es["writer"].startswith("En N.docx: Capítulo 7")
    with pytest.raises(word_live.WordLiveError, match="needs find"):  # nothing to say either way
        word_live.call("locate", {"document": "N.docx", "find": "", "locator": {"chapter": "7"}})


def test_lc_word_reads_inline_and_file_payloads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["word", "reopen", "--payload", json.dumps(PAYLOADS["reopen"])]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "manual"
    assert main(["word", "reopen", "--payload", "[1]"]) == 2
    capsys.readouterr()
    long_find = {**PAYLOADS["locate"], "find": "palabra/" * 40}
    assert main(["word", "locate", "--payload", json.dumps(long_find)]) == 0
    capsys.readouterr()
    request = tmp_path / "locate.json"
    request.write_text(json.dumps({**PAYLOADS["locate"], "find": 'I don\'t "know"'}))
    assert main(["word", "locate", "--payload", str(request)]) == 0
    assert "I don't" in " ".join(json.loads(capsys.readouterr().out)["steps"])


def test_the_live_engine_does_it_when_word_has_the_document_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a full path, `lc word` asks doc-control's live engine first; locate selects by
    the paragraph's address, and the answer says it is done."""
    doc = str(tmp_path / "N.docx")
    calls: list[tuple[str, dict[str, Any]]] = []

    def live(op: str, request: dict[str, Any]) -> dict[str, Any]:
        calls.append((word_live.LIVE[op], request))
        if op == "locate":
            return {"text": "Ya voy, dijo cansada.", "at": request["at"]}
        return {"saved": True}

    monkeypatch.setattr(word_live, "_live", live)
    payload = {**PAYLOADS["locate"], "path": doc, "at": "p7#0a1b2c3d"}
    out = word_live.call("locate", payload)
    assert out == {
        "status": "done",
        "how": "live",
        "selected": "Ya voy, dijo cansada.",
        "writer": "In N.docx: Chapter 7, p. ≈112: the paragraph that starts “Ya voy…” "
        "and ends “…cansada.”.",
    }
    assert calls[-1] == ("live.select", {"doc": doc, "mode": "cursor", "at": "p7#0a1b2c3d"})
    assert word_live.call("save", {"document": doc})["result"] == {"saved": True}
    word_live.call("close", {"document": doc, "save": False})
    assert calls[-1] == ("live.close", {"doc": doc, "save": False})
    word_live.call("reopen", {"document": doc})
    assert calls[-1] == ("live.open", {"doc": doc, "app": "word"})
    # file edits never go through Word; a relative path, or a passage with neither its
    # address nor a phrase Word's search could type, has no live request
    calls.clear()
    word_live.call("apply_edits", {"document": doc, "edits": []})
    word_live.call("locate", {**PAYLOADS["locate"], "path": doc, "find": "por^u173que"})
    word_live.call("save", {"document": "N/N.docx"})
    assert calls == []


def test_without_the_live_engine_the_steps_carry_the_mcp_call(tmp_path: Path) -> None:
    """Where doc-control cannot reach Word (Cowork's sandbox, the document not open), the
    computer-use steps come with the doc-control MCP call that would do it, and why not.
    Its ``doc`` is the bare file name, which doc-control resolves on the writer's computer."""
    doc = str(tmp_path / "N.docx")
    out = word_live.call("locate", {**PAYLOADS["locate"], "path": doc, "at": "p7#0a1b2c3d"})
    assert out["status"] == "manual" and out["steps"]
    assert out["live"] == {
        "tool": "live_select",
        # the bare name: see the docstring
        "arguments": {"doc": "N.docx", "mode": "cursor", "at": "p7#0a1b2c3d"},
        "error": {"code": "LIVE_UNAVAILABLE", "message": "no live app"},
    }
    close = word_live.call("close", {"document": doc, "save": True})
    assert close["live"]["tool"] == "live_close" and close["live"]["arguments"]["save"] is True
    assert "live" not in word_live.call("locate", PAYLOADS["locate"])


def _dc(monkeypatch: pytest.MonkeyPatch, select: Any) -> list[Any]:
    """doc-control stand-in behind the real live call: ``select`` answers ``live.select``
    (a result, an exception to raise, or a delay in seconds)."""
    calls: list[Any] = []

    def run(op: str, req: dict[str, Any]) -> dict[str, Any]:
        calls.append((op, req))
        if isinstance(select, BaseException):
            raise select
        if isinstance(select, float):
            time.sleep(select)
            return {"at": "p3#ab", "selected": True}
        return dict(select)

    monkeypatch.setattr(word_live, "_live", LIVE)
    monkeypatch.setattr(dc, "run", run)
    return calls


def test_without_an_address_locate_selects_by_the_find_phrase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = str(tmp_path / "N.docx")
    calls = _dc(monkeypatch, {"at": "p3#ab", "text": "Ya voy"})
    out = word_live.call("locate", {**PAYLOADS["locate"], "path": doc, "paragraphs_after": 2})
    assert out["status"] == "done" and out["how"] == "live" and out["writer"]
    assert calls[-1] == (
        "live.select",
        {"doc": doc, "mode": "cursor", "find_phrase": "Ya voy\rdijo", "paragraphs_after": 2},
    )


@pytest.mark.parametrize(
    "select",
    [dc.DocError("ENGINE_UNAVAILABLE", "no Word"), 0.5, {"selected": False}, {}],
    ids=["error", "timeout", "not-selected", "empty"],
)
def test_a_live_failure_falls_back_to_the_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, select: Any
) -> None:
    monkeypatch.setattr(word_live, "LIVE_TIMEOUT", 0.1)
    _dc(monkeypatch, select)
    out = word_live.call("locate", {**PAYLOADS["locate"], "path": str(tmp_path / "N.docx")})
    assert out["status"] == "manual" and out["how"] == "computer-use" and out["steps"]
    assert out["live"]["error"]["code"]


def test_docx_locate_go_takes_word_there_in_one_step(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`lc docx locate --go` answers as `lc word locate` on its answer, in one command."""
    ws, _ = _workspace(tmp_path, _corpus_docx(120), anchor=True)
    capsys.readouterr()
    assert main(["docx", "locate", "c01.s1.p5", "--workspace", str(ws)]) == 0
    request = tmp_path / "locate.json"
    # the writer line in the novel's language, as the prompt asks of the two steps
    located = {**json.loads(capsys.readouterr().out), "language": "es"}
    request.write_text(json.dumps(located, ensure_ascii=False), encoding="utf-8")
    assert main(["word", "locate", "--payload", str(request)]) == 0
    two_steps = json.loads(capsys.readouterr().out)
    assert main(["docx", "locate", "c01.s1.p5", "--go", "--workspace", str(ws)]) == 0
    assert json.loads(capsys.readouterr().out) == two_steps


def test_docx_places_is_one_live_places_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`lc docx places` turns a list into doc-control's `live_places`: one button per place,
    each at the paragraph `lc docx locate` finds, the cursor left there; misses are listed."""
    ws, _ = _workspace(tmp_path, _corpus_docx(120), anchor=True)
    capsys.readouterr()
    assert main(["docx", "locate", "c01.s1.p5", "--workspace", str(ws)]) == 0
    one = json.loads(capsys.readouterr().out)
    targets = ["c01.s1.p5", "c02", "no such words anywhere"]
    assert main(["docx", "places", *targets, "--workspace", str(ws)]) == 0
    out = json.loads(capsys.readouterr().out)
    args = out["live"]["arguments"]
    assert out["live"]["tool"] == "live_places" and args["mode"] == "cursor"
    assert args["doc"] == Path(one["path"]).name and len(args["places"]) == 2
    first = args["places"][0]
    assert first["at"] == one["at"] and one["locator"]["first_words"] in first["label"]
    assert out["writer"].splitlines()[0] == f"1. {first['label']}"
    assert [m["target"] for m in out["missing"]] == [targets[2]]
    assert main(["docx", "places", targets[2], "--workspace", str(ws)]) == 1


class _FakeLive:
    """doc-control's live engine for one open document: records the batches it gets and,
    like the real one, makes no revision for a plain write."""

    def __init__(
        self, doc: Path, refuse: dc.DocError | None = None, texts: list[str] | None = None
    ) -> None:
        self.doc = doc
        self.refuse = refuse
        self.texts = texts or []  # the open document's paragraphs, unsaved edits and all
        self.batches: list[dict[str, Any]] = []
        self.selected: list[str] = []
        self.revisions: list[Any] = []
        self.real = dc.run

    def run(self, op: str, req: dict[str, Any]) -> dict[str, Any]:
        if op == "live.status":
            return {"documents": [{"path": str(self.doc)}]}
        if op == "live.select":
            hits = [t for t in self.texts if req["find_phrase"].lower() in t.lower()]
            if len(hits) != 1:
                raise dc.DocError("ANCHOR_AMBIGUOUS" if hits else "ANCHOR_NOT_FOUND", "")
            self.selected.append(req["find_phrase"])
            n = self.texts.index(hits[0]) + 1
            return {"text": hits[0], "at": str(Address(n, fingerprint(hits[0])))}
        if op == "doc.batch" and req.get("engine") == "live":
            self.batches.append(req)
            if self.refuse:
                raise self.refuse
            if req.get("tracked", True) is not False:
                self.revisions.extend(req["ops"])
            for edit in req["ops"]:  # the write lands in the open document, as in Word
                para, span = edit["at"].rsplit(":", 1)
                n, (lo, hi) = int(para[1:].split("#")[0]), map(int, span.split("-"))
                t = self.texts[n - 1]
                self.texts[n - 1] = t[:lo] + edit["text"] + t[hi:]
            return {"applied": len(req["ops"]), "engine": "live"}
        return self.real(op, req)


def _approve_live(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    refuse: dc.DocError | None = None,
    unsaved: str = "",
) -> tuple[_FakeLive, int, dict[str, Any], bytes, Path]:
    p1 = "Era una tarde fria de otoño y nadie salía de casa."
    ws, doc = _workspace(tmp_path, _plain(p1, "La calle seguía vacía."))
    fake = _FakeLive(doc, refuse, [unsaved + p1, "La calle seguía vacía."])
    monkeypatch.setattr(dc, "run", fake.run)
    capsys.readouterr()
    args = ["change", "propose", "--workspace", str(ws), "--quote", "fria", "--replace", "fría"]
    assert main([*args, "--by", "writer"]) == 0
    capsys.readouterr()
    before = doc.read_bytes()
    code = main(["change", "approve", "C1", "--workspace", str(ws)])
    return fake, code, json.loads(capsys.readouterr().out), before, doc


def test_live_change_approve_sends_untracked_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With the document open in Word, approving a change is one plain `doc.batch` on the
    live engine: `tracked: false`, no revision mark, and the file is left to the app."""
    fake, code, out, before, doc = _approve_live(tmp_path, monkeypatch, capsys)
    assert code == 0 and out["status"] == "applied" and out["how"] == "live"
    assert len(fake.batches) == 1
    sent = fake.batches[0]
    assert sent["tracked"] is False and sent["engine"] == "live"
    assert [o["op"] for o in sent["ops"]] == ["text.replace"] and sent["ops"][0]["text"]
    assert "expect" not in sent and "dry_run" not in sent
    assert fake.revisions == []
    assert doc.read_bytes() == before  # Word holds the change until the writer saves


@pytest.mark.parametrize(
    ("code", "message", "reason"),
    [
        ("SCHEMA_INVALID", "unknown field tracked", "doc_control_too_old"),
        ("UNSUPPORTED_CONTENT", "paragraph holds an unresolved tracked change", "marked"),
    ],
)
def test_live_plain_write_refusals_have_the_file_engines_reasons(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    code: str,
    message: str,
    reason: str,
) -> None:
    _fake, status, out, _before, _doc = _approve_live(
        tmp_path, monkeypatch, capsys, dc.DocError(code, message)
    )
    assert status == 1 and out["status"] == "refused" and out["reason"] == reason


def test_every_live_call_runs_on_one_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Word's COM handle answers only on the thread that made it: status, the write and
    the select must share one thread, or the second call sees no open document."""
    threads: list[int] = []

    def run(name: str, request: dict[str, Any]) -> dict[str, Any]:
        threads.append(threading.get_ident())
        return {"documents": [], "at": "p1", "text": ""}

    monkeypatch.setattr(dc, "run", run)
    word_live.is_open(tmp_path / "N.docx")
    word_live.write({"doc": "N.docx", "ops": []})
    word_live.run("live.select", {"doc": "N.docx"})
    word_live.is_open(tmp_path / "N.docx")
    assert len(threads) == 4 and len(set(threads)) == 1
    assert threads[0] != threading.get_ident()


def test_a_timed_out_live_call_frees_the_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()

    def run(name: str, request: dict[str, Any]) -> dict[str, Any]:
        if name == "slow":
            release.wait(5)
        return {"name": name}

    monkeypatch.setattr(dc, "run", run)
    with pytest.raises(dc.DocError) as err:
        word_live.run("slow", {}, timeout=0.05)
    assert err.value.code == "LIVE_TIMEOUT"
    assert word_live.run("fast", {}, timeout=1) == {"name": "fast"}
    release.set()


def test_live_approve_finds_the_quote_in_the_open_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Word holds an edit not yet saved in the quote's paragraph: the range sent is the
    open paragraph's (its address and offsets), not the saved file's."""
    unsaved = "Al fin, "
    fake, code, out, _before, doc = _approve_live(tmp_path, monkeypatch, capsys, unsaved=unsaved)
    assert code == 0 and out["how"] == "live"
    open_text = unsaved + "Era una tarde fria de otoño y nadie salía de casa."
    start = open_text.index("fria")
    at = f"{Address(1, fingerprint(open_text))}:{start}-{start + 4}"
    assert fake.batches[0]["ops"][0]["at"] == at
    # Read back and gone to by the words around it: the whole short paragraph here.
    assert fake.texts[0] == open_text.replace("fria", "fría")
    assert out["locate"]["live"] == {"doc": str(doc), "find_phrase": fake.texts[0]}
    assert fake.selected[-1] == fake.texts[0]


def test_live_approve_refuses_a_quote_gone_from_the_open_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    p1 = "Era una tarde fria de otoño y nadie salía de casa."
    ws, doc = _workspace(tmp_path, _plain(p1, "La calle seguía vacía."))
    fake = _FakeLive(doc, texts=[p1, "La calle seguía vacía."])
    monkeypatch.setattr(dc, "run", fake.run)
    args = ["change", "propose", "--workspace", str(ws), "--quote", "fria", "--replace", "fría"]
    assert main([*args, "--by", "writer"]) == 0
    fake.texts[0] = "Era una tarde gris."  # the writer edits it before clicking Approve
    capsys.readouterr()
    assert main(["change", "approve", "C1", "--workspace", str(ws)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["reason"] == "moved" and "Pide la tarjeta de nuevo" in out["message"]
    assert fake.batches == []


def test_live_approve_never_writes_the_quote_at_another_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The words around the quote were edited while the quote is still in the document,
    once, at another place: nothing is written there."""
    p1 = "Era una tarde fria de otoño y nadie salía de casa."
    ws, doc = _workspace(tmp_path, _plain(p1, "La calle seguía vacía."))
    fake = _FakeLive(doc, texts=[p1, "La calle seguía vacía."])
    monkeypatch.setattr(dc, "run", fake.run)
    args = ["change", "propose", "--workspace", str(ws), "--quote", "fria", "--replace", "fría"]
    assert main([*args, "--by", "writer"]) == 0
    fake.texts[:] = ["Era una mañana gris.", "La noche fria de otoño."]
    capsys.readouterr()
    assert main(["change", "approve", "C1", "--workspace", str(ws)]) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "moved"
    assert fake.batches == []


def test_live_approve_says_so_when_the_write_is_not_read_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Word took the batch but the place does not read back as the change: the writer is
    told, and the change is logged as written but not confirmed."""
    p1 = "Era una tarde fria de otoño y nadie salía de casa."
    ws, doc = _workspace(tmp_path, _plain(p1, "La calle seguía vacía."))
    fake = _FakeLive(doc, texts=[p1, "La calle seguía vacía."])
    monkeypatch.setattr(dc, "run", fake.run)
    args = ["change", "propose", "--workspace", str(ws), "--quote", "fria", "--replace", "fría"]
    assert main([*args, "--by", "writer"]) == 0
    real = fake.run

    def lost(op: str, req: dict[str, Any]) -> dict[str, Any]:
        out = real(op, req)
        if op == "doc.batch":
            fake.texts[0] = p1  # undone at once (an add-in, Ctrl+Z): not as written
        return out

    monkeypatch.setattr(dc, "run", lost)
    capsys.readouterr()
    assert main(["change", "approve", "C1", "--workspace", str(ws)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "unconfirmed" and "Ctrl+Z" in out["message"]
    applied = [e for e in plan.read_log(ws) if e["event"] == "change.applied"]
    assert applied[-1]["data"]["confirmed"] is False


def test_go_takes_word_to_the_phrase_in_the_open_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeLive(tmp_path / "N.docx", texts=["Una tarde fría.", "Otra."])
    monkeypatch.setattr(dc, "run", fake.run)
    out = word_live.go(tmp_path / "N.docx", "fría")
    assert out == {"status": "done", "how": "live", "selected": "Una tarde fría."}
    assert word_live.go(tmp_path / "N.docx", "nada")["status"] == "failed"


class _ClosedWord:
    """A Word with nothing open: ``live.select`` fails until ``live.open`` opens the file."""

    def __init__(self, opens: bool = True) -> None:
        self.open: list[str] = []
        self.calls: list[str] = []
        self.opens = opens

    def run(self, op: str, req: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(op)
        if op == "live.status":
            return {"documents": [{"path": p} for p in self.open]}
        if op == "live.open":
            if not self.opens:
                raise dc.DocError("ENGINE_UNAVAILABLE", "no Word")
            self.open.append(req["doc"])
            return {"opened": True}
        if op == "live.select":
            if req["doc"] not in self.open:
                raise dc.DocError("DOC_NOT_OPEN", "not open")
            return {"at": "p1#ab", "selected": True, "text": "Una tarde fría."}
        raise AssertionError(op)


def test_a_click_opens_the_document_word_does_not_have_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = tmp_path / "N.docx"
    doc.write_bytes(_plain("Una tarde fría."))
    word = _ClosedWord()
    monkeypatch.setattr(dc, "run", word.run)
    assert word_live.go(doc, "fría")["status"] == "done"
    assert word.calls == ["live.select", "live.status", "live.open", "live.select"]
    assert word_live.open_if_closed(doc) is False  # open now: nothing to do

    monkeypatch.setattr(word_live, "_live", LIVE)
    word.open.clear()
    out = word_live.call("locate", {**PAYLOADS["locate"], "path": str(doc)})
    assert out["status"] == "done" and word.open == [str(doc)]


def test_a_document_that_cannot_be_opened_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    word = _ClosedWord(opens=False)
    monkeypatch.setattr(dc, "run", word.run)
    gone = tmp_path / "gone.docx"  # no such file: Word is not asked to open it
    assert word_live.go(gone, "fría")["status"] == "failed"
    assert word.calls == ["live.select"]
    doc = tmp_path / "N.docx"
    doc.write_bytes(_plain("Una tarde fría."))
    assert word_live.go(doc, "fría")["status"] == "failed"
    assert word.calls[1:] == ["live.select", "live.status", "live.open"]
