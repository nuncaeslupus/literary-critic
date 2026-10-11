import json
import zipfile
from pathlib import Path

import pytest

from litcritic import pack, workspace
from litcritic.cli import main


def _ws(tmp_path: Path) -> Path:
    ws = workspace.create("novel", "Novel", "en", tmp_path / "home").root
    (ws / "text" / "v001.txt").write_text("One.\nTwo.\n", encoding="utf-8")
    return ws


def _edit(ws: Path, text: str) -> None:
    (ws / "log" / "session.md").write_text(text, encoding="utf-8")


def test_unpack_refuses_older_zip(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    old, _ = pack.pack(ws, tmp_path / "g1.zip")
    _edit(ws, "later work")
    new, manifest = pack.pack(ws, tmp_path / "g2.zip")
    assert manifest["generation"] == 2
    with pytest.raises(pack.PackError, match="older"):
        pack.unpack(old, ws)
    assert (ws / "log" / "session.md").read_text(encoding="utf-8") == "later work"
    assert pack.unpack(new, ws).action == "unchanged"
    assert pack.unpack(old, ws, force=True).action == "updated"
    assert not (ws / "log" / "session.md").exists()


def test_stale_overwrite_blocked_in_every_case(tmp_path: Path) -> None:
    """Gate stale_overwrite_blocked: each way of losing work is refused."""
    ws = _ws(tmp_path)
    z1, _ = pack.pack(ws, tmp_path / "a.zip")
    copy = tmp_path / "elsewhere"
    pack.unpack(z1, copy)
    _edit(copy, "session B")
    zb, _ = pack.pack(copy, tmp_path / "b.zip")  # generation 2 from the copy
    _edit(ws, "session A")
    za, _ = pack.pack(ws, tmp_path / "a2.zip")  # generation 2 from the original
    cases = []
    with pytest.raises(pack.PackError, match="both continue"):
        pack.unpack(zb, ws)  # diverged: same generation, different content
    cases.append(True)
    _edit(copy, "more B, not packed")
    _, _ = pack.pack(ws, tmp_path / "a3.zip")
    with pytest.raises(pack.PackError, match="changed since"):
        pack.unpack(tmp_path / "a3.zip", copy)  # newer zip, unsaved local edits
    cases.append(True)
    with pytest.raises(pack.PackError, match="older"):
        pack.unpack(z1, ws)
    cases.append(True)
    assert sum(cases) / 3 == 1.0
    assert za.exists()


def test_round_trip_and_new_target(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    z, manifest = pack.pack(ws)
    assert z.name == "novel-g001.zip"
    target = tmp_path / "restored"
    result = pack.unpack(z, target)
    assert (result.action, result.written) == ("created", len(manifest["files"]))
    assert (target / "text" / "v001.txt").read_text(encoding="utf-8") == "One.\nTwo.\n"
    _edit(target, "next session")
    z2, m2 = pack.pack(target, tmp_path / "next.zip")
    assert m2["generation"] == 2
    assert pack.unpack(z2, ws).action == "updated"
    assert (ws / "log" / "session.md").read_text(encoding="utf-8") == "next session"


def test_corrupt_or_unsafe_zips_rejected(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    z, _ = pack.pack(ws, tmp_path / "ok.zip")
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(z) as src, zipfile.ZipFile(bad, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            dst.writestr(name, b"tampered" if name == "text/v001.txt" else data)
    with pytest.raises(pack.PackError, match="checksum"):
        pack.read_zip(bad)
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr(pack.ZIP_MANIFEST, json.dumps({"generation": 1, "files": {"../x": "0"}}))
    with pytest.raises(pack.PackError, match="unsafe"):
        pack.read_zip(evil)
    plain = tmp_path / "plain.zip"
    with zipfile.ZipFile(plain, "w") as zf:
        zf.writestr("a.txt", "x")
    with pytest.raises(pack.PackError, match="manifest"):
        pack.read_zip(plain)


def test_cli_pack_unpack(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    out = tmp_path / "w.zip"
    assert main(["pack", "--workspace", str(ws), "--out", str(out)]) == 0
    assert main(["unpack", str(out), "--home", str(tmp_path / "other")]) == 0
    assert (tmp_path / "other" / "novel" / "workspace.toml").is_file()
    _edit(ws, "x")
    assert main(["pack", "--workspace", str(ws), "--out", str(tmp_path / "w2.zip")]) == 0
    assert main(["unpack", str(out), "--workspace", str(ws)]) == 1
