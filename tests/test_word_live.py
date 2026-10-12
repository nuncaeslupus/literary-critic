import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from litcritic import word_live
from litcritic.cli import main

DOC = Path(__file__).resolve().parents[1] / "docs" / "word-control-interface.md"

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


def _keys(line: str) -> set[str]:
    return set(re.findall(r"`(\w+)`", re.sub(r"\(.*?\)", "", line)))


def _documented() -> dict[str, tuple[set[str], set[str]]]:
    out: dict[str, tuple[set[str], set[str]]] = {}
    for block in re.split(r"^### ", DOC.read_text(encoding="utf-8"), flags=re.M)[1:]:
        name = re.match(r"`(\w+)`", block)
        req = re.search(r"^- Request: (.*)$", block, re.M)
        res = re.search(r"^- Response: (.*)$", block, re.M)
        if name and req and res:
            out[name.group(1)] = (_keys(req.group(1)), _keys(res.group(1)))
    return out


def test_word_live_adapter_matches_interface_doc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(word_live.ENV, raising=False)
    documented = _documented()
    matches = 0
    for op, (request, response) in word_live.OPERATIONS.items():
        doc_req, doc_res = documented.get(op, (set(), set()))
        optional = set(word_live.OPTIONAL.get(op, ()))
        same = doc_req == set(request) | optional and doc_res == set(response)
        out = word_live.call(op, PAYLOADS[op])
        manual = out["status"] == "manual" and set(word_live.MANUAL_KEYS) <= out.keys()
        manual = manual and all(isinstance(s, str) and s for s in out["steps"]) and out["writer"]
        matches += bool(same and manual)
    word_helper_interface_documented = int(
        matches == len(word_live.OPERATIONS) and set(documented) == set(word_live.OPERATIONS)
    )
    assert word_helper_interface_documented == 1


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


def test_extension_command_is_used_and_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = tmp_path / "fake_word.py"
    fake.write_text(
        "import json, sys\n"
        "req = json.load(sys.stdin)\n"
        "print(json.dumps({'status': 'ok', 'found': True, 'op': sys.argv[1], 'req': req}))\n"
    )
    monkeypatch.setenv(word_live.ENV, f"{sys.executable} {fake}")
    out = word_live.call("locate", PAYLOADS["locate"])
    assert out["status"] == "ok" and out["op"] == "locate" and out["req"] == PAYLOADS["locate"]
    monkeypatch.setenv(word_live.ENV, f"{sys.executable} {tmp_path / 'missing.py'}")
    out = word_live.call("save", PAYLOADS["save"])
    assert out["status"] == "manual" and out["extension_error"]
    monkeypatch.delenv(word_live.ENV)
    assert main(["word", "reopen", "--payload", json.dumps(PAYLOADS["reopen"])]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "manual"
    assert main(["word", "reopen", "--payload", "[1]"]) == 2
    long_find = {**PAYLOADS["locate"], "find": "palabra/" * 40}
    assert main(["word", "locate", "--payload", json.dumps(long_find)]) == 0
    capsys.readouterr()
    request = tmp_path / "locate.json"
    request.write_text(json.dumps({**PAYLOADS["locate"], "find": 'I don\'t "know"'}))
    assert main(["word", "locate", "--payload", str(request)]) == 0
    assert "I don't" in " ".join(json.loads(capsys.readouterr().out)["steps"])
