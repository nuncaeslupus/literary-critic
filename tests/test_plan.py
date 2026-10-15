import json
import random
import shutil
from pathlib import Path
from typing import Any

import pytest

from litcritic import codex, corpus, plan, query, rounds, workspace
from litcritic import spans as spanlib
from litcritic.cli import main


def _work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(workspace.REGISTRY_ENV, str(tmp_path / "workspaces.txt"))
    novel = tmp_path / "Novel"
    novel.mkdir()
    ws = workspace.create("novel", "Novel", "en", base=novel, folder="literary-critic")
    workspace.register(ws.root)
    return ws.root


def _run(root: Path, capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any]]:
    code = main(["plan", *argv, "--workspace", str(root)])
    return code, json.loads(capsys.readouterr().out)


def _log_bytes(root: Path) -> bytes:
    f = plan.log_path(root)
    return f.read_bytes() if f.exists() else b""


def _part_in(root: Path, status: str) -> str:
    """A new part in ``status``, reached only through the commands."""
    by = "tool" if status == "proposed" else "writer"
    state, _ev = plan.add(root, "aspect", f"a {status} part", by)
    pid = str(state["parts"][-1]["id"])
    if status in ("active", "done"):
        plan.transition(root, "start", pid, "writer")
    if status == "done":
        plan.transition(root, "done", pid, "writer")
    if status == "skipped":
        plan.transition(root, "skip", pid, "writer", "not now")
    return pid


def test_plan_transition_matrix_refuses_every_invalid_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _work(tmp_path, monkeypatch)
    assert _run(root, capsys, "init", "--mode", "iterative")[0] == 0
    accepted = 0
    for status in plan.STATUSES:
        for cmd, (_ev, sources, _target) in plan.COMMANDS.items():
            for p in plan.load_state(root)["parts"]:
                if p["status"] == "active":
                    plan.transition(root, "done", p["id"], "writer")
            pid = _part_in(root, status)
            before = _log_bytes(root)
            code, out = _run(root, capsys, cmd, pid, "--by", "writer", "--reason", "because")
            if status in sources:
                assert code == 0, (status, cmd, out)
                continue
            assert code == 1, (status, cmd, out)
            assert out["status"] == "refused" and out["reason"] == "transition"
            assert _log_bytes(root) == before
            accepted += code == 0
    assert accepted == 0  # invalid_transitions_accepted == 0


def test_plan_refusals_write_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _work(tmp_path, monkeypatch)
    code, out = _run(root, capsys, "add", "--kind", "aspect", "--title", "x", "--by", "writer")
    assert (code, out["reason"]) == (1, "no_plan")
    _run(root, capsys, "init", "--mode", "report")
    assert _run(root, capsys, "init", "--mode", "report")[1]["reason"] == "already_initialized"
    p1 = _part_in(root, "todo")
    p2 = _part_in(root, "todo")
    before = _log_bytes(root)
    cases = [
        (("start", p1), "missing_by"),
        (("skip", p1, "--by", "writer"), "missing_reason"),
        (("skip", p1, "--by", "writer", "--reason", "  "), "missing_reason"),
        (("reopen", "P99", "--by", "writer", "--reason", "r"), "unknown_part"),
        (("move", p1, "--after", "P99", "--by", "writer"), "unknown_part"),
        (("edit", p1, "--by", "writer"), "invalid"),
    ]
    for argv, reason in cases:
        code, out = _run(root, capsys, *argv)
        assert (code, out["reason"]) == (1, reason), argv
    assert _log_bytes(root) == before
    assert _run(root, capsys, "start", p1, "--by", "writer")[0] == 0
    code, out = _run(root, capsys, "start", p2, "--by", "writer")
    assert (code, out["reason"]) == (1, "one_active")
    assert len(_log_bytes(root).splitlines()) == len(before.splitlines()) + 1


