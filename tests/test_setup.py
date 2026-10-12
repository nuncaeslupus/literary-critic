import json
import os
import random
from pathlib import Path

import pytest
from docgen import docx

from litcritic import corpus, ingest, setup
from litcritic.cli import main


def _paras(name: str, n: int) -> list[tuple[str, bool]]:
    draft = ingest.read(corpus.get(name).path)
    return [(p.text, bool(p.heading)) for p in draft.paragraphs[:n]]


def _revise(paras: list[tuple[str, bool]], seed: int) -> list[tuple[str, bool]]:
    """Another draft: some paragraphs dropped, some words changed."""
    rng = random.Random(seed)
    out = []
    for text, heading in paras:
        if not heading and rng.random() < 0.1:
            continue
        words = text.split()
        if not heading and words and rng.random() < 0.3:
            words[rng.randrange(len(words))] = "cambiado"
        out.append((" ".join(words), heading))
    return out


def _put(folder: Path, name: str, data: bytes | str, day: int) -> Path:
    f = folder / name
    if isinstance(data, str):
        f.write_text(data, encoding="utf-8")
    else:
        f.write_bytes(data)
    ts = 1_760_000_000 + day * 86_400
    os.utime(f, (ts, ts))
    return f


def _novel_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "MyNovel"
    folder.mkdir()
    base = _paras("marianela", 220)
    _put(folder, "MyNovel_v1.docx", docx(_revise(base[:150], 1), seed=1), 1)
    _put(folder, "MyNovel_v2.docx", docx(_revise(base[:190], 2), seed=2), 5)
    v3 = docx(base, seed=3)
    _put(folder, "MyNovel_v3.docx", v3, 9)
    _put(folder, "Copy of MyNovel_v3.docx", v3, 10)
    _put(folder, "MyNovel_v3 (1).docx", v3, 11)
    _put(folder, "MyNovel backup.docx", docx(base[:200], seed=4), 12)
    md = "\n\n".join(t for t, _ in base)
    _put(folder, "MyNovel_v3.md", md, 13)  # an export: the .docx stays the manuscript
    _put(folder, "notes.docx", docx(_paras("jekyll-hyde", 60), seed=5), 14)
    _put(folder, "letter to agent.txt", "Dear agent,\n\nPlease find attached my novel.\n", 15)
    _put(folder, "~$MyNovel_v3.docx", b"lock", 15)
    return folder


EXPECTED = {
    "manuscript": "MyNovel/MyNovel_v3.docx",
    "versions": [
        "MyNovel/MyNovel_v3.md",
        "MyNovel/MyNovel backup.docx",
        "MyNovel/MyNovel_v3 (1).docx",
        "MyNovel/Copy of MyNovel_v3.docx",
        "MyNovel/MyNovel_v2.docx",
        "MyNovel/MyNovel_v1.docx",
    ],
    "others": ["MyNovel/letter to agent.txt", "MyNovel/notes.docx"],
}


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {str(f.relative_to(folder)): f.read_bytes() for f in folder.rglob("*") if f.is_file()}


def test_setup_picks_latest_draft_and_lists_versions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenarios = 0
    correct = 0
    # 1. drafts, copies, a backup, an export and unrelated documents
    folder = _novel_folder(tmp_path)
    assert main(["setup", "--folder", str(folder)]) == 0
    out = json.loads(capsys.readouterr().out)
    got = {
        "manuscript": out["manuscript"]["path"],
        "versions": [v["path"] for v in out["versions"]],
        "others": sorted(out["others"]),
    }
    scenarios += 1
    correct += got == EXPECTED
    assert got == EXPECTED
    assert out["status"] == "ready" and out["workspace"] == "MyNovel/literary-critic"
    assert out["language"] == "es" and out["version"] == "v001"
    assert out["environment"]["folder_writable"] and out["environment"]["word_lock"]
    assert (folder / "literary-critic" / "text" / "v001.txt").is_file()
    assert (folder / "literary-critic" / "index" / "v001" / "structure.json").is_file()
    # 2. drafts with no number: the newest one, whatever its name
    other = tmp_path / "Second"
    other.mkdir()
    base = _paras("jekyll-hyde", 120)
    _put(other, "final.docx", docx(_revise(base, 7), seed=7), 3)
    _put(other, "draft.docx", docx(base, seed=8), 4)
    found = setup.discover(other)
    scenarios += 1
    correct += found.manuscript.path.name == "draft.docx" and [
        f.path.name for f, _ in found.versions
    ] == ["final.docx"]
    # 3. only copies: the newest copy is the manuscript
    third = tmp_path / "Third"
    third.mkdir()
    _put(third, "Copy of Book.docx", docx(base, seed=9), 1)
    _put(third, "Book (1).docx", docx(base, seed=9), 2)
    found = setup.discover(third)
    scenarios += 1
    correct += found.manuscript.path.name == "Book (1).docx" and not found.others
    novel_discovery_accuracy = correct / scenarios
    assert novel_discovery_accuracy == 1.0


def test_setup_reuses_existing_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _novel_folder(tmp_path)
    assert main(["setup", "--folder", str(folder)]) == 0
    first = json.loads(capsys.readouterr().out)
    before = _snapshot(folder)
    assert main(["setup", "--folder", str(folder)]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second == first
    assert _snapshot(folder) == before
    # The writer saves a new draft: it is ingested into the same workspace.
    _put(folder, "MyNovel_v4.docx", docx(_revise(_paras("marianela", 220), 9), seed=6), 20)
    assert main(["setup", "--folder", str(folder)]) == 0
    third = json.loads(capsys.readouterr().out)
    assert third["manuscript"]["path"] == "MyNovel/MyNovel_v4.docx"
    assert third["version"] == "v002" and third["workspace"] == first["workspace"]


def test_setup_without_documents_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["setup", "--folder", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"
