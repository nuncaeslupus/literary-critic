"""`lc upgrade`: an old workspace moves onto doc-control's formats and loses nothing."""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pytest
import upgrade_fixture as uf

from litcritic import query, structure, upgrade
from litcritic import spans as spanlib
from litcritic.cli import main
from litcritic.codex import Codex

RESOLVED = ("ok", "moved")


def _snapshot(root: Path) -> dict[str, str]:
    """Every file of the workspace (the upgrade backups left out) and its hash."""
    return {
        f.relative_to(root).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(root.rglob("*"))
        if f.is_file() and f.relative_to(root).parts[0] != upgrade.BACKUP_DIR
    }


def _resolved(root: Path) -> dict[tuple[str, int], dict[str, Any]]:
    """(item, span number) -> span, for every span that resolves in its draft."""
    out = {}
    for f in (root / "codex" / "items").glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            for k, s in enumerate(item["spans"]):
                if s["state"] in RESOLVED:
                    out[(item["id"], k)] = s
    return out


def _lines(f: Path) -> list[str]:
    return f.read_text(encoding="utf-8").split("\n")[:-1]


def _check_in_place(root: Path) -> None:
    """Every resolved span's quote is the text at its position in the upgraded draft."""
    cx = Codex(root)
    texts: dict[str, spanlib.Text] = {}
    for item in cx.items.values():
        for s in item.spans:
            if s.state not in RESOLVED:
                continue
            if s.draft not in texts:
                ix = query.load(root, s.draft, codex=False)
                texts[s.draft] = spanlib.Text(ix.paragraphs, ix.anchors, s.draft)
            t = texts[s.draft]
            g0, g1 = t.gpos(s.start.para, s.start.off), t.gpos(s.end.para, s.end.off)
            assert spanlib.matches(s, t.joined, g0, g1), (item.id, s.start, s.end)


def _drift(root: Path, version: str) -> None:
    """Make the old text differ from what doc-control reads: one extra paragraph that
    the old reader kept (a stray line between two paragraphs no span covers)."""
    text = root / "text" / f"{version}.txt"
    s_file = root / "index" / version / "structure.json"
    paras, data = _lines(text), json.loads(s_file.read_text(encoding="utf-8"))
    at = len(paras) // 2
    paras.insert(at, "12")
    data["paragraphs"].insert(at, ["c99.s9.p999", structure.fingerprint("12")])
    text.write_text("".join(p + "\n" for p in paras), encoding="utf-8")
    s_file.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize(
    ("slug", "drift"), [("jekyll-hyde", False), ("marianela", False), ("jekyll-hyde", True)]
)
def test_upgrade_keeps_every_resolved_span(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], slug: str, drift: bool
) -> None:
    root = uf.unpack(slug, tmp_path)
    if drift:
        _drift(root, "v002")
    writer = tmp_path / "writer" / "novel.docx"  # the writer's own file, outside the workspace
    writer.parent.mkdir()
    writer.write_bytes(next((root / "manuscript").glob("v001.*")).read_bytes())
    (root / "state").mkdir()
    (root / "state" / "documents.json").write_text(
        json.dumps({str(writer): {"path": str(writer), "sha256": "x", "seq": 1}}), "utf-8"
    )
    before = _resolved(root)
    manuscripts = {p.name: p.read_bytes() for p in (root / "manuscript").iterdir()}
    assert before, "the fixture has spans"

    t0 = time.perf_counter()
    assert main(["upgrade", "--workspace", str(root)]) == 0
    seconds = time.perf_counter() - t0
    out = capsys.readouterr().out
    assert "lost on upgrade: 0" in out, out

    after = _resolved(root)
    lost = sorted(set(before) - set(after))
    assert lost == [], f"codex_spans_lost_on_upgrade = {len(lost)}: {lost[:5]}"
    _check_in_place(root)
    for v in ("v001", "v002"):
        meta = json.loads((root / "text" / f"{v}.meta.json").read_text(encoding="utf-8"))
        assert meta["schema_version"] == 2 and all(r["at"] for r in meta["paragraphs"])
        s = json.loads((root / "index" / v / "structure.json").read_text(encoding="utf-8"))
        assert s["schema_version"] == 2
    overrides = json.loads((root / "analysis" / "structure-overrides.json").read_text("utf-8"))
    assert overrides["schema_version"] == 2 and len(overrides["overrides"]) == 2
    assert not (root / "backups").exists()
    assert (root / "analysis" / "upgrade-report.md").is_file()
    assert Codex(root).check() == []
    # Only snapshots are read: the snapshots and the writer's file are untouched.
    assert {p.name: p.read_bytes() for p in (root / "manuscript").iterdir()} == manuscripts
    assert sorted(p.name for p in writer.parent.iterdir()) == ["novel.docx"]
    assert seconds < 30


