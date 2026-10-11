import shutil
from pathlib import Path

import pytest

from litcritic import workspace
from litcritic.cli import main


def test_same_title_two_authors_coexist(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    home = tmp_path / "home"
    a = workspace.create("ana-the-house", "The House", "en", home, author="Ana", kind="novel")
    b = workspace.create(
        "bo-the-house", "The House", "en", home / "poems", author="Bo", kind="poem"
    )
    ids = {a.manifest["id"], b.manifest["id"]}
    assert len(ids) == 2
    for ws in (a, b):
        assert workspace.resolve(str(ws.manifest["id"]), home).root == ws.root
    assert main(["library", "--by", "author", "--home", str(home)]) == 0
    out = capsys.readouterr().out
    assert "Ana:" in out and "Bo:" in out and "2 work(s)" in out
    assert main(["library", "--by", "kind", "--home", str(home)]) == 0
    assert "poem:" in capsys.readouterr().out


def test_moved_folder_keeps_references(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ws = workspace.create("draft", "Draft", "es", home, author="X")
    wid = str(ws.manifest["id"])
    moved = home / "clients" / "x" / "draft"
    moved.parent.mkdir(parents=True)
    shutil.move(str(ws.root), moved)
    assert workspace.resolve(wid, home).root == moved.resolve()
    assert workspace.resolve("draft", home).root == moved.resolve()


def test_same_slug_in_two_folders_needs_the_id(tmp_path: Path) -> None:
    home = tmp_path / "home"
    a = workspace.create("book", "Book", "es", home / "a", author="A")
    workspace.create("book", "Book", "es", home / "b", author="B")
    with pytest.raises(workspace.WorkspaceError, match="give one of these ids"):
        workspace.resolve("book", home)
    assert workspace.resolve(str(a.manifest["id"]), home).root == a.root


def test_discovery_survives_loops_broken_works_and_copies(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ws = workspace.create("good", "Good", "es", home)
    (home / "loop").symlink_to(home, target_is_directory=True)
    broken = home / "broken"
    broken.mkdir()
    (broken / workspace.MANIFEST).write_text("not = [valid", encoding="utf-8")
    assert workspace.resolve("good", home).root == ws.root
    copy = home / "backup"
    shutil.copytree(ws.root, copy)
    with pytest.raises(workspace.WorkspaceError, match="share the id"):
        workspace.resolve(str(ws.manifest["id"]), home)


def test_unpack_finds_the_work_by_id(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    home = tmp_path / "home"
    ws = workspace.create("book", "Book", "es", home / "shelf")
    zip_path = tmp_path / "book.zip"
    assert main(["pack", "--workspace", str(ws.root), "--out", str(zip_path)]) == 0
    (ws.root / "log" / "note.txt").write_text("x", encoding="utf-8")
    assert main(["unpack", str(zip_path), "--home", str(home), "--force"]) == 0
    assert not (home / "book").exists() and not (ws.root / "log" / "note.txt").exists()
