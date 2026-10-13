import json
from pathlib import Path
from typing import Any

import pytest
from test_docx_cli import _corpus_docx, _workspace

from litcritic import word_live
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
    assert "Cmd+F" in " ".join(mac["steps"]) and "Ctrl+F" in " ".join(win["steps"])
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
