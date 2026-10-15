import json
from pathlib import Path

import pytest

from litcritic import workspace
from litcritic.cli import main


def _work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setenv(workspace.REGISTRY_ENV, str(tmp_path / "workspaces.txt"))
    novel = tmp_path / "Novel"
    novel.mkdir()
    (novel / "draft.md").write_text("# One\n\nText.\n", encoding="utf-8")
    ws = workspace.create("novel", "Novel", "en", base=novel, folder="literary-critic")
    workspace.register(ws.root)
    (ws.root / "log" / "notes.md").write_text("notes\n", encoding="utf-8")
    return novel, ws.root


def test_remove_says_what_would_go_and_deletes_only_with_the_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    novel, root = _work(tmp_path, monkeypatch)
    assert main(["remove", "--workspace", str(root)]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["status"] == "dry_run" and dry["files"] >= 2 and root.is_dir()
    assert main(["remove", "--workspace", str(root), "--confirm", "wrong"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run" and root.is_dir()
    assert main(["remove", "--workspace", str(root), "--confirm", dry["confirm"]]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "removed"
    assert not root.exists()
    assert (novel / "draft.md").is_file()  # the writer's own files stay
    assert str(root) not in workspace.registry_file().read_text(encoding="utf-8")


def test_remove_refuses_what_is_not_a_work(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["remove", "--workspace", str(tmp_path / "nothing")]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"
