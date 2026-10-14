import json
import time
from pathlib import Path
from typing import Any

import pytest
from test_docx_cli import _corpus_docx, _workspace

from litcritic import dc, word_live
from litcritic.cli import main

LOC = {"chapter": "7", "page": 112, "first_words": "Ya voy", "last_words": "cansada."}
PAYLOADS: dict[str, dict[str, Any]] = {
    "locate": {"document": "N/N.docx", "find": "Ya voy^pdijo", "locator": LOC},
    "apply_edits": {"document": "N/N.docx", "edits": []},
    "rename": {"document": "N/N.docx", "old": "A", "new": "B", "case_sensitive": True},
    "save": {"document": "N/N.docx"},
    "close": {"document": "N/N.docx", "save": True},
    "reopen": {"document": "N/N.docx"},
    "selection": {"document": "N/N.docx"},
}


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


def _live(monkeypatch: pytest.MonkeyPatch, select: Any, reachable: bool = True) -> list[Any]:
    """doc-control stand-in: Word listed as reachable (or not); ``select`` answers
    ``live.select`` (a result, an exception to raise, or a delay in seconds)."""
    calls: list[Any] = []

    def run(op: str, req: dict[str, Any]) -> dict[str, Any]:
        calls.append((op, req))
        if op == "capabilities":
            app = {"app": "word", "available": reachable, "reachable": reachable}
            return {"engines": ["file", "live"], "live": {"apps": [app]}}
        if isinstance(select, BaseException):
            raise select
        if isinstance(select, float):
            time.sleep(select)
            return {"at": "p3#ab", "selected": True}
        return dict(select)

    monkeypatch.setattr(dc, "run", run)
    return calls


def test_locate_live_selects_when_word_is_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _live(monkeypatch, {"at": "p3#ab", "text": "Ya voy"})
    out = word_live.call("locate", {**PAYLOADS["locate"], "paragraphs_after": 2})
    assert out["status"] == "done" and out["how"] == "live" and out["writer"]
    assert calls[-1] == (
        "live.select",
        {"doc": "N/N.docx", "find_phrase": "Ya voy\rdijo", "paragraphs_after": 2},
    )


@pytest.mark.parametrize(
    "select",
    [dc.DocError("ENGINE_UNAVAILABLE", "no Word"), 0.5, {"selected": False}, {}],
    ids=["error", "timeout", "not-selected", "empty"],
)
def test_locate_live_failure_falls_back_to_steps(
    monkeypatch: pytest.MonkeyPatch, select: Any
) -> None:
    monkeypatch.setattr(word_live, "LIVE_TIMEOUT", 0.1)
    _live(monkeypatch, select)
    out = word_live.call("locate", PAYLOADS["locate"])
    assert out["status"] == "manual" and out["how"] == "computer-use" and out["steps"]


def test_locate_live_skipped_when_word_unreachable_or_find_untypable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _live(monkeypatch, {"at": "p3#ab"}, reachable=False)
    assert word_live.call("locate", PAYLOADS["locate"])["how"] == "computer-use"
    calls = _live(monkeypatch, {"at": "p3#ab"})
    soft = {**PAYLOADS["locate"], "find": "por^u173que"}  # a Find-box code with no plain form
    assert word_live.call("locate", soft)["how"] == "computer-use"
    assert all(op != "live.select" for op, _ in calls)
