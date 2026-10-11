"""C11: phase-1 per-type formats are gone; what they fed now comes from the Codex."""

import re
import subprocess
from pathlib import Path

import pytest
from codex_fixture import build

from litcritic import metrics, query
from litcritic.cli import main
from litcritic.workspace import repo_root

ROOT = repo_root()
GONE_FILES = [
    "src/litcritic/index.py",
    "schemas/scene-card.schema.json",
    "schemas/register.schema.json",
    "schemas/finding.schema.json",
    "schemas/action.schema.json",
    "prompts/20-scene-cards.md",
    "prompts/25-summaries.md",
]
OLD_NAMES = re.compile(
    r"scene_cards\.json|chapter_summaries\.json|registers/|20-scene-cards|25-summaries"
    r"|(?:scene-card|register|finding|action)\.schema"
    r"|schema `(?:scene-card|register|finding|action)`"
    r"|lc index\b|lc validate (?:scene-card|register|finding|action)\b"
    r"|litcritic\.index\b|from litcritic import[^\n]*\bindex\b"
)
# Records of past work and the vendored bundle keep their history.
SKIP = (
    "status/",
    "arsenal/",
    "claude-arsenal/",
    ".claude/skills/init/",
    "tests/test_codex_cleanup.py",
)


def phase1_leftovers() -> list[str]:
    files = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    out = [f"{f}: still exists" for f in GONE_FILES if (ROOT / f).exists()]
    for f in files:
        path = ROOT / f
        if f.startswith(SKIP) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        out += [f"{f}: {m.group()}" for m in OLD_NAMES.finditer(text)]
    return out


def test_no_phase1_leftovers() -> None:
    assert phase1_leftovers() == []


@pytest.fixture(scope="module")
def work(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    root = tmp_path_factory.mktemp("marianela")
    return root, build(root)


def test_metrics_and_context_read_the_codex(
    work: tuple[Path, dict[str, str]], capsys: pytest.CaptureFixture[str]
) -> None:
    root, _ = work
    ix = query.load(root, "v001")
    scene = ix.scene_of(0)
    w = ["--workspace", str(root)]
    fields = '{"summary": "Arrival at dusk.", "pov": "omniscient", "time": "dusk"}'
    args = ["codex", "add", "scene", "--text", "Arrival.", "--unit", scene, "--fields", fields]
    assert main([*args, *w]) == 0
    assert main(["codex", "add", "scene", "--text", "x", "--unit", "c99", *w]) == 2
    assert "not a chapter or scene" in capsys.readouterr().err
    motif = '{"kind": "motif", "name": "ojos"}'
    assert main(["codex", "add", "entity", "--text", "Eyes.", "--fields", motif, *w]) == 0

    assert main(["codex", "add", "scene", "--text", "x", "--unit", f"{scene}.p1", *w]) == 2
    nela = '{"kind": "character", "name": "NELA", "aliases": ["la hija de la Canela"]}'
    assert main(["codex", "add", "entity", "--text", "Again.", "--fields", nela, *w]) == 0
    lone = '{"label": "sight", "side": "payoff"}'
    quote = ["--quote", ix.paragraphs[40][:40]]
    assert main(["codex", "add", "setup", "--text", "P.", "--fields", lone, *quote, *w]) == 0

    ctx = metrics.context_for(root, "v001", "es")
    merged = [e for e in ctx.registers["characters"] if e["name"].casefold() == "nela"]
    assert len(merged) == 1 and "la hija de la Canela" in merged[0]["aliases"]
    assert {e["name"].casefold() for e in ctx.registers["characters"]} >= {"nela", "pablo"}
    assert ctx.registers["motifs"] == [{"name": "ojos", "aliases": []}]
    setups = {e["id"].split(" (")[0]: e for e in ctx.registers["setups"]}
    assert len(ctx.registers["setups"]) == 3 and setups["star"]["status"] == "open"
    pos = {a: i for i, a in enumerate(ctx.anchors)}
    for e in ctx.registers["setups"]:
        assert [pos[a] for a in e["anchors"]] == sorted(pos[a] for a in e["anchors"])
    distance = metrics.compute(ctx, ["setup_payoff_distance"])["setup_payoff_distance"]
    statuses = sorted(x.get("status", "paid") for x in distance["items"])
    assert statuses == ["paid", "unpaid", "unplanted"]
    assert ctx.scene_cards == [{"anchor": scene, "pov": "omniscient"}]
    res = metrics.compute(ctx, ["pov_distribution", "motif_occurrences"])
    assert res["pov_distribution"]["book"]["scenes"] == {"omniscient": 1}
    assert sum(res["motif_occurrences"]["book"]["ojos"].values()) > 5

    shown = query.context(query.load(root, "v001"), ix.anchors[0])
    assert f"scene {query._bare(scene)}: Arrival at dusk. | POV omniscient | dusk" in shown
    # A Codex synced to another draft feeds nothing.
    assert metrics.codex_registers(root, "v002", ctx.anchors) == ({}, [])