def test_plan_init_seeds_parts_from_the_profile_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _work(tmp_path, monkeypatch)
    code, out = _run(root, capsys, "status")
    assert code == 0 and out["status"] == "no_plan" and not plan.log_path(root).exists()
    (root / "analysis").mkdir(exist_ok=True)
    (root / "analysis" / "profile.toml").write_text(
        'mode = "reader-report"\nlanguage = "en"\n', encoding="utf-8"
    )
    code, out = _run(root, capsys, "init")
    assert code == 0 and out["mode"] == "report"
    assert [p["kind"] for p in out["parts"]] == ["checks", "report"]
    assert {p["status"] for p in out["parts"]} == {"proposed"}
    code, out = _run(root, capsys, "status")
    assert out["by_status"] == {"proposed": 2} and out["active"] is None


def test_plan_add_move_edit_next_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _work(tmp_path, monkeypatch)
    _run(root, capsys, "init", "--mode", "iterative")
    add = ["add", "--by", "writer"]
    code, out = _run(
        root, capsys, *add, "--kind", "aspect", "--title", "the dialogue",
        "--refs-json", '{"area": "dialogue"}',
    )  # fmt: skip
    assert code == 0 and out["part"]["status"] == "todo" and out["part"]["id"] == "P2"
    assert out["part"]["refs"] == {"area": "dialogue"}
    _run(root, capsys, *add, "--kind", "new-draft", "--title", "d2", "--after", "P1")
    ids = [p["id"] for p in plan.load_state(root)["parts"]]
    assert ids == ["P1", "P3", "P2"]
    _run(root, capsys, "move", "P2", "--by", "writer", "--after", "P1")
    ids = [p["id"] for p in plan.load_state(root)["parts"]]
    assert ids == ["P1", "P2", "P3"]
    _run(root, capsys, "move", "P3", "--by", "writer")
    parts = plan.load_state(root)["parts"]
    assert [p["order"] for p in parts] == [1, 2, 3] and parts[0]["id"] == "P3"
    code, out = _run(root, capsys, "edit", "P2", "--by", "writer", "--title", "first dialogues")
    assert out["part"]["title"] == "first dialogues"
    code, out = _run(root, capsys, "next")
    assert out["part"]["id"] == "P3" and out["command"] is None
    _run(root, capsys, "start", "P3", "--by", "writer")
    _run(root, capsys, "skip", "P2", "--by", "writer", "--reason", "later")
    code, out = _run(root, capsys, "status", "--timeline", "2")
    assert out["active"]["id"] == "P3" and out["by_status"]["skipped"] == 1
    assert [t["what"] for t in out["timeline"]] == ["skipped", "started"]
    assert out["timeline"][0]["reason"] == "later"


def test_plan_check_and_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _work(tmp_path, monkeypatch)
    _run(root, capsys, "init", "--mode", "iterative")
    _run(root, capsys, "add", "--kind", "aspect", "--title", "x", "--by", "writer")
    assert _run(root, capsys, "check")[0] == 0
    snap = json.loads(plan.snapshot_path(root).read_text(encoding="utf-8"))
    snap["parts"][1]["status"] = "done"
    plan.snapshot_path(root).write_text(json.dumps(snap), encoding="utf-8")
    code, out = _run(root, capsys, "check")
    assert code == 1 and out["status"] == "differs" and out["differs"] == "P2"
    code, out = _run(root, capsys, "check", "--repair")
    assert code == 0 and out["status"] == "repaired"
    assert _run(root, capsys, "check")[0] == 0
    plan.snapshot_path(root).unlink()  # a crash between the append and the snapshot
    assert _run(root, capsys, "check")[0] == 1
    assert _run(root, capsys, "check", "--repair")[0] == 0
    folder = plan.snapshot_path(root).parent
    assert plan.snapshot_path(root).is_file() and not list(folder.glob("*.tmp"))


def test_plan_unknown_events_are_kept_and_skipped() -> None:
    state = plan.empty_state()
    ev = {"seq": 1, "at": "t", "by": "tool", "event": "change.proposed", "change": "C1"}
    new = plan.apply(state, ev)
    assert new["last_seq"] == 1 and new["parts"] == [] and state["last_seq"] == 0


