"""The saved overview: stored with its draft, read back, stale after a new draft."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from litcritic import cli, overview


def _work(tmp_path: Path, drafts: int = 1) -> Path:
    root = tmp_path / "ws"
    (root / "text").mkdir(parents=True)
    (root / "work.toml").write_text('id = "w-test"\nslug = "w"\n', encoding="utf-8")
    for n in range(1, drafts + 1):
        (root / "text" / f"v{n:03d}.txt").write_text("Text.\n", encoding="utf-8")
    return root


def test_save_and_load_keep_draft_reading_and_text(tmp_path: Path) -> None:
    root = _work(tmp_path)
    assert overview.load(root) is None
    saved = overview.save(root, "  What works. Problem one.  ", ["c01,c23", "c46"], partial=True)
    assert saved["draft"] == "v001" and saved["stale"] is False
    assert saved["read"] == ["c01", "c23", "c46"] and saved["partial"] is True
    shown = overview.load(root)
    assert shown is not None
    assert shown["text"] == "What works. Problem one."
    assert shown["stale"] is False and shown["issues"] == []
    assert json.loads(overview.path(root).read_text("utf-8"))["schema_version"] == 1


def test_a_new_draft_makes_it_stale(tmp_path: Path) -> None:
    root = _work(tmp_path)
    overview.save(root, "Overview.", ["all"])
    (root / "text" / "v002.txt").write_text("Text.\n", encoding="utf-8")
    shown = overview.load(root)
    assert shown is not None and shown["stale"] is True and shown["draft"] == "v001"


def test_long_text_is_capped_when_asked(tmp_path: Path) -> None:
    root = _work(tmp_path)
    overview.save(root, "word " * 100)
    shown = overview.load(root, cap=20)
    assert shown is not None and shown["truncated"] is True and len(shown["text"]) <= 22


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"text": "   "}, "empty"),
        ({"text": "Overview.", "draft": "v009"}, "no draft"),
        ({"text": "Overview.", "issues": ["is-nothere"]}, "Codex"),
    ],
)
def test_save_refuses_bad_input(tmp_path: Path, kwargs: dict, message: str) -> None:
    root = _work(tmp_path)
    with pytest.raises(overview.OverviewError, match=message):
        overview.save(root, **kwargs)
    assert overview.load(root) is None


def test_cli_save_and_show(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _work(tmp_path)
    note = tmp_path / "overview.md"
    note.write_text("What works.\n\n1. The middle sags.\n", encoding="utf-8")
    ws = ["--workspace", str(root)]
    assert cli.main(["overview", "save", *ws, "--text-file", str(note), "--read", "all"]) == 0
    assert json.loads(capsys.readouterr().out)["overview"]["read"] == ["all"]
    assert cli.main(["overview", "show", *ws]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["status"] == "ok" and "middle sags" in shown["overview"]["text"]
    assert cli.main(["overview", "save", *ws, "--text", ""]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "refused"