def test_upgrade_lists_unmatched_overrides(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = uf.unpack("jekyll-hyde", tmp_path)
    target = uf.override_targets("jekyll-hyde")["scene_start"]
    # The old reader saw this paragraph with other text, and the override named that text.
    changed = target.replace(" ", "  the ", 1)
    text = root / "text" / "v002.txt"
    paras = _lines(text)
    paras[paras.index(target)] = " ".join(changed.split())
    text.write_text("".join(p + "\n" for p in paras), encoding="utf-8")
    old_fp = structure.fingerprint(changed)
    f = root / "analysis" / "structure-overrides.json"
    data = json.loads(f.read_text(encoding="utf-8"))
    data["scene_starts"] = [old_fp]
    f.write_text(json.dumps(data), encoding="utf-8")

    assert main(["upgrade", "--workspace", str(root)]) == 1  # something for the writer
    assert "1 migrated, 1 to re-confirm" in capsys.readouterr().out
    migrated = json.loads(f.read_text(encoding="utf-8"))
    assert [o["action"] for o in migrated["overrides"]] == ["deny"]
    assert [(u["key"], u["fp"], u["reason"]) for u in migrated["unconfirmed"]] == [
        ("scene_starts", old_fp, "missing")
    ]
    report = (root / "analysis" / "upgrade-report.md").read_text(encoding="utf-8")
    head = " ".join(changed.split()[:5])
    assert f"start a scene at the paragraph that begins «{head}»" in report
    assert "the paragraph changed or is gone" in report


def test_second_upgrade_changes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = uf.unpack("jekyll-hyde", tmp_path)
    assert main(["upgrade", "--workspace", str(root)]) == 0
    first = _snapshot(root)
    backups = upgrade.backups(root)
    capsys.readouterr()
    assert main(["upgrade", "--workspace", str(root)]) == 0
    assert "already up to date" in capsys.readouterr().out
    assert _snapshot(root) == first
    assert upgrade.backups(root) == backups and len(backups) == 1
    assert upgrade.needed(root) == []


def test_restore_puts_the_old_workspace_back(tmp_path: Path) -> None:
    root = uf.unpack("marianela", tmp_path)
    old = _snapshot(root)
    assert upgrade.needed(root)
    assert main(["upgrade", "--workspace", str(root)]) == 0
    assert _snapshot(root) != old
    assert main(["upgrade", "--workspace", str(root), "--restore"]) == 0
    assert _snapshot(root) == old
    assert upgrade.needed(root)


def test_failed_upgrade_restores_the_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = uf.unpack("jekyll-hyde", tmp_path)
    old = _snapshot(root)

    def boom(*_: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(upgrade, "_reanchor", boom)
    with pytest.raises(upgrade.UpgradeError, match="restored"):
        upgrade.upgrade(root)
    assert _snapshot(root) == old


def test_damaged_backup_is_not_restored(tmp_path: Path) -> None:
    root = uf.unpack("jekyll-hyde", tmp_path)
    assert main(["upgrade", "--workspace", str(root)]) == 0
    now = _snapshot(root)
    b = upgrade.backups(root)[-1]
    (b / "text" / "v001.txt").write_text("damaged", encoding="utf-8")
    with pytest.raises(upgrade.UpgradeError, match="damaged"):
        upgrade.restore(root)
    assert _snapshot(root) == now


# Invented placeholder text: one paragraph per line, an empty line between paragraphs,
# a wider gap before each chapter, and a paragraph with a double space in it.
LINES_DRAFT = (
    "The Placeholder\n\n\n\n"
    "Chapter One\n\n"
    "Ana opened the door and  looked at the empty street.\n\n"
    "Nobody was there, only the wind in the trees.\n\n"
    "She went back inside and sat down to wait.\n\n\n\n"
    "Chapter Two\n\n"
    "The morning came slowly over the roofs of the town.\n\n"
    "Ana made coffee and read the letter again.\n"
)


def test_text_drafts_read_through_a_converted_copy_are_readdressed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A .txt ingested by the release that converted it to a .docx first: doc-control
    now reads the file itself, so its raw text gives other addresses; the
    upgrade reads it again, says so, and moves overrides and Codex spans along."""
    from litcritic import convert, ingest, workspace

    root = workspace.create("w", "W", "en", tmp_path / "home").root
    src = tmp_path / "draft.txt"
    src.write_text(LINES_DRAFT, encoding="utf-8")
    assert main(["ingest", str(src), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    now = ingest.read(src)
    # What that release read: one paragraph per line, through a converted .docx copy.
    old_lines = [ingest.Para(line) for line in LINES_DRAFT.split("\n")]
    old_docx = convert.draft_to_docx(ingest.Draft(ingest._collect(old_lines), "txt"))
    old = ingest.read(Path("old.docx"), old_docx)
    assert [p.text for p in old.paragraphs] == [p.text for p in now.paragraphs]
    assert [p.at for p in old.paragraphs] != [p.at for p in now.paragraphs]
    meta_file = root / "text" / "v001.meta.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    del meta["source"]
    meta["notes"], meta["paragraphs"] = [], [p.meta() for p in old.paragraphs]
    meta_file.write_text(json.dumps(meta), encoding="utf-8")
    k = next(i for i, p in enumerate(now.paragraphs) if "door" in p.text)
    old_fp, new_fp = old.paragraphs[k].at.split("#")[1], now.paragraphs[k].at.split("#")[1]
    assert old_fp != new_fp  # the double space: raw text now, cleaned text then
    forced = {"fp": old_fp, "kind": "scene", "action": "force"}
    (root / "analysis").mkdir(exist_ok=True)
    (root / "analysis" / "structure-overrides.json").write_text(
        json.dumps({"schema_version": 2, "overrides": [forced]}), "utf-8"
    )
    cx = Codex.init(root, "v001")
    ix = query.load(root, "v001", codex=False)
    text = spanlib.Text(ix.paragraphs, ix.anchors, "v001")
    j = k + 1
    span = spanlib.make(text, "v001", ix.anchors[j], 0, ix.anchors[j], len(ix.paragraphs[j]))
    item = cx.add("issue", "Slow.", {"level": "line", "severity": "low"}, [span])

    assert "text/v001.meta.json" in upgrade.needed(root)
    with pytest.raises(ValueError, match="lc upgrade"):
        structure.build(root)
    capsys.readouterr()
    assert main(["upgrade", "--workspace", str(root)]) == 0
    out = capsys.readouterr().out
    n = len(now.paragraphs)
    assert f"v001: re-read ({n} -> {n} paragraphs); " in out
    assert "paragraph addresses changed" in out
    assert "overrides: 1 moved to their paragraph's new address" in out
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    assert meta["source"] == now.source and now.source["mode"] == "lines"
    assert [r["at"] for r in meta["paragraphs"]] == [p.at for p in now.paragraphs]
    saved = json.loads((root / "analysis" / "structure-overrides.json").read_text("utf-8"))
    assert saved["overrides"] == [{**forced, "fp": new_fp}]
    _, _, errors = structure.build(root)
    assert errors == []
    assert Codex(root).items[item.id].spans[0].state in RESOLVED
    _check_in_place(root)
    assert upgrade.needed(root) == []
