from pathlib import Path

import pytest

from litcritic import workspace


def test_create_outside_repo(tmp_path: Path) -> None:
    ws = workspace.create("my-novel", "A Title", "es", tmp_path)
    assert ws.manifest["language"] == "es"
    assert "A Title" in ws.guard_terms_file.read_text(encoding="utf-8")
    for sub in workspace.SUBDIRS:
        assert (ws.root / sub).is_dir()
    assert workspace.all_workspaces(tmp_path) == [ws]


def test_refuses_inside_repo() -> None:
    with pytest.raises(workspace.WorkspaceError):
        workspace.create("x", "t", "en", workspace.repo_root() / "workspace")


def test_refuses_duplicate_and_bad_slug(tmp_path: Path) -> None:
    workspace.create("n", "t", "en", tmp_path)
    with pytest.raises(workspace.WorkspaceError):
        workspace.create("n", "t", "en", tmp_path)
    with pytest.raises(workspace.WorkspaceError):
        workspace.create("../evil", "t", "en", tmp_path)
