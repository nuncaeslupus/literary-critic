from pathlib import Path
from typing import Any

import pytest

from litcritic import dc, winblock


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dc, "_checked", False)


def test_dc_check_rejects_other_major(monkeypatch: pytest.MonkeyPatch) -> None:
    real = dc._execute

    def fake(op: str, request: dict[str, Any]) -> dict[str, Any]:
        if op == "capabilities":
            return {"api": "2.0", "ok": True, "op": op, "result": {}}
        return real(op, request)

    monkeypatch.setattr(dc, "_execute", fake)
    with pytest.raises(dc.DocError) as err:
        dc.run("server.capabilities", {})
    assert err.value.code == "API_UNSUPPORTED" and "pip install" in err.value.hint


def test_dc_check_rejects_a_release_before_the_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(op: str, request: dict[str, Any]) -> dict[str, Any]:
        return {"api": "1.0", "ok": True, "op": op, "result": {"version": "0.8.2"}}

    monkeypatch.setattr(dc, "_execute", fake)
    with pytest.raises(dc.DocError) as err:
        dc.check()
    assert err.value.code == "API_UNSUPPORTED" and "0.8.4" in err.value.hint


def test_dc_source_names_how_a_text_file_was_read(tmp_path: Path) -> None:
    f = tmp_path / "x.md"
    f.write_text("# Title\n\nBody.\n", encoding="utf-8")
    with dc.open(f) as doc:
        assert doc.source() == {"format": "md", "encoding": "utf-8", "mode": "markdown"}
    verse = tmp_path / "x.txt"
    verse.write_text("Line one\nline two\n\nLine three\nline four\n", encoding="utf-8")
    with dc.open(verse, text_mode="lines") as doc:
        assert doc.source()["mode"] == "lines" and len(doc.paragraphs()) == 5
    with pytest.raises(dc.DocError):
        dc.open(verse, text_mode="poem").paragraphs()


def test_dc_run_returns_result_and_raises_error_envelopes() -> None:
    assert "operations" in dc.run("server.capabilities", {})
    with pytest.raises(dc.DocError) as err:
        dc.run("doc.info", {"doc": "/nonexistent/x.docx"})
    assert err.value.code and err.value.message


def test_dc_open_maps_errors_to_doc_error() -> None:
    with dc.open("/nonexistent/x.docx") as doc, pytest.raises(dc.DocError) as err:
        doc.paragraphs()
    assert err.value.code == "DOC_NOT_FOUND" and err.value.hint


def _refusing(times: int) -> tuple[list[str], Any]:
    """An ``_execute`` that refuses the document ``times`` times, then reads it."""
    calls: list[str] = []
    refused = {"code": "INTERNAL", "message": "PermissionError: [Errno 13] Permission denied"}

    def fake(op: str, request: dict[str, Any]) -> dict[str, Any]:
        if op == "capabilities":
            return {"api": "1.0", "ok": True, "op": op, "result": {"version": "0.8.4"}}
        calls.append(op)
        if len(calls) <= times:
            return {"ok": False, "error": refused}
        return {"ok": True, "result": {"at": "p1"}}

    return calls, fake


def test_a_read_refused_for_a_moment_is_tried_again(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, fake = _refusing(2)  # Word saving, or OneDrive syncing, holds the file briefly
    monkeypatch.setattr(dc, "_execute", fake)
    monkeypatch.setattr(dc, "WAIT", 0)
    assert dc.run("anchor.resolve", {})["at"] == "p1"
    assert len(calls) == 3


def test_a_read_still_refused_says_the_file_is_held(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, fake = _refusing(99)
    monkeypatch.setattr(dc, "_execute", fake)
    monkeypatch.setattr(dc, "WAIT", 0)
    with pytest.raises(dc.DocError) as err:
        dc.run("anchor.resolve", {})
    assert len(calls) == dc.TRIES
    assert winblock.kind(err.value) == "held"  # never the ransomware steps for a read
    assert "Nothing was changed" in winblock.advice(err.value)["windows_block"]["say"]


def test_a_refused_write_is_not_tried_again(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, fake = _refusing(99)
    monkeypatch.setattr(dc, "_execute", fake)
    with pytest.raises(dc.DocError) as err:
        dc.run("text.replace", {})
    assert len(calls) == 1
    assert winblock.kind(err.value, platform="win32") == "blocked_or_open"