def _random_valid_step(root: Path, rng: random.Random) -> None:
    parts = plan.load_state(root)["parts"]
    options: list[tuple[str, Any]] = [("add", None)]
    has_active = any(q["status"] == "active" for q in parts)
    for p in parts:
        for cmd, (_ev, sources, _t) in plan.COMMANDS.items():
            if p["status"] in sources and not (cmd == "start" and has_active):
                options.append((cmd, p["id"]))
        options += [("move", p["id"]), ("edit", p["id"])]
    cmd, pid = rng.choice(options)
    by = rng.choice(plan.BY)
    if cmd == "add":
        after = rng.choice([None, *[p["id"] for p in parts]])
        plan.add(root, rng.choice(plan.KINDS), f"t{rng.randint(0, 99)}", by, after)
    elif cmd == "move":
        others = [p["id"] for p in parts if p["id"] != pid]
        plan.move(root, pid, by, rng.choice([None, *others]))
    elif cmd == "edit":
        plan.edit(root, pid, by, title=f"e{rng.randint(0, 99)}", refs={"n": rng.randint(0, 9)})
    else:
        plan.transition(root, cmd, pid, by, "because")


def test_plan_replay_matches_snapshot_after_random_sequence(tmp_path: Path) -> None:
    rng = random.Random(20261015)
    mismatches = 0
    for n in range(200):
        root = tmp_path / f"w{n}"
        plan.init(root, rng.choice(plan.MODES))
        for _ in range(rng.randint(1, 25)):
            _random_valid_step(root, rng)
        snap = json.loads(plan.snapshot_path(root).read_text(encoding="utf-8"))
        mismatches += snap != plan.replay(plan.read_log(root))
        assert [e["seq"] for e in plan.read_log(root)] == list(range(1, snap["last_seq"] + 1))
    assert mismatches == 0


def test_plan_events_carry_required_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _work(tmp_path, monkeypatch)
    _run(root, capsys, "init", "--mode", "iterative")
    for cmd in ("accept", "start", "done", "reopen", "skip"):
        _run(root, capsys, cmd, "P1", "--by", "writer", "--reason", "in my words")
    _run(root, capsys, "add", "--kind", "aspect", "--title", "x", "--by", "tool")
    _run(root, capsys, "move", "P2", "--by", "writer")
    _run(root, capsys, "edit", "P2", "--by", "tool", "--title", "y")
    events = plan.read_log(root)
    names = [e["event"] for e in events]
    assert names == [
        "initialized", "accepted", "started", "done", "reopened", "skipped",
        "added", "moved", "edited",
    ]  # fmt: skip
    missing = 0
    for i, e in enumerate(events, 1):
        assert e["seq"] == i and e["at"].endswith("Z") and e["by"] in ("writer", "tool")
        missing += any(k not in e for k in ("seq", "at", "by", "event", "refs"))
        if e["event"] != "initialized":
            missing += "part" not in e
        if e["event"] in plan.REASON_REQUIRED:
            missing += not e.get("reason")
    assert missing == 0  # events_missing_fields == 0


# --- status, next and legacy seeding (T3) ------------------------------------------


