import json
import os
from pathlib import Path

import pytest

from litcritic import folders
from litcritic.mcp import ToolError
from litcritic.workspace import MANIFEST


@pytest.fixture(autouse=True)
def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state" / "folders.json"
    monkeypatch.setenv(folders.FOLDERS_ENV, str(state))
    return state


def _work(path: Path, title: str, slug: str) -> Path:
    path.mkdir(parents=True)
    (path / MANIFEST).write_text(
        f'id = "{slug}-abc123"\nslug = "{slug}"\ntitle = "{title}"\n', encoding="utf-8"
    )
    return path


def _link(link: Path, target: Path) -> None:
    """A symlink, or a junction on Windows when symlinks need rights the runner lacks."""
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("symlinks not available")
        import _winapi

        _winapi.CreateJunction(str(target), str(link))  # type: ignore[attr-defined]


def test_confine_outside_paths_refused(tmp_path: Path) -> None:
    novels = tmp_path / "Novels"
    (novels / "Book" / "literary-critic").mkdir(parents=True)
    secret = tmp_path / "Private"
    secret.mkdir()
    (secret / "diary.txt").write_text("x", encoding="utf-8")
    (tmp_path / "Novels2").mkdir()
    _link(novels / "escape", secret)
    grant = folders.Grant([str(novels)])

    refused = [
        novels / ".." / "Private" / "diary.txt",  # ..
        secret / "diary.txt",  # absolute
        novels / "escape" / "diary.txt",  # symlink or junction out
        tmp_path / "Novels2" / "x.txt",  # sibling sharing the prefix
        Path("Book"),  # relative with no base
    ]
    for p in refused:
        with pytest.raises(ToolError) as exc:
            grant.confine(p)
        assert exc.value.payload["error"] == "outside_granted_folders"
    with pytest.raises(ToolError):
        grant.confine("../../Private", base=novels / "Book")

    inside = novels / "Book" / "literary-critic" / "work.toml"
    assert grant.confine(inside) == Path(os.path.realpath(inside))
    assert grant.confine(novels) == Path(os.path.realpath(novels))
    assert grant.confine("literary-critic", base=novels / "Book") == Path(
        os.path.realpath(novels / "Book" / "literary-critic")
    )


def test_confine_counts_added_folders(tmp_path: Path, _state: Path) -> None:
    other = tmp_path / "Other"
    other.mkdir()
    grant = folders.Grant([])
    with pytest.raises(ToolError):
        grant.confine(other / "a.txt")
    grant.add(other)
    grant.add(other)  # stored once
    assert json.loads(_state.read_text(encoding="utf-8"))["folders"] == [os.path.realpath(other)]
    assert grant.confine(other / "a.txt") == Path(os.path.realpath(other / "a.txt"))
    with pytest.raises(ToolError):
        grant.add(tmp_path / "missing")


def test_works_one_level_deep_and_lookup(tmp_path: Path) -> None:
    novels = tmp_path / "Novels"
    a = _work(novels / "Época de lluvias" / "literary-critic", "Época de lluvias", "epoca")
    b = _work(novels / "plain-work", "Second", "second")
    _work(novels / "deep" / "deeper" / "literary-critic", "Too Deep", "deep")
    c = _work(tmp_path / "Single" / "literary-critic", "Single", "single")
    grant = folders.Grant([str(novels), str(tmp_path / "Single"), str(tmp_path / "gone")])

    real = {Path(os.path.realpath(p)) for p in (a, b, c)}
    assert {ws.root for ws in grant.works()} == real
    assert [ws.root for ws in grant.lookup("EPOCA DE LLUVIAS")] == [Path(os.path.realpath(a))]
    assert [ws.root for ws in grant.lookup("second")] == [Path(os.path.realpath(b))]
    assert [ws.root for ws in grant.lookup("single")] == [Path(os.path.realpath(c))]
    assert grant.lookup("Too Deep") == []
