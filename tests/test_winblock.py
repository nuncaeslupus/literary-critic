"""Windows refusing a save: blocked by Windows Security or the file open in Word, faked."""

from __future__ import annotations

import pytest

from litcritic import winblock

DOCS = r"C:\Users\w\OneDrive\Documents\My Novel\literary-critic\analysis\overview.json"


def _err(winerror: int | None, cls: type[OSError] = PermissionError) -> OSError:
    exc = cls(13, "Access is denied", DOCS)
    if winerror is not None:
        exc.winerror = winerror  # type: ignore[misc]  # only Windows sets it
    return exc


@pytest.mark.parametrize(
    ("problem", "platform", "expected"),
    [
        (_err(5), "linux", "blocked"),
        (_err(32, OSError), "linux", "open"),
        (_err(33, OSError), "darwin", "open"),
        (_err(None), "win32", "blocked_or_open"),
        (_err(None), "darwin", None),
        (FileNotFoundError(2, "No such file", DOCS), "win32", None),
        (f"[WinError 5] Access is denied: '{DOCS}'", "linux", "blocked"),
        ("[WinError 5] Acceso denegado: 'C:\\x\\y.docx'", "linux", "blocked"),
        (
            "[WinError 32] The process cannot access the file because it is being used by "
            "another process",
            "linux",
            "open",
        ),
        ("[Errno 13] Permission denied: 'C:\\x\\y.docx'", "win32", "blocked_or_open"),
        ("[Errno 13] Permission denied: '/x/y.docx'", "darwin", None),
        ("Paragraph not found", "win32", None),
    ],
)
def test_kind_tells_the_faults_apart(
    problem: BaseException | str, platform: str, expected: str | None
) -> None:
    assert winblock.kind(problem, platform) == expected


def test_blocked_advice_gives_the_clicks_and_the_program() -> None:
    out = winblock.advice(_err(5), program=r"C:\uv\python.exe", platform="win32")
    block = out["windows_block"]
    assert block["kind"] == "blocked" and block["path"] == DOCS
    assert block["protected_folder"] is True and block["program"] == r"C:\uv\python.exe"
    say = block["say"]
    assert "Recently blocked apps" in say and "Controlled folder access" in say
    assert r"C:\uv\python.exe" in say and "doc-control" in say and "update" in say


def test_open_advice_says_close_it_and_text_gives_the_path() -> None:
    text = "[WinError 32] being used by another process: 'D:\\Books\\draft.docx'"
    block = winblock.advice(text, platform="win32")["windows_block"]
    assert block["kind"] == "open" and "Close it" in block["say"]
    assert block["path"] == "D:\\Books\\draft.docx" and block["protected_folder"] is False


def test_other_errors_get_no_advice() -> None:
    assert winblock.advice(ValueError("bad"), platform="win32") == {}
    assert winblock.advice("Paragraph not found", platform="win32") == {}
