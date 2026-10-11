import json
from pathlib import Path

import pytest

from litcritic import corpus, locate, query, rounds
from litcritic.cli import main


@pytest.fixture(scope="module")
def ws(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("ws")
    (root / "work.toml").write_text('slug = "ws"\nlanguage = "es"\n', encoding="utf-8")
    assert main(["ingest", str(corpus.get("marianela").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    return root


def writer_locators_complete(ix: query.Index) -> float:
    builder = locate.LocatorBuilder(ix)
    text = "\n".join(ix.paragraphs)
    complete = 0
    sample = [a for a in ix.anchors if len(ix.paragraphs[ix.anchors.index(a)].split()) >= 8][::5]
    for a in sample:
        loc = builder.locate(a)
        ok = (
            loc.chapter
            and loc.page > 0
            and text.count(loc.first_words) == 1
            and text.count(loc.last_words) == 1
            and ix.paragraphs[ix.anchors.index(a)].startswith(loc.first_words)
            and ix.paragraphs[ix.anchors.index(a)].endswith(loc.last_words)
        )
        complete += bool(ok)
    return complete / len(sample)


def test_locator_first_last_words_unique(ws: Path) -> None:
    assert writer_locators_complete(query.load(ws)) == 1.0


def test_describe_and_pages(ws: Path) -> None:
    ix = query.load(ws)
    loc = locate.LocatorBuilder(ix).locate("c03.s1.p2")
    assert loc.chapter.startswith("3 (-III-") and loc.page > 1 and not loc.page_exact
    line = locate.describe(loc, "es")
    assert line.startswith("Capítulo 3") and "pág. ≈" in line and "«" in line
    assert locate.describe(loc, "en").startswith("Chapter 3")
    meta = [{"page": 7} for _ in ix.paragraphs]
    assert locate.LocatorBuilder(ix, meta).locate("c03.s1.p2").page == 7


def _findings() -> list[dict[str, object]]:
    def f(fid: str, check: str, anchor: str, sev: str, kind: str = "problem") -> dict[str, object]:
        return {
            "schema_version": 1,
            "id": fid,
            "check_id": check,
            "anchors": [anchor],
            "evidence": [{"anchor": anchor + ".p1", "quote": "x"}],
            "explanation": f"Explanation of {fid}.",
            "severity": sev,
            "confidence": 0.8,
            "effort": "M",
            "kind": kind,
            "status": "open",
        }

    return [
        f("F1", "scene-craft.purpose", "c04.s1", "high"),
        f("F2", "architecture.proportion", "c02.s1", "medium")
        | {"what": "Shorten chapter 2", "options": ["Cut", "Merge"]},
        f("F3", "architecture.proportion", "c09.s1", "high"),
        f("F4", "scene-craft.value-shift", "c01.s1", "high", kind="strength"),
    ]


def test_rounds_build_letter_mark_status(ws: Path) -> None:
    (ws / "analysis").mkdir(exist_ok=True)
    with pytest.raises(rounds.RoundError):
        rounds.build(ws)
    (ws / "analysis" / "findings.json").write_text(json.dumps(_findings()), encoding="utf-8")
    out, actions, warnings = rounds.build(ws)
    assert out.parent.name == "round-01" and warnings == []
    assert [a["level"] for a in actions] == ["structural", "structural"]
    assert [a["finding_ids"] for a in actions] == [["F3"], ["F2"]]  # high before medium
    assert actions[1]["what"] == "Shorten chapter 2" and actions[1]["options"] == ["Cut", "Merge"]
    assert actions[0]["where"]["first_words"] and actions[0]["where"]["chapter"].startswith("9")
    letter = rounds.letter(ws).read_text(encoding="utf-8")
    assert letter.startswith("# Ronda 1: estructura")
    assert "Lo que funciona" in letter and "Capítulo 9" in letter
    assert rounds.status(ws)["can_close"] is False
    assert rounds.mark(ws, actions[0]["id"], "done")["status"] == "done"
    assert rounds.status(ws)["can_close"] is True
    _, second, _ = rounds.build(ws, level="scene")
    assert second[0]["id"] == "A3" and second[0]["round"] == 2


def test_prose_in_actions_is_flagged() -> None:
    long_quote = "«" + " ".join(["palabra"] * 20) + "»"
    action = {"id": "A1", "what": "x", "why": f"Write it like {long_quote}", "options": []}
    assert rounds.prose_flags(action, "texto del libro")
    assert not rounds.prose_flags(action, " ".join(["palabra"] * 20))


def test_cli_locate_and_round(ws: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["locate", "c02.s1.p3", "--workspace", str(ws)]) == 0
    assert capsys.readouterr().out.startswith("Capítulo 2")
    assert main(["locate", "c02.s1.p3", "--workspace", str(ws), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["anchor"] == "c02.s1.p3"
    assert main(["round", "status", "--workspace", str(ws)]) in (0, 1)
    assert main(["round", "mark", "--workspace", str(ws)]) == 1


def test_short_paragraph_points_to_its_neighbour() -> None:
    ix = query.Index(
        ["Una frase larga y única para empezar aquí.", "—Sí.", "Otra cosa distinta.", "—Sí."],
        ["c01.s1.p1", "c01.s1.p2", "c01.s1.p3", "c01.s1.p4"],
        ["a", "b", "c", "d"],
        [],
        {},
        {},
    )
    loc = locate.LocatorBuilder(ix).locate("c01.s1.p4")
    assert not loc.unique and loc.after == "Otra cosa distinta."
    assert "justo después del que empieza «Otra cosa distinta.…»" in locate.describe(loc, "es")


def test_round_lifecycle_regressions(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "work.toml").write_text('slug = "ws"\nlanguage = "es"\n', encoding="utf-8")
    assert main(["ingest", str(corpus.get("marianela").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    (root / "analysis").mkdir()
    findings = _findings()
    inventory = dict(findings[0]) | {"id": "F9", "check_id": "scene-craft.scene-inventory"}
    (root / "analysis" / "findings.json").write_text(json.dumps([*findings, inventory]))
    _, first, _ = rounds.build(root)
    # Rebuilding before anything is decided replaces the round instead of adding one.
    _, again, _ = rounds.build(root)
    assert [d.name for d in rounds.round_dirs(root)] == ["round-01"]
    assert [a["id"] for a in again] == [a["id"] for a in first]
    # A decision is mirrored on the finding and keeps it out of later rounds.
    rounds.mark(root, first[0]["id"], "done")
    saved = json.loads((root / "analysis" / "findings.json").read_text(encoding="utf-8"))
    assert next(f for f in saved if f["id"] == "F3")["status"] == "resolved"
    _, scene_round, _ = rounds.build(root)
    ids = {fid for a in scene_round for fid in a["finding_ids"]}
    assert "F3" not in ids and "F9" not in ids  # decided; and a no-action check
    with pytest.raises(rounds.RoundError, match="no open line"):
        rounds.build(root, level="line")
    # The letter quotes the places stored with the actions.
    text = rounds.letter(root).read_text(encoding="utf-8")
    assert all(a["where"]["first_words"] in text for a in scene_round)
    # Spanish labels in locators.
    ix = query.load(root)
    assert locate.LocatorBuilder(ix, lang="es").locate("c00.s1.p1").chapter == "preliminares"
