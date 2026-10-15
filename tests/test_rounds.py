import json
import shutil
from pathlib import Path

import pytest

from litcritic import codex, corpus, query, rounds
from litcritic import spans as spanlib
from litcritic.cli import main


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("ws")
    (root / "work.toml").write_text('slug = "ws"\nlanguage = "es"\n', encoding="utf-8")
    assert main(["ingest", str(corpus.get("marianela").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    codex.Codex.init(root, "v001")
    return root


@pytest.fixture
def ws(base: Path, tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    shutil.copytree(base, root)
    return root


def _span(root: Path, unit: str) -> spanlib.Span:
    ix = query.load(root)
    i = query.paragraph_range(ix, unit).start
    text = spanlib.Text(ix.paragraphs, ix.anchors, "v001")
    return spanlib.make(text, "v001", ix.anchors[i], 0, ix.anchors[i], len(ix.paragraphs[i]))


def _issues(root: Path) -> dict[str, str]:
    cx = codex.Codex(root)

    def issue(
        name: str, check: str, unit: str, sev: str, kind: str = "problem", **extra: object
    ) -> None:
        fields = {
            "level": "scene",
            "severity": sev,
            "check": check,
            "kind": kind,
            "confidence": 0.8,
            "effort": "M",
            "why": f"Explanation of {name}.",
            **extra,
        }
        ids[name] = cx.add("issue", f"Look at {name}", fields, [_span(root, unit)]).id

    ids: dict[str, str] = {}
    issue("F1", "scene-craft.purpose", "c04.s1", "high")
    issue("F2", "architecture.proportion", "c02.s1", "medium", options=["Cut", "Merge"])
    issue("F3", "architecture.proportion", "c09.s1", "high")
    issue("F4", "scene-craft.value-shift", "c01.s1", "high", kind="strength")
    issue("F9", "scene-craft.scene-inventory", "c05.s1", "high")
    return ids


def test_round_built_from_issue_items(ws: Path) -> None:
    with pytest.raises(rounds.RoundError, match="no open problem issues"):
        rounds.build(ws)
    ids = _issues(ws)
    out, actions, warnings = rounds.build(ws)
    assert out.name == "round.json" and out.parent.name == "round-01" and warnings == []
    assert [a["issue"] for a in actions] == [ids["F3"], ids["F2"]]  # high before medium
    assert actions[1]["options"] == ["Cut", "Merge"] and actions[0]["status"] == "pending"
    assert actions[0]["where"]["chapter"].startswith("9")
    st = rounds.status(ws)
    assert st["can_close"] is False
    assert [r["id"] for r in st["remaining"]] == [a["id"] for a in actions]
    assert st["remaining"][0]["where"]["chapter"].startswith("9")
    # Rebuilding before the letter and any decision replaces the round.
    _, again, _ = rounds.build(ws)
    assert [d.name for d in rounds.round_dirs(ws)] == ["round-01"]
    assert [a["id"] for a in again] == [a["id"] for a in actions]
    letter = rounds.letter(ws).read_text(encoding="utf-8")
    assert letter.startswith("# Ronda 1: estructura")
    assert "Lo que funciona" in letter and "Capítulo 9" in letter
    # A decision is a Codex item about the issue, and keeps it out of later rounds.
    assert rounds.mark(ws, actions[0]["id"], "rejected", "it is the point")["status"] == "rejected"
    cx = codex.Codex(ws)
    d = rounds.decision(cx, ids["F3"])
    assert d is not None and d.fields["verdict"] == "rejected"
    assert d.fields["reason"] == "it is the point" and d.fields["at"]
    assert [r["id"] for r in rounds.status(ws)["remaining"]] == [actions[1]["id"]]
    rounds.mark(ws, actions[1]["id"], "done")
    assert rounds.status(ws)["can_close"] is True
    assert rounds.status(ws)["remaining"] == []
    _, scene_round, _ = rounds.build(ws)
    assert [a["issue"] for a in scene_round] == [ids["F1"]]  # F9's check makes no action
    assert scene_round[0]["id"] == "A3" and scene_round[0]["round"] == 2
    with pytest.raises(rounds.RoundError, match="no open line"):
        rounds.build(ws, level="line")
    # Withdrawing a decision brings the issue back.
    rounds.mark(ws, actions[0]["id"], "pending")
    assert rounds.action_status(codex.Codex(ws), ids["F3"]) == "pending"
    for old in ("findings.json", "actions.json"):
        assert not list(ws.rglob(old))


def test_round_actions_follow_the_codex(ws: Path) -> None:
    ids = _issues(ws)
    rounds.build(ws)
    cx = codex.Codex(ws)
    cx.update(ids["F3"], text="Chapter 9 is too long for what it does")
    actions = rounds.round_actions(ws, rounds.latest_round(ws))
    assert actions[0]["what"] == "Chapter 9 is too long for what it does"


def test_round_cli(ws: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _issues(ws)
    w = ["--workspace", str(ws)]
    assert main(["round", "build", *w]) == 0
    assert main(["round", "mark", "--id", "A1", "--status", "done", *w]) == 0
    assert main(["round", "status", *w]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["by_status"]["done"] == 1
    assert main(["round", "mark", *w]) == 1


def test_round_with_a_letter_is_never_rebuilt(ws: Path) -> None:
    _issues(ws)
    rounds.build(ws)
    rounds.letter(ws)
    first = (ws / "revisions" / "round-01" / "round.json").read_text(encoding="utf-8")
    rounds.build(ws)  # the scene issue goes to a new round; round 1 keeps its numbering
    assert [d.name for d in rounds.round_dirs(ws)] == ["round-01", "round-02"]
    assert (ws / "revisions" / "round-01" / "round.json").read_text(encoding="utf-8") == first


def test_mark_refuses_an_issue_gone_from_the_codex(ws: Path) -> None:
    _issues(ws)
    _, actions, _ = rounds.build(ws)
    gone = actions[0]["issue"]
    f = ws / "codex" / "items" / "issue.jsonl"
    keep = [ln for ln in f.read_text(encoding="utf-8").splitlines() if gone not in ln]
    f.write_text("\n".join(keep) + "\n", encoding="utf-8")
    with pytest.raises(rounds.RoundError, match="not in the Codex"):
        rounds.mark(ws, actions[0]["id"], "done")
