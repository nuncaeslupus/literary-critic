import json
import os
import shutil
import subprocess
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

        _winapi.CreateJunction(str(target), str(link))  # type: ignore[attr-defined,unused-ignore]


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


def test_add_folder_decodes_utf8_accents(tmp_path: Path, _state: Path) -> None:
    picked = tmp_path / "Señora Ñúñez"
    _work(picked / "literary-critic", "Señora", "senora")
    calls: list[list[str]] = []

    def fake(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=str(picked).encode("utf-8"))

    grant = folders.Grant([])
    out = folders.add_folder(grant, fake)
    assert out["added"] == os.path.realpath(picked)
    assert json.loads(_state.read_text(encoding="utf-8"))["folders"] == [os.path.realpath(picked)]
    assert out["works"] == ["Señora"]
    assert "-STA" in calls[0]

    def cancel(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(cmd, 1, stdout=b"")

    assert folders.add_folder(grant, cancel) == {"cancelled": True}


def test_add_folder_tool_listed(tmp_path: Path) -> None:
    from litcritic import mcp

    assert "add_folder" in [t.name for t in mcp.tools(folders.Grant([str(tmp_path)]))]


# --- the state place (Controlled folder access) -------------------------------------

from litcritic import cfa  # noqa: E402


def _layouts(tmp_path: Path) -> tuple[Path, Path, dict[str, Path]]:
    home = tmp_path / "Users" / "me"
    drive = home / "OneDrive"
    novels = {
        "Documents": home / "Documents" / "Novel",
        "OneDrive-Documents": drive / "Documents" / "Novel",
        "OneDrive-other": drive / "Books" / "Novel",
        "outside": tmp_path / "Work" / "Novel",
    }
    for p in novels.values():
        p.mkdir(parents=True)
    return home, drive, novels


def _place(
    grant: folders.Grant, novel: Path, status: cfa.Status | None, home: Path, drive: Path | None
) -> tuple[dict[str, object], list[Path]]:
    wrote: list[Path] = []

    def run(root: Path) -> dict[str, object]:
        root.mkdir(parents=True, exist_ok=True)
        (root / MANIFEST).write_text('id = "n-1"\n', encoding="utf-8")
        wrote.append(root)
        return {"status": "ready"}

    return folders.with_state_place(grant, novel, run, lambda: status, home, drive), wrote


def test_state_place_cfa_on_protected_uses_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        monkeypatch.delenv(name, raising=False)
    home, drive, novels = _layouts(tmp_path)
    on = cfa.Status(True)
    for layout, novel in novels.items():
        protected = layout in ("Documents", "OneDrive-Documents")
        for onedrive, base in ((drive, drive), (None, home)):
            if onedrive is None and layout.startswith("OneDrive"):
                continue  # no OneDrive, no such layout
            grant = folders.Grant([str(novel.parent)])
            folders.state_file().unlink(missing_ok=True)
            out, wrote = _place(grant, novel, on, home, onedrive)
            assert len(wrote) == 1
            if protected:
                assert wrote[0].parent == base / "literary-critic", layout
                assert not (novel / "literary-critic").exists(), layout
                assert out["state_place"]["kind"] == "fallback"  # type: ignore[index]
                assert grant.state_root(novel) == wrote[0]
                assert [w.root for w in grant.works()] == [wrote[0].resolve()]
                # kept: the second call neither re-chooses nor reports again
                again, _ = _place(grant, novel, on, home, onedrive)
                assert "state_place" not in again
            else:
                assert wrote[0] == novel / "literary-critic", layout
            shutil.rmtree(wrote[0])
    folders.state_file().unlink(missing_ok=True)
    # a folder the user added to the list is protected too
    extra = cfa.Status(True, (str(novels["outside"]),))
    out, wrote = _place(folders.Grant([]), novels["outside"], extra, home, drive)
    assert wrote[0].parent == drive / "literary-critic"
    # unreadable settings: beside first, the fallback once Windows refuses
    refused = PermissionError(13, "denied")
    refused.winerror = 5  # type: ignore[attr-defined,unused-ignore]
    calls: list[Path] = []

    def run(root: Path) -> dict[str, object]:
        calls.append(root)
        if len(calls) == 1:
            raise refused
        return {"status": "ready"}

    grant = folders.Grant([])
    novel = novels["Documents"]
    out = folders.with_state_place(grant, novel, run, lambda: None, home, None)
    assert calls == [novel / "literary-critic", home / "literary-critic" / "novel"]
    assert grant.state_root(novel) == calls[1]
    assert out["state_place"]["kind"] == "fallback"  # type: ignore[index]


def test_state_place_cfa_off_beside_novel(tmp_path: Path) -> None:
    home, drive, novels = _layouts(tmp_path)
    for status in (cfa.Status(False), cfa.Status(False, (str(novels["outside"]),))):
        for layout, novel in novels.items():
            grant = folders.Grant([str(novel.parent)])
            out, wrote = _place(grant, novel, status, home, drive)
            assert wrote == [novel / "literary-critic"], layout
            assert out["state_place"]["kind"] == "beside"  # type: ignore[index]
            assert "say" not in out["state_place"]  # type: ignore[operator]
            shutil.rmtree(wrote[0])
            folders.state_file().unlink(missing_ok=True)


def test_cfa_read_parses_powershell() -> None:
    def fake(*_a: object, **_k: object) -> subprocess.CompletedProcess[bytes]:
        out = (
            b'{"EnableControlledFolderAccess":1,'
            b'"ControlledFolderAccessProtectedFolders":["D:/Books"]}'
        )
        return subprocess.CompletedProcess([], 0, out, b"")

    status = cfa.read(fake)
    assert status == cfa.Status(True, ("D:/Books",))
    audit = subprocess.CompletedProcess([], 0, b'{"EnableControlledFolderAccess":2}', b"")
    assert cfa.read(lambda *a, **k: audit) == cfa.Status(False)