@pytest.fixture(scope="module")
def novel_base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("legacy")
    (root / "work.toml").write_text('slug = "ws"\nlanguage = "en"\n', encoding="utf-8")
    assert main(["ingest", str(corpus.get("marianela").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    codex.Codex.init(root, "v001")
    return root


def _issue(root: Path, name: str, check: str, unit: str, sev: str, level: str) -> str:
    ix = query.load(root)
    i = query.paragraph_range(ix, unit).start
    text = spanlib.Text(ix.paragraphs, ix.anchors, "v001")
    span = spanlib.make(text, "v001", ix.anchors[i], 0, ix.anchors[i], len(ix.paragraphs[i]))
    fields = {
        "level": level,
        "severity": sev,
        "check": check,
        "kind": "problem",
        "confidence": 0.8,
        "effort": "M",
        "why": f"Why {name}.",
    }
    return codex.Codex(root).add("issue", f"Look at {name}", fields, [span]).id


@pytest.fixture
def legacy(novel_base: Path, tmp_path: Path) -> Path:
    """A workspace with two rounds: round 1 fully decided, round 2 still open."""
    root = tmp_path / "ws"
    shutil.copytree(novel_base, root)
    _issue(root, "F2", "architecture.proportion", "c02.s1", "medium", "scene")
    rounds.build(root)
    rounds.letter(root)
    rounds.mark(root, "A1", "done", "fixed")
    _issue(root, "F1", "scene-craft.purpose", "c04.s1", "high", "scene")
    _issue(root, "F3", "scene-craft.purpose", "c09.s1", "medium", "scene")
    rounds.build(root)
    return root


def test_plan_init_on_legacy_workspace_seeds_rounds(
    legacy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _run(legacy, capsys, "status")
    assert code == 0 and out["status"] == "no_plan"
    assert [(p["kind"], p["status"]) for p in out["proposed"]] == [
        ("round", "done"),
        ("round", "active"),
    ]
    assert not plan.log_path(legacy).exists()  # nothing written
    code, out = _run(legacy, capsys, "init", "--mode", "iterative")
    assert code == 0
    parts = out["parts"]
    assert [(p["id"], p["kind"], p["status"], p["refs"]) for p in parts] == [
        ("P1", "round", "done", {"round": "round-01"}),
        ("P2", "round", "active", {"round": "round-02"}),
    ]
    assert parts[1]["title"] == "Round 2: scenes and characters"
    assert [e["by"] for e in plan.read_log(legacy)] == ["tool"]
    assert plan.check(legacy)["status"] == "ok"


def test_plan_status_joins_rounds_and_decisions(
    legacy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan.init(legacy, "iterative")
    rounds.mark(legacy, "A2", "rejected", "it is the point")
    # a change event from the same log is shown as it is, without T4's commands
    ev = {"seq": 2, "at": plan._now(), "by": "writer", "event": "change.applied", "change": "C1"}
    plan._append(legacy, ev)
    code, out = _run(legacy, capsys, "status")
    assert code == 0 and out["status"] == "ok"
    active = out["active"]
    assert active["id"] == "P2" and active["round"] == "round-02"
    assert [r["id"] for r in active["remaining"]] == ["A3"] and active["can_close"] is True
    whats = [(r["what"], r["id"]) for r in out["timeline"]]
    assert whats[0] == ("change.applied", "C1")
    assert ("decision", "A2") in whats and ("decision", "A1") in whats
    dec = next(r for r in out["timeline"] if r["id"] == "A2")
    assert dec["verdict"] == "rejected" and dec["reason"] == "it is the point"
    assert out["by_status"] == {"done": 1, "active": 1}
    assert plan.status(legacy, timeline=0)["timeline"] == []


def test_plan_next_aspect_part_builds_area_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _work(tmp_path, monkeypatch)
    _run(root, capsys, "init", "--mode", "iterative")
    refs = '{"area": "dialogue"}'
    add = ["add", "--kind", "aspect", "--title", "x", "--by", "writer", "--refs-json", refs]
    _run(root, capsys, *add)
    code, out = _run(root, capsys, "next")
    assert code == 0 and out["part"]["kind"] == "aspect"
    assert out["command"] == ["round", "build", "--area", "dialogue"]
    _run(root, capsys, "start", out["part"]["id"], "--by", "writer")
    plan.add(root, "overview", "read it", "writer")
    assert _run(root, capsys, "next")[1]["command"] is None  # an overview is read
    part = {"kind": "report-part", "refs": {"issues": ["i1", "i2"]}}
    assert plan.command_for(part) == ["round", "build", "--issues", "i1,i2"]
