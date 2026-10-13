import io
import itertools
import json
import random
import shutil
from pathlib import Path
from typing import Any

import pytest

from litcritic import codex, corpus, packets
from litcritic.cli import main

# --- fixtures ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("jh") / "ws"
    root.mkdir()
    (root / "work.toml").write_text('slug = "jh"\nlanguage = "en"\n', "utf-8")
    assert main(["ingest", str(corpus.get("jekyll-hyde").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    packets.plan(root)
    return root


@pytest.fixture
def ws(base: Path, tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    shutil.copytree(base, root)
    return root


def _draft(ws: Path) -> packets.Draft:
    return packets.load_draft(ws)


def _unique_quote(draft: packets.Draft, lo: int, hi: int, skip: int = 0) -> str | None:
    """A run of words from the scene that occurs once in it."""
    scope = "\n".join(draft.paragraphs[lo : hi + 1])
    found = 0
    for i in range(lo, hi + 1):
        words = draft.paragraphs[i].split()
        if len(words) < 12:
            continue
        q = " ".join(words[2:12])
        if q in draft.paragraphs[i] and scope.count(q) == 1:
            if found == skip:
                return q
            found += 1
    return None


def _scene_answer(ws: Path, pid: str) -> dict[str, Any]:
    doc = packets.load_plan(ws)
    draft = _draft(ws)
    p = next(x for x in doc["packets"] if x["id"] == pid)
    scenes = []
    for u in p["inputs"]["units"]:
        q = _unique_quote(draft, *u["paras"])
        setups = [{"label": f"detail {u['scene']}", "side": "setup", "quote": q}] if q else []
        scenes.append(
            {
                "scene": u["scene"],
                "summary": "A placeholder summary of what happens here.",
                "pov": "narrator",
                "setups": setups,
            }
        )
    scenes.sort(key=lambda s: not s["setups"])  # any order will do; setups first for tests
    return {"scenes": scenes}


def _import(ws: Path, pid: str, answer: Any) -> str:
    raw = answer if isinstance(answer, str) else json.dumps(answer)
    return packets.import_answer(ws, pid, raw)


def _status(ws: Path, pid: str) -> dict[str, Any]:
    return next(p for p in packets.load_plan(ws)["packets"] if p["id"] == pid)


# --- gate --------------------------------------------------------------------------


def test_import_is_all_or_nothing(ws: Path) -> None:
    answer = _scene_answer(ws, "s001")
    last = len(answer["scenes"]) - 1
    k = len(answer["scenes"][last]["setups"])
    answer["scenes"][last]["setups"].append(
        {"label": "missing", "side": "setup", "quote": "words that the novel never says"}
    )
    line = _import(ws, "s001", answer)
    assert line.startswith(f"error s001: $.scenes[{last}].setups[{k}].quote: not found in ")
    cx = codex.Codex(ws)
    assert cx.items == {}
    assert not (cx.root / "changes.jsonl").exists()
    assert _status(ws, "s001")["status"] == "failed"
    assert (ws / "index" / "work" / "answers" / "s001.json").is_file()

    answer["scenes"][last]["setups"].pop()
    line = _import(ws, "s001", answer)
    setups = sum(len(s["setups"]) for s in answer["scenes"])
    n = len(answer["scenes"]) + setups  # a scene card per scene, plus its setups
    assert line == f"ok s001: {n} items"
    cx = codex.Codex(ws)
    assert len(cx.live("scene")) == len(answer["scenes"]) and len(cx.live("setup")) == setups
    log = [json.loads(x) for x in (cx.root / "changes.jsonl").read_text("utf-8").splitlines()]
    assert len(log) == n and {e["batch"] for e in log} == {"index:v001:s001"}
    assert _status(ws, "s001")["status"] == "done"
    assert cx.check() == []
    assert _import(ws, "s001", answer) == "error s001: $: packet already imported"


def _synthetic_book(words: int) -> str:
    raw = corpus.get("jekyll-hyde").path.read_text(encoding="utf-8")
    paras = [" ".join(b.split()) for b in raw.split("\n\n")]
    paras = [p for p in paras if len(p.split()) >= 20]
    rng = random.Random(7)
    out: list[str] = []
    total = k = ch = 0
    sizes = [150, 400, 900, 1500, 2500, 6000]
    while total < words:
        ch += 1
        out.append(f"CHAPTER {ch}")
        for s in range(rng.randint(1, 6)):
            if s:
                out.append("* * *")
            target = 12_000 if ch == 3 and s == 0 else rng.choice(sizes)  # one huge scene
            got = 0
            while got < target:
                p = paras[k % len(paras)]
                k += 1
                out.append(p)
                got += len(p.split())
            total += got
    return "\n\n".join(out) + "\n"


def test_scene_packets_bounded(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "work.toml").write_text('slug = "synth"\nlanguage = "en"\n', "utf-8")
    src = tmp_path / "book.txt"
    src.write_text(_synthetic_book(300_000), "utf-8")
    assert main(["ingest", str(src), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    doc = packets.plan(root)
    draft = _draft(root)
    assert sum(len(p.split()) for p in draft.paragraphs) >= 300_000
    worst = max(packets.tokens(packets.render(root, doc, p["id"], draft)) for p in doc["packets"])
    assert worst <= packets.PACKET_MAX, worst
    assert doc["stats"]["max_packet_tokens"] == worst
    # Every scene is covered once, in order; only scenes over SPLIT_AT are cut.
    units = [u for p in doc["packets"] if p["kind"] == "scenes" for u in p["inputs"]["units"]]
    assert [s["id"] for s in draft.scenes] == list(dict.fromkeys(u["scene"] for u in units))
    parts = [u for u in units if "part" in u]
    assert parts and all(
        packets.tokens("\n".join(draft.paragraphs[s["start"] : s["end"] + 1])) > packets.SPLIT_AT
        for s in draft.scenes
        if s["id"] in {u["scene"] for u in parts}
    )
    for p in doc["packets"]:
        us = p["inputs"].get("units", [])
        if len(us) > 1:
            assert sum(u["tokens"] for u in us) <= packets.SCENE_TEXT_CAP
            assert not any("part" in u for u in us)


# --- planning ----------------------------------------------------------------------


def test_entity_packets_split_most_frequent_first(base: Path) -> None:
    draft = _draft(base)
    cands = draft.pre["candidates"]
    groups = packets.entity_groups(draft.pre, cap=900)
    assert len(groups) >= 2
    assert groups[0][0] == 0 and groups[-1][1] == len(cands)
    assert all(a[1] == b[0] for a, b in itertools.pairwise(groups))
    doc = {
        "draft": draft.version,
        "packets": [
            {"id": f"e{k}", "kind": "entities", "inputs": {"candidates": [a, b]}}
            for k, (a, b) in enumerate(groups, 1)
        ],
    }
    for k, (a, _) in enumerate(groups, 1):
        text = packets.render(base, doc, f"e{k}", draft)
        assert packets.tokens(text) <= 900
        assert text.startswith(f"packet e{k} · entities {k}/{len(groups)}")
        assert "Other names: " in text  # self-contained: knows the other packets' names
        assert cands[a]["name"] in text
    assert cands[0]["count"] >= cands[groups[-1][0]]["count"]


def test_plan_keeps_statuses_and_changed_needs_sync(ws: Path) -> None:
    assert _import(ws, "s002", _scene_answer(ws, "s002")).startswith("ok ")
    packets.plan(ws)
    assert _status(ws, "s002")["status"] == "done"
    assert _status(ws, "s001")["status"] == "todo"
    with pytest.raises(packets.PacketError, match="no sync data"):
        packets.plan(ws, changed=True)


# --- importing ---------------------------------------------------------------------


def test_quote_ambiguous_or_outside_scene_is_refused(ws: Path) -> None:
    answer = _scene_answer(ws, "s001")
    answer["scenes"][0]["setups"][0]["quote"] = "the"
    line = _import(ws, "s001", answer)
    assert "$.scenes[0].setups[0].quote: found " in line and "quote more words" in line
    draft = _draft(ws)
    doc = packets.load_plan(ws)
    other = next(p for p in doc["packets"] if p["id"] == "s003")["inputs"]["units"][0]
    answer["scenes"][0]["setups"][0]["quote"] = _unique_quote(draft, *other["paras"])
    line = _import(ws, "s001", answer)
    assert line.startswith("error s001: $.scenes[0].setups[0].quote: not found in ")
    assert codex.Codex(ws).items == {}


def test_answer_must_cover_exactly_the_packet_scenes(ws: Path) -> None:
    answer = _scene_answer(ws, "s001")
    dropped = answer["scenes"].pop()
    assert _import(ws, "s001", answer) == f"error s001: $.scenes: missing {dropped['scene']}"
    answer["scenes"].append({**dropped, "scene": "c99.s9"})
    assert "is not in this packet" in _import(ws, "s001", answer)


def test_schema_errors_name_the_field(ws: Path) -> None:
    answer = _scene_answer(ws, "s001")
    answer["scenes"][0]["summary"] = " ".join(["word"] * 81)
    assert _import(ws, "s001", answer) == "error s001: $.scenes[0].summary: 81 words, limit 80"
    answer["scenes"][0]["summary"] = "ok"
    answer["scenes"][0]["setups"] *= 7
    assert _import(ws, "s001", answer) == "error s001: $.scenes[0].setups: 7 items, limit 6"
    assert _import(ws, "s001", "{not json").startswith("error s001: $: not valid JSON")


def test_entity_import_anchors_on_first_quote_and_merges(ws: Path) -> None:
    cx = codex.Codex(ws)
    known = cx.add("entity", "Jekyll", {"kind": "character", "name": "Henry Jekyll"})
    answer = {
        "entities": [
            {"name": "Utterson", "kind": "character", "aliases": ["Mr. Utterson", "the lawyer"]},
            {"name": "Henry Jekyll", "kind": "character", "aliases": ["Dr. Jekyll"]},
        ],
        "rejects": ["London"],
    }
    assert _import(ws, "e1", answer) == "ok e1: 2 items"
    cx = codex.Codex(ws)
    ut = next(i for i in cx.live("entity") if i.fields["name"] == "Utterson")
    assert ut.spans[0].exact == "Mr. Utterson" and ut.spans[0].start.para == "c01.s1.p1"
    jek = cx.get(known.id)
    assert jek.fields["aliases"] == ["Dr. Jekyll"] and jek.rev == 2
    assert cx.check() == []


def test_entity_answer_errors(ws: Path) -> None:
    dup = {
        "entities": [
            {"name": "Utterson", "kind": "character"},
            {"name": "Mr. Utterson", "kind": "character", "aliases": ["utterson"]},
        ]
    }
    assert _import(ws, "e1", dup) == (
        "error e1: $.entities[1].aliases[0]: 'utterson' is already in $.entities[0]"
    )
    invented = {"entities": [{"name": "Nobody Atall", "kind": "character"}]}
    assert _import(ws, "e1", invented) == (
        "error e1: $.entities[0].name: not a candidate name; add a quote naming it"
    )
    invented["entities"][0]["quote"] = "Mr. Utterson the lawyer was a man"
    assert _import(ws, "e1", invented) == "ok e1: 1 items"


def test_payoff_links_to_its_setup(ws: Path) -> None:
    answer = _scene_answer(ws, "s001")
    draft = _draft(ws)
    units = packets.load_plan(ws)["packets"][1]["inputs"]["units"]
    lo, hi = next(u["paras"] for u in units if u["scene"] == answer["scenes"][0]["scene"])
    first = answer["scenes"][0]["setups"][0]
    answer["scenes"][0]["setups"].append(
        {
            "label": "pay",
            "side": "payoff",
            "quote": _unique_quote(draft, lo, hi, skip=1),
            "pays_off": first["label"].upper(),
        }
    )
    answer["scenes"][0]["entities"] = [
        {"name": "Somebody New", "kind": "object", "quote": _unique_quote(draft, lo, hi, skip=2)}
    ]
    assert _import(ws, "s001", answer).startswith("ok s001: ")
    cx = codex.Codex(ws)
    pay = next(i for i in cx.live("setup") if i.fields["side"] == "payoff")
    target = cx.get(pay.links[0]["to"])
    assert pay.links[0]["rel"] == "pays_off" and target.fields["label"] == first["label"]
    assert any(i.fields["name"] == "Somebody New" for i in cx.live("entity"))


def test_add_many_is_all_or_nothing(ws: Path) -> None:
    cx = codex.Codex(ws)
    good = codex.Item(
        id=cx.new_id("entity"), type="entity", text="x", fields={"kind": "place", "name": "X"}
    )
    bad = codex.Item(
        id=cx.new_id("entity"), type="entity", text="y", fields={"kind": "spaceship", "name": "Y"}
    )
    with pytest.raises(codex.CodexError, match="spaceship"):
        cx.add_many([good, bad])
    assert cx.items == {} and codex.Codex(ws).items == {}
    linked = codex.Item(
        id=cx.new_id("entity"),
        type="entity",
        text="z",
        fields={"kind": "place", "name": "Z"},
        links=[{"rel": "part_of", "to": good.id}],
    )
    cx.add_many([linked, good], batch="b1")
    assert set(codex.Codex(ws).items) == {good.id, linked.id}


# --- commands ----------------------------------------------------------------------


def test_cli_packet_import_from_stdin_and_status(
    ws: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    w = ["--workspace", str(ws)]
    assert main(["index", "packet", "s001", *w]) == 0
    out = capsys.readouterr().out
    assert out.startswith("packet s001 · scenes ")
    assert '"required":["scenes"]' in out and "\n## c00.s1 " in out
    answer = json.dumps(_scene_answer(ws, "s001"))
    monkeypatch.setattr("sys.stdin", io.StringIO(answer))
    assert main(["index", "import", "s001", "--file", "-", "--next", *w]) == 0
    out = capsys.readouterr().out
    first, rest = out.split("\n", 1)
    assert first.startswith("ok s001: ") and rest.startswith("packet e1 · entities")
    monkeypatch.setattr("sys.stdin", io.StringIO("[]"))
    assert main(["index", "import", "s002", "--file", "-", *w]) == 1
    assert capsys.readouterr().out.startswith("error s002: $: expected object")
    assert main(["index", "status", *w]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("e1 entities todo ~")
    assert any(x.startswith("s001 scenes done ~") for x in lines)
    assert any(x.startswith("s002 scenes failed ~") for x in lines)
    assert lines[-1].endswith(f": {len(lines) - 3} todo, 1 done, 1 failed")
    assert main(["index", "packet", "zz9", *w]) == 2
    assert main(["index", "plan", "--changed", *w]) == 2


def test_plan_changed_packs_only_scenes_to_reread(ws: Path) -> None:
    assert _import(ws, "s002", _scene_answer(ws, "s002")).startswith("ok ")
    cx = codex.Codex(ws)
    scene = sorted(cx.live("scene"), key=lambda i: i.spans[0].start.para)[1]
    (cx.root / "reread.jsonl").write_text(json.dumps({"item": scene.id}) + "\n", "utf-8")
    doc = packets.plan(ws, changed=True)
    units = [u["scene"] for p in doc["packets"] for u in p["inputs"]["units"]]
    assert units == [scene.spans[0].start.para.rsplit(".p", 1)[0]]
    assert doc["stats"]["scenes"] == 1 and doc["stats"]["entity_packets"] == 0
