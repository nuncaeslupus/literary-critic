"""Chapters and scenes from doc-control's ``segment``, measured on the corpus."""

import json
from pathlib import Path
from typing import Any

import pytest

from litcritic import corpus, structure
from litcritic.cli import main

GOLD = Path(__file__).parent / "fixtures" / "gold" / "chapters.json"
LANGUAGE = {"jekyll-hyde": "en", "marianela": "es"}


def _workspace(tmp_path: Path, language: str) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    (ws / "work.toml").write_text(f'slug = "ws"\nlanguage = "{language}"\n', encoding="utf-8")
    return ws


def _indexed(ws: Path, source: Path) -> dict[str, Any]:
    assert main(["ingest", str(source), "--workspace", str(ws)]) == 0
    assert main(["anchor", "--workspace", str(ws)]) == 0
    data: dict[str, Any] = json.loads(
        (ws / "index" / "v001" / "structure.json").read_text(encoding="utf-8")
    )
    return data


def _gold_starts(paragraphs: list[str], headings: list[str]) -> set[int]:
    """The paragraph holding each gold heading, found in order."""
    starts: set[int] = set()
    at = 0
    for heading in headings:
        at = paragraphs.index(heading, at)
        starts.add(at)
        at += 1
    return starts


def chapter_boundary_f1(tmp_path: Path, slug: str) -> tuple[float, set[int], set[int]]:
    """F1 of detected chapter starts against the gold chapters of a corpus text."""
    data = _indexed(_workspace(tmp_path / slug, LANGUAGE[slug]), corpus.get(slug).path)
    text = (tmp_path / slug / "ws" / "text" / "v001.txt").read_text(encoding="utf-8")
    paragraphs = text.split("\n")[:-1]
    gold = _gold_starts(paragraphs, json.loads(GOLD.read_text(encoding="utf-8"))[slug])
    got = {c["start"] for c in data["chapters"] if c["reason"] != "front"}
    tp = len(gold & got)
    f1 = 2 * tp / (len(gold) + len(got)) if gold or got else 1.0
    return f1, gold, got


@pytest.mark.parametrize("slug", ["jekyll-hyde", "marianela"])
def test_corpus_chapters_match_gold(tmp_path: Path, slug: str) -> None:
    f1, gold, got = chapter_boundary_f1(tmp_path, slug)
    assert f1 >= 0.99, sorted(gold ^ got)


def _overrides(ws: Path, items: list[dict[str, Any]]) -> None:
    (ws / "analysis").mkdir(exist_ok=True)
    (ws / "analysis" / "structure-overrides.json").write_text(
        json.dumps({"schema_version": 2, "overrides": items}), encoding="utf-8"
    )


def _fp(ws: Path, text: str) -> str:
    meta = json.loads((ws / "text" / "v001.meta.json").read_text(encoding="utf-8"))
    paragraphs = (ws / "text" / "v001.txt").read_text(encoding="utf-8").split("\n")
    at: str = meta["paragraphs"][paragraphs.index(text)]["at"]
    return at.split("#")[1]


def test_override_forces_and_denies_chapter(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = "Una frase de relleno para el capítulo. " * 30
    src = tmp_path / "draft.txt"
    src.write_text(
        f"Capítulo 1\n\n{body}\n\nInterludio\n\n{body}\n\nCapítulo 2\n\n{body}\n\n"
        f"Capítulo 3\n\n{body}\n",
        encoding="utf-8",
    )
    ws = _workspace(tmp_path, "es")
    data = _indexed(ws, src)
    assert [c["title"] for c in data["chapters"]] == ["Capítulo 1", "Capítulo 2", "Capítulo 3"]

    _overrides(
        ws,
        [
            {"fp": _fp(ws, "Interludio"), "kind": "chapter", "action": "force"},
            {"fp": _fp(ws, "Capítulo 2"), "kind": "chapter", "action": "deny"},
        ],
    )
    assert main(["anchor", "--workspace", str(ws)]) == 0
    data = json.loads((ws / "index" / "v001" / "structure.json").read_text(encoding="utf-8"))
    assert [c["title"] for c in data["chapters"]] == ["Capítulo 1", "Interludio", "Capítulo 3"]
    assert [c["id"] for c in data["chapters"]] == ["c01", "c02", "c03"]
    forced = data["chapters"][1]
    assert forced["reason"] == "override" and forced["stable_id"].startswith("ch-")
    assert data["paragraphs"][4][0] == "c02.s1.p2"  # "Capítulo 2" is now body text

    _overrides(ws, [{"fp": "0badf00d", "kind": "chapter", "action": "force"}])
    assert main(["anchor", "--workspace", str(ws)]) == 1
    assert "no paragraph has this fingerprint" in capsys.readouterr().err


def test_legacy_overrides_are_translated(tmp_path: Path) -> None:
    body = "x " * 200
    s = structure.detect(["CHAPTER ONE", body, "Interlude", body, "CHAPTER TWO", body])
    assert [c.title for c in s.chapters] == ["CHAPTER ONE", "CHAPTER TWO"]
    ws = tmp_path / "ws"
    (ws / "analysis").mkdir(parents=True)
    paragraphs = ["Uno", "Dos", "Dos"]
    ats = ["p1#00000001", "p3#00000002", "p5#00000002"]
    fp = structure.fingerprint
    f = ws / "analysis" / "structure-overrides.json"
    f.write_text(json.dumps({"chapter_starts": [fp("Uno")], "not_scene": [fp("Uno")]}))
    assert structure.load_overrides(ws, paragraphs, ats) == (
        [
            {"fp": "00000001", "kind": "chapter", "action": "force"},
            {"fp": "00000001", "kind": "scene", "action": "deny"},
        ],
        [],
    )
    f.write_text(json.dumps({"chapter_starts": [fp("Dos")], "bogus": []}))
    assert structure.load_overrides(ws, paragraphs, ats) == (
        [],
        ["unknown key 'bogus'", f"chapter_starts: {fp('Dos')} matches 2 paragraphs"],
    )
    f.write_text("[]")
    assert structure.load_overrides(ws, paragraphs, ats)[1] == ["overrides must be a JSON object"]


def test_structure_json_records_doc_control_ids_and_signals(tmp_path: Path) -> None:
    data = _indexed(_workspace(tmp_path, "es"), corpus.get("marianela").path)
    assert data["schema_version"] == 2
    first = data["chapters"][1]
    assert first["id"] == "c01" and first["title"] == "-I-"
    assert first["stable_id"].startswith("ch-") and "heading_style" in first["signals"]
    scene = first["scenes"][0]
    assert scene["id"] == "c01.s1" and scene["stable_id"].startswith("sc-")
    assert scene["signals"] == ["chapter_start"]
    assert data["chapters"][0]["reason"] == "front" and data["chapters"][0]["stable_id"] == ""


def test_old_meta_asks_for_a_new_ingest(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "en")
    _indexed(ws, corpus.get("jekyll-hyde").path)
    meta_file = ws / "text" / "v001.meta.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    for row in meta["paragraphs"]:
        row.pop("at")
    meta_file.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="ingest"):
        structure.build(ws)
