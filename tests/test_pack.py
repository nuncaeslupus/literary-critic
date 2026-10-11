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
    refused = 0
    ws = _ws(tmp_path)
    z1, _ = pack.pack(ws, tmp_path / "a1.zip")
    other = tmp_path / "b"
    pack.unpack(z1, other)
    # 1. Older zip over newer work.
    _edit(ws, "A1")
    pack.pack(ws, tmp_path / "a2.zip")
    with pytest.raises(pack.PackError, match="older"):
        pack.unpack(z1, ws)
    refused += 1
    # 2. Diverged at the same generation.
    _edit(other, "B1")
    zb, _ = pack.pack(other, tmp_path / "b2.zip")
    with pytest.raises(pack.PackError, match="separate ways"):
        pack.unpack(zb, ws)
    refused += 1
    # 3. Diverged at different generations (A packed twice, B once).
    _edit(ws, "A2")
    za3, m3 = pack.pack(ws, tmp_path / "a3.zip")
    assert m3["generation"] == 3
    with pytest.raises(pack.PackError, match="separate ways"):
        pack.unpack(za3, other)
    refused += 1
    # 4. Newer zip of the same line over unsaved local changes.
    third = tmp_path / "c"
    pack.unpack(za3, third)
    _edit(ws, "A3")
    za4, _ = pack.pack(ws, tmp_path / "a4.zip")
    _edit(third, "C unsaved")
    with pytest.raises(pack.PackError, match="changed since"):
        pack.unpack(za4, third)
    refused += 1
    assert refused / 4 == 1.0
    # A clean fast-forward goes through.
    fourth = tmp_path / "d"
    pack.unpack(za3, fourth)
    assert pack.unpack(za4, fourth).action == "updated"


def test_force_makes_an_exact_copy(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    z1, _ = pack.pack(ws, tmp_path / "g1.zip")
    (ws / "analysis" / "new.md").write_text("local only", encoding="utf-8")
    pack.pack(ws, tmp_path / "g2.zip")
    (ws / "analysis" / "extra.md").write_text("unsaved", encoding="utf-8")
    result = pack.unpack(z1, ws, force=True)
    assert result.action == "updated" and result.removed == 2
    assert not (ws / "analysis" / "new.md").exists()
    assert pack.unpack(z1, ws).action == "unchanged"


def test_failed_pack_leaves_state_alone(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    with pytest.raises(OSError):
        pack.pack(ws, tmp_path / "missing-dir" / "x.zip")
    assert not (ws / pack.STATE).exists()


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
        zf.writestr(
            pack.ZIP_MANIFEST, json.dumps({"generation": 1, "slug": "e", "files": {"../x": "0"}})
        )
    with pytest.raises(pack.PackError, match="unsafe"):
        pack.read_zip(evil)
    plain = tmp_path / "plain.zip"
    with zipfile.ZipFile(plain, "w") as zf:
        zf.writestr("a.txt", "x")
    with pytest.raises(pack.PackError, match="manifest"):
        pack.read_zip(plain)
    for manifest in ("{not json", '{"files": [], "slug": "x", "generation": 1}'):
        damaged = tmp_path / "damaged.zip"
        with zipfile.ZipFile(damaged, "w") as zf:
            zf.writestr(pack.ZIP_MANIFEST, manifest)
        with pytest.raises(pack.PackError, match="damaged"):
            pack.read_zip(damaged)
    for slug in ("../../x", "/tmp/x"):
        crafted = tmp_path / "crafted.zip"
        with zipfile.ZipFile(crafted, "w") as zf:
            zf.writestr(pack.ZIP_MANIFEST, json.dumps({"files": {}, "slug": slug, "generation": 1}))
        with pytest.raises(pack.PackError, match="unsafe workspace name"):
            pack.read_zip(crafted)
    assert not pack._safe("..\\..\\evil.txt") and not pack._safe("C:evil.txt")
    assert pack._safe("text/v001.txt")


def test_cli_pack_unpack(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    out = tmp_path / "w.zip"
    assert main(["pack", "--workspace", str(ws), "--out", str(out)]) == 0
    assert main(["unpack", str(out), "--home", str(tmp_path / "other")]) == 0
    assert (tmp_path / "other" / "novel" / "work.toml").is_file()
    _edit(ws, "x")
    assert main(["pack", "--workspace", str(ws), "--out", str(tmp_path / "w2.zip")]) == 0
    assert main(["unpack", str(out), "--workspace", str(ws)]) == 1
    assert main(["unpack", str(out), "--workspace", "renamed", "--home", str(tmp_path / "h")]) == 0
    assert (tmp_path / "h" / "renamed" / "work.toml").is_file()
