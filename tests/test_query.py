import json
import statistics
from pathlib import Path

import pytest

from litcritic import corpus, index, query
from litcritic.cli import main


@pytest.fixture(scope="module")
def ws(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("ws")
    (root / "workspace.toml").write_text('slug = "ws"\nlanguage = "es"\n', encoding="utf-8")
    assert main(["ingest", str(corpus.get("marianela").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    return root


def _queries(ix: query.Index) -> list[str]:
    out = [query.toc(ix)]
    for c in ix.chapters:
        out.append(query.show(ix, c["id"]))
        for s in c["scenes"][:2]:
            out.append(query.show(ix, s["id"]))
    for word in ("Pablo", "ojos", "Nela", "luz", "madre", '"la mina"', "zzzz"):
        out.append(query.find(ix, word))
    for i in range(0, len(ix.anchors), 40):
        out.append(query.context(ix, ix.anchors[i]))
    return out


def test_context_respects_budget(ws: Path) -> None:
    ix = query.load(ws)
    for budget in (150, 600, 2000):
        for anchor in ix.anchors[::97]:
            assert query.estimate_tokens(query.context(ix, anchor, budget)) <= budget
        assert query.estimate_tokens(query.show(ix, "c02", budget)) <= budget
        assert query.estimate_tokens(query.find(ix, "Nela", budget)) <= budget
        assert query.estimate_tokens(query.toc(ix, budget)) <= budget


def test_index_query_tokens_p95(ws: Path) -> None:
    ix = query.load(ws)
    sizes = sorted(query.estimate_tokens(t) for t in _queries(ix))
    p95 = sizes[int(0.95 * (len(sizes) - 1))]
    assert p95 <= 2500
    assert statistics.mean(sizes) > 200  # the queries return real content


def test_show_find_context_content(ws: Path) -> None:
    ix = query.load(ws)
    toc = query.toc(ix)
    assert "c01 |" in toc and "Perdido" in toc
    text = query.show(ix, "c01", budget=400)
    assert text.splitlines()[0].startswith("[c01.s0.p1] -I-")
    assert "continue: lc show c01.s1.p" in text.splitlines()[-1]
    nxt = text.splitlines()[-1].split("lc show ")[1]
    assert query.show_from(ix, nxt).startswith(f"[{nxt.rstrip('-')}]")
    found = query.find(ix, "PABLO", budget=300)
    assert found.splitlines()[0].endswith("match 'PABLO'") and "[c" in found
    assert query.find(ix, "zzzz").splitlines()[0].startswith("0 paragraphs")
    ctx = query.context(ix, "c05.s1.p3", budget=1500)
    lines = ctx.splitlines()
    target = next(k for k, line in enumerate(lines) if line.startswith(">>> [c05.s1.p3]"))
    assert lines[target - 1].startswith("[c05.s1.p2]") and lines[target + 1].startswith(
        "[c05.s1.p4]"
    )
    with pytest.raises(KeyError):
        query.show(ix, "c99")


def test_index_builds_registers_from_cards(ws: Path) -> None:
    base = ws / "index" / "v001"
    with pytest.raises(FileNotFoundError):
        index.build(ws)
    card = {
        "schema_version": 1,
        "anchor": "c01.s1",
        "summary": "A traveller is lost at dusk.",
        "pov": "omniscient",
        "characters": ["Teodoro", "teodoro", "Nela"],
        "location": "Socartes",
        "story_time": "Day 1, dusk",
        "events": ["Gets lost"],
        "setups": ["the mines"],
        "payoffs": [],
    }
    later = card | {
        "anchor": "c03.s1",
        "characters": ["Nela"],
        "setups": [],
        "payoffs": ["the mines"],
    }
    (base / "scene_cards.json").write_text(json.dumps([card, card | {"anchor": "c99.s1"}]))
    written, errors = index.build(ws)
    assert written == [] and "no scene 'c99.s1'" in errors[0]
    (base / "scene_cards.json").write_text(json.dumps([card, later]))
    written, errors = index.build(ws)
    assert errors == [] and len(written) == 4
    chars = json.loads((base / "registers" / "characters.json").read_text(encoding="utf-8"))
    nela = next(e for e in chars["entries"] if e["name"] == "Nela")
    assert nela["anchors"] == ["c01.s1", "c03.s1"]
    teo = next(e for e in chars["entries"] if e["id"] == "teodoro")
    assert teo["aliases"] == ["teodoro"]
    setups = json.loads((base / "registers" / "setups.json").read_text(encoding="utf-8"))
    assert setups["entries"][0]["status"] == "paid_off"
    ix = query.load(ws)
    assert "scene c01.s1: A traveller is lost" in query.context(ix, "c01.s1.p2")


def test_cli_queries(ws: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["show", "--workspace", str(ws), "--budget", "300"]) == 0
    assert "chapter | words" in capsys.readouterr().out
    assert main(["find", "Nela", "--workspace", str(ws), "--in", "c02"]) == 0
    assert "[c02." in capsys.readouterr().out
    assert main(["context", "c02.s1.p3", "--workspace", str(ws)]) == 0
    assert main(["show", "c77", "--workspace", str(ws)]) == 2


def test_review_regressions(ws: Path) -> None:
    ix = query.load(ws)
    # A paragraph longer than the budget is shown cut, and the hint moves on.
    long_ix = query.Index(
        ["x " * 3000, "next one"], ["c01.s1.p1", "c01.s1.p2"], ["a", "b"], [], {}, {}
    )
    text = query.show(long_ix, "c01", budget=200)
    assert text.startswith("[c01.s1.p1] x x") and "lc show c01.s1.p2-" in text
    assert query.estimate_tokens(text) <= 200
    with pytest.raises(ValueError, match="empty"):
        query.find(ix, "  ")
    with pytest.raises(ValueError, match="at least"):
        query.toc(ix, budget=10)
    # Payoff listed before its setup still pairs; two payoffs alone stay open.
    base = {
        "schema_version": 1,
        "summary": "s",
        "pov": "none",
        "characters": [],
        "location": "",
        "story_time": "",
        "events": ["e"],
    }
    regs = index.registers_from_cards(
        [
            base | {"anchor": "c05.s1", "payoffs": ["the letter", "the key"]},
            base | {"anchor": "c02.s1", "setups": ["the letter", "the mines", "the mines!"]},
            base | {"anchor": "c06.s1", "payoffs": ["the key"]},
        ]
    )
    entries = {e["name"]: e for e in regs["setups"]["entries"]}
    assert entries["the letter"]["status"] == "paid_off"
    assert entries["the key"]["status"] == "open"
    assert len({e["id"] for e in regs["setups"]["entries"]}) == len(entries)
    # The same scene with and without its part prefix is one card.
    assert any(
        "two cards" in e
        for e in index.check_cards(
            [base | {"anchor": "c01.s1"}, base | {"anchor": "p1.c01.s1"}], {"c01.s1"}
        )
    )
