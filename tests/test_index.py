import io
import itertools
import json
import random
import shutil
from pathlib import Path
from typing import Any

import pytest

from litcritic import codex, corpus, packets, sync, view
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
    for p in packets.load_plan(ws)["packets"]:
        if p["kind"] == "scenes":
            assert _import(ws, p["id"], _scene_answer(ws, p["id"])).startswith("ok ")
    cx = codex.Codex(ws)
    scene = sorted(cx.live("scene"), key=lambda i: i.spans[0].start.para)[1]
    (cx.root / "reread.jsonl").write_text(json.dumps({"item": scene.id}) + "\n", "utf-8")
    doc = packets.plan(ws, changed=True)
    assert _packed(doc) == [scene.spans[0].start.para.rsplit(".p", 1)[0]]
    assert doc["stats"]["scenes"] == 1


# --- re-index after a new draft (T6) ----------------------------------------------

REINDEX_RATIO = 0.15


def _scenes_of_book(count: int, paras_each: int = 6) -> list[list[str]]:
    raw = corpus.get("jekyll-hyde").path.read_text(encoding="utf-8")
    paras = [" ".join(b.split()) for b in raw.split("\n\n")]
    paras = [p for p in paras if len(p.split()) >= 40]
    return [
        [paras[(k * paras_each + j) % len(paras)] for j in range(paras_each)] for k in range(count)
    ]


def _write_book(
    root: Path,
    scenes: list[list[str]],
    tmp: Path,
    tail: str = "",
    starts: list[int] | None = None,
) -> None:
    starts = starts if starts is not None else list(range(0, len(scenes), 5))
    out: list[str] = []
    for k, sc in enumerate(scenes):
        if k in starts:
            out.append(f"CHAPTER {starts.index(k) + 1}")
        elif k:
            out.append("* * *")
        out += sc
    src = tmp / "book.txt"
    src.write_text("\n\n".join(out) + "\n" + tail, "utf-8")
    assert main(["ingest", str(src), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0


def _index_all(root: Path) -> dict[str, Any]:
    doc = packets.plan(root)
    cands = _draft(root).pre["candidates"]
    for p in doc["packets"]:
        if p["kind"] == "entities":
            a, b = p["inputs"]["candidates"]
            ents = [{"name": c["name"], "kind": "character"} for c in cands[a:b]]
            assert _import(root, p["id"], {"entities": ents, "rejects": []}).startswith("ok ")
        else:
            assert _import(root, p["id"], _scene_answer(root, p["id"])).startswith("ok ")
    return doc


def _reindexed(
    tmp_path: Path, edit: Any, count: int = 20, tail: str = "", starts: list[int] | None = None
) -> tuple[Path, dict[str, Any], dict[str, Any], list[list[str]]]:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "work.toml").write_text('slug = "re"\nlanguage = "en"\n', "utf-8")
    scenes = _scenes_of_book(count)
    _write_book(root, scenes, tmp_path)
    first = _index_all(root)
    new = edit([list(sc) for sc in scenes])
    _write_book(root, new, tmp_path, tail, starts)
    sync.sync(root)
    return root, first, packets.plan(root, changed=True), new


def _packed(doc: dict[str, Any]) -> list[str]:
    return [
        u["scene"] for p in doc["packets"] if p["kind"] == "scenes" for u in p["inputs"]["units"]
    ]


def _rewrite(sc: list[str]) -> list[str]:
    return [sc[0], "A wholly new paragraph, invented for this test, " * 8, *sc[2:]]


def test_reindex_packs_only_changed_scenes(tmp_path: Path) -> None:
    def edit(sc: list[list[str]]) -> list[list[str]]:
        sc[3], sc[11] = _rewrite(sc[3]), _rewrite(sc[11])
        return sc

    root, first, doc, _ = _reindexed(tmp_path, edit)
    draft = _draft(root)
    scene_id = [s["id"] for s in draft.scenes]
    assert len(scene_id) == 20
    assert _packed(doc) == [scene_id[3], scene_id[11]]
    assert doc["stats"]["entity_packets"] == 0
    ratio = doc["stats"]["total_packet_tokens"] / first["stats"]["total_packet_tokens"]
    assert ratio <= REINDEX_RATIO, ratio
    # Importing the re-read scenes updates the scene items in place and clears the flag.
    before = {i.id for i in codex.Codex(root).live("scene")}
    for p in doc["packets"]:
        assert _import(root, p["id"], _scene_answer(root, p["id"])).startswith("ok ")
    cx = codex.Codex(root)
    assert {i.id for i in cx.live("scene")} == before
    assert not [i for i in cx.items.values() if i.type == "scene" and i.status == "needs_reread"]


def test_reindex_packs_a_new_scene(tmp_path: Path) -> None:
    def edit(sc: list[list[str]]) -> list[list[str]]:
        return [*sc, _scenes_of_book(30)[25]]

    root, _, doc, _ = _reindexed(tmp_path, edit)
    draft = _draft(root)
    assert len(draft.scenes) == 21
    assert _packed(doc) == [draft.scenes[20]["id"]]


def test_reindex_new_name_gets_an_entity_packet_with_only_that_name(tmp_path: Path) -> None:
    def edit(sc: list[list[str]]) -> list[list[str]]:
        sc[4] = [
            *sc[4][:2],
            "Then Zephaniah Quillfeather said that Zephaniah Quillfeather knew.",
            *sc[4][2:],
        ]
        return sc

    root, _, doc, _ = _reindexed(tmp_path, edit)
    ents = [p for p in doc["packets"] if p["kind"] == "entities"]
    assert len(ents) == 1 and len(_packed(doc)) == 1
    pre = _draft(root).pre
    assert [c["name"] for c in pre["candidates"]] == ["Zephaniah Quillfeather"]
    assert "Zephaniah Quillfeather" in packets.render(root, doc, ents[0]["id"])


def test_reindex_unchanged_draft_has_nothing_to_do(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A new draft file (one more blank line at the end) with every scene as before.
    root, _, doc, _ = _reindexed(tmp_path, lambda sc: sc, tail="\n")
    assert _draft(root).version == "v002"
    assert doc["packets"] == [] and doc["stats"]["total_packet_tokens"] == 0
    assert main(["index", "plan", "--changed", "--workspace", str(root)]) == 0
    assert "nothing to do" in capsys.readouterr().out


# --- entities and references (T3) --------------------------------------------------

GOLD = Path(__file__).parent / "fixtures" / "gold"


def _gold_fields(e: dict[str, Any]) -> dict[str, Any]:
    """A gold entry as entity fields: all-lower-case forms are role titles."""
    forms = list(dict.fromkeys([e["name"], *e["aliases"]]))
    titles = [f for f in forms if f == f.lower()]
    aliases = [f for f in forms[1:] if f not in titles]
    fields: dict[str, Any] = {"kind": e["kind"], "name": e["name"]}
    if aliases:
        fields["aliases"] = aliases
    if titles:
        fields["titles"] = titles
    return fields


def _reference_recall(root: Path, slug: str) -> dict[str, Any]:
    """Gold entities imported; recall = sum of min(found, gold) over gold occurrences."""
    gold = json.loads((GOLD / f"{slug}.json").read_text("utf-8"))
    cx = codex.Codex(root)
    ids = [cx.add("entity", e["name"], _gold_fields(e)).id for e in gold["entities"]]
    v = view.View(root, cx)
    found = dict(v.run("SELECT entity_id, COUNT(*) FROM mentions GROUP BY entity_id")[1])
    occ = [e["occurrences"] for e in gold["entities"]]
    hits = sum(min(found.get(i, 0), n) for i, n in zip(ids, occ, strict=True))
    titles = v.run("SELECT COUNT(*) FROM mentions WHERE via = 'title'")[1][0][0]
    return {
        "recall": hits / sum(occ),
        "hits": hits,
        "gold": sum(occ),
        "found": sum(found.values()),
        "title_hits": titles,
    }


@pytest.fixture(scope="module")
def recall(base: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    out = {}
    jh = tmp_path_factory.mktemp("jh-gold") / "ws"
    shutil.copytree(base, jh)
    out["jekyll-hyde"] = _reference_recall(jh, "jekyll-hyde")
    mn = tmp_path_factory.mktemp("mn-gold") / "ws"
    mn.mkdir()
    (mn / "work.toml").write_text('slug = "mn"\nlanguage = "es"\n', "utf-8")
    assert main(["ingest", str(corpus.get("marianela").path), "--workspace", str(mn)]) == 0
    assert main(["anchor", "--workspace", str(mn)]) == 0
    codex.Codex.init(mn, "v001")
    out["marianela"] = _reference_recall(mn, "marianela")
    return out


def test_reference_recall_on_gold(recall: dict[str, dict[str, Any]]) -> None:
    for slug, r in recall.items():
        assert r["recall"] >= 0.95, (slug, r)


def _entity(ws: Path, **fields: Any) -> codex.Item:
    return codex.Codex(ws).add("entity", fields["name"], fields)


def _mentions(ws: Path, sql: str) -> list[tuple[Any, ...]]:
    return view.View(ws).run(sql)[1]


def test_mentions_longest_match_counts_once(ws: Path) -> None:
    jek = _entity(ws, kind="character", name="Henry Jekyll", aliases=["Jekyll"])
    henry = _entity(ws, kind="character", name="Henry", exact_case=True)
    rows = _mentions(
        ws,
        "SELECT m.entity_id, m.para_idx, m.off, m.form, m.via FROM mentions m"
        " JOIN paragraphs p ON p.idx = m.para_idx WHERE p.text LIKE '%Henry Jekyll%'",
    )
    full = [r for r in rows if r[3] == "Henry Jekyll"]
    assert full and all(r[0] == jek.id and r[4] == "name" for r in full)
    starts = {(r[1], r[2]) for r in full}
    inside = [r for r in rows if any(p == r[1] and s <= r[2] < s + 12 for p, s in starts)]
    assert inside == full  # no second row for 'Henry' or 'Jekyll' inside 'Henry Jekyll'
    assert henry.id not in {r[0] for r in full}
    # exact_case: only 'Guest' with a capital counts; without it 'guest' counts too
    guest = _entity(ws, kind="character", name="Guest", exact_case=True)
    loose = _entity(ws, kind="character", name="Mr. Guest", aliases=["guest"])
    forms = _mentions(ws, f"SELECT DISTINCT form FROM mentions WHERE entity_id = '{guest.id}'")
    assert forms == [("Guest",)]
    forms = _mentions(ws, f"SELECT DISTINCT form FROM mentions WHERE entity_id = '{loose.id}'")
    assert {f for (f,) in forms} >= {"guest", "Guest"}


def test_titles_count_only_in_scenes_naming_the_entity(ws: Path) -> None:
    lan = _entity(
        ws, kind="character", name="Lanyon", aliases=["Dr. Lanyon"], titles=["the lawyer"]
    )
    rows = _mentions(ws, f"SELECT scene, via, form FROM mentions WHERE entity_id = '{lan.id}'")
    named = {s for s, via, _ in rows if via in ("name", "alias")}
    titled = [(s, f) for s, via, f in rows if via == "title"]
    assert titled and {s for s, _ in titled} <= named
    total = sum(p.lower().count("the lawyer") for p in _draft(ws).paragraphs)
    assert len(titled) < total  # 'the lawyer' elsewhere is Utterson, not Lanyon
    assert all(f.lower() == "the lawyer" for _, f in titled)


def test_entity_quote_ambiguous_anchors_first_occurrence(ws: Path) -> None:
    answer = {
        "entities": [
            {"name": "Utterson", "kind": "character", "quote": "Utterson"},
            {"name": "Edward Hyde", "kind": "character", "aliases": ["Hyde"], "quote": "Hyde"},
            {"name": "Poole", "kind": "character", "quote": "words the novel never says"},
        ]
    }
    assert _import(ws, "e1", answer) == "ok e1: 3 items (3 quote fallbacks)"
    cx = codex.Codex(ws)
    by = {i.fields["name"]: i for i in cx.live("entity")}
    draft = _draft(ws)
    first = next(k for k, p in enumerate(draft.paragraphs) if "Utterson" in p)
    assert by["Utterson"].spans[0].start.para == draft.anchors[first]
    assert by["Utterson"].spans[0].exact == "Utterson"
    hyde = next(c for c in draft.pre["candidates"] if "Hyde" in [c["name"], *c["forms"]])
    assert by["Edward Hyde"].spans[0].start.para == hyde["first"]["para"]
    assert by["Edward Hyde"].spans[0].exact == "Hyde"
    assert by["Poole"].spans[0].exact.endswith("Poole")
    assert cx.check() == []


def test_entity_quote_missing_without_candidate_is_refused(ws: Path) -> None:
    nobody = {"entities": [{"name": "Nobody Atall", "kind": "character", "quote": "zzz qqq"}]}
    assert _import(ws, "e1", nobody) == (
        "error e1: $.entities[0].quote: not found in the draft (copy the words exactly)"
    )


def test_entity_titles_and_same_as(ws: Path) -> None:
    answer = {
        "entities": [
            {
                "name": "Henry Jekyll",
                "kind": "character",
                "aliases": ["Dr. Jekyll"],
                "titles": ["the doctor", "Dr. Jekyll"],
            },
            {
                "name": "Edward Hyde",
                "kind": "character",
                "aliases": ["Hyde"],
                "same_as": "Dr. Jekyll",
            },
            {
                "name": "Lanyon",
                "kind": "character",
                "titles": ["the doctor"],
                "same_as": "Nobody Atall",
            },
        ]
    }
    assert _import(ws, "e1", answer) == (
        "ok e1: 3 items (1 same_as left unlinked: no entity with that name yet)"
    )
    cx = codex.Codex(ws)
    by = {i.fields["name"]: i for i in cx.live("entity")}
    assert by["Henry Jekyll"].fields["titles"] == ["the doctor"]
    assert by["Lanyon"].fields["titles"] == ["the doctor"]  # a title may be shared
    assert by["Edward Hyde"].links == [{"rel": "same_as", "to": by["Henry Jekyll"].id}]
    assert cx.check() == []
    # A later packet links to an entity already in the Codex, and merges titles.
    later = {
        "entities": [
            {"name": "Mr. Hyde", "kind": "character", "quote": "Mr. Hyde", "same_as": "Jekyll"},
            {"name": "Henry Jekyll", "kind": "character", "aliases": ["Jekyll"]},
            {
                "name": "Dr. Lanyon",
                "kind": "character",
                "aliases": ["Lanyon"],
                "titles": ["the physician"],
            },
        ]
    }
    doc = packets.load_plan(ws)
    doc["packets"].append(
        {
            "id": "e9",
            "kind": "entities",
            "inputs": {"candidates": [0, 1]},
            "status": "todo",
            "tokens": 0,
        }
    )
    packets._save_plan(ws, doc)
    assert _import(ws, "e9", later) == "ok e9: 3 items (1 quote fallback)"
    cx = codex.Codex(ws)
    by = {i.fields["name"]: i for i in cx.live("entity")}
    assert by["Mr. Hyde"].links == [{"rel": "same_as", "to": by["Henry Jekyll"].id}]
    assert by["Henry Jekyll"].fields["aliases"] == ["Dr. Jekyll", "Jekyll"]
    assert by["Lanyon"].fields["titles"] == ["the doctor", "the physician"]
    assert by["Lanyon"].fields["aliases"] == ["Dr. Lanyon"]
    assert cx.check() == []


def test_packet_tiers_and_entity_rules(base: Path) -> None:
    doc = packets.load_plan(base)
    e1 = packets.render(base, doc, "e1")
    s1 = packets.render(base, doc, "s001")
    assert e1.startswith("packet e1 · entities 1/1 · tier strong · draft v001\n")
    assert s1.startswith("packet s001 · scenes ") and " · tier standard · " in s1.split("\n")[0]
    assert {p["tier"] for p in doc["packets"] if p["kind"] == "entities"} == {"strong"}
    assert {p["tier"] for p in doc["packets"] if p["kind"] == "scenes"} == {"standard"}
    for words in ("titles", "rejects", "same_as", '"titles"', '"same_as"'):
        assert words in e1


# --- scene packets (T4) ------------------------------------------------------------


def test_scene_answer_schema_caps_lengths(ws: Path) -> None:
    def refused(change: Any) -> str:
        answer = _scene_answer(ws, "s001")
        change(answer["scenes"][0])
        line = _import(ws, "s001", answer)
        assert codex.Codex(ws).items == {}
        return line

    def put(key: str, value: Any) -> Any:
        return lambda s: s.__setitem__(key, value)

    assert refused(lambda s: s.pop("pov")) == "error s001: $.scenes[0]: missing pov"
    assert refused(put("pov", "  ")) == "error s001: $.scenes[0].pov: must not be empty"
    assert refused(put("pov", "x" * 61)) == ("error s001: $.scenes[0].pov: 61 characters, limit 60")
    assert refused(put("summary", " ".join(["word"] * 81))) == (
        "error s001: $.scenes[0].summary: 81 words, limit 80"
    )
    assert refused(put("location", "y" * 81)) == (
        "error s001: $.scenes[0].location: 81 characters, limit 80"
    )
    assert refused(put("time", "z" * 81)) == (
        "error s001: $.scenes[0].time: 81 characters, limit 80"
    )
    assert refused(put("setups", [{"label": "a", "side": "setup"}] * 7)).startswith(
        "error s001: $.scenes[0].setups: 7 items, limit 6"
    )
    for key in ("label", "side", "quote"):
        line = refused(lambda s, key=key: s["setups"][0].pop(key))
        assert line == f"error s001: $.scenes[0].setups[0]: missing {key}"
    line = refused(lambda s: s["setups"][0].__setitem__("quote", " ".join(["w"] * 31)))
    assert line == "error s001: $.scenes[0].setups[0].quote: 31 words, limit 30"
    answer = _scene_answer(ws, "s001")
    for s in answer["scenes"]:
        s.pop("pov")
    line = _import(ws, "s001", answer)
    assert line == f"error s001: $.scenes[0]: missing pov (+{len(answer['scenes']) - 1} more)"


def test_first_person_pov_is_accepted(ws: Path) -> None:
    answer = _scene_answer(ws, "s001")
    answer["scenes"][0]["pov"] = "narrator (first person), Utterson"
    answer["scenes"][1]["pov"] = "narrator (first person)"
    assert _import(ws, "s001", answer).startswith("ok s001: ")
    povs = {i.fields["pov"] for i in codex.Codex(ws).live("scene")}
    assert {"narrator (first person), Utterson", "narrator (first person)"} <= povs


def test_tiers_are_three_valued(base: Path) -> None:
    assert packets.TIERS == ("cheap", "standard", "strong")
    assert packets.TIER == {"entities": "strong", "scenes": "standard"}
    assert set(packets.TIER.values()) <= set(packets.TIERS)
    for p in packets.load_plan(base)["packets"]:
        assert p["tier"] in packets.TIERS


def test_payoffs_link_across_packets_by_label_or_id(ws: Path) -> None:
    first = _scene_answer(ws, "s001")
    planted = next(su for s in first["scenes"] for su in s["setups"])
    planted["label"] = "the locked door"
    assert _import(ws, "s001", first).startswith("ok s001: ")
    cx = codex.Codex(ws)
    target = next(i for i in cx.live("setup") if i.fields["label"] == "the locked door")
    assert f"the locked door [{target.id}]" in packets.render(ws, packets.load_plan(ws), "s002")

    draft = _draft(ws)
    second = _scene_answer(ws, "s002")
    doc = packets.load_plan(ws)
    units = {u["scene"]: u for u in _status(ws, "s002")["inputs"]["units"]}
    scene = second["scenes"][0]
    lo, hi = units[scene["scene"]]["paras"]
    quotes = [_unique_quote(draft, lo, hi, skip=k) for k in range(4)]
    assert all(quotes), doc["packets"]
    scene["setups"] = [
        {
            "label": "door opened",
            "side": "payoff",
            "quote": quotes[0],
            "pays_off": "THE LOCKED DOOR",
        },
        {"label": "door again", "side": "payoff", "quote": quotes[1], "pays_off": target.id},
        {"label": "the locked door", "side": "payoff", "quote": quotes[2]},
        {"label": "nothing", "side": "payoff", "quote": quotes[3], "pays_off": "never planted"},
    ]
    line = _import(ws, "s002", second)
    assert line.startswith("ok s002: ") and "1 payoff(s) left unlinked" in line
    pays = [i for i in codex.Codex(ws).live("setup") if i.fields["side"] == "payoff"]
    linked = {i.fields["label"]: [x["to"] for x in i.links] for i in pays}
    assert linked == {
        "door opened": [target.id],
        "door again": [target.id],
        "the locked door": [target.id],
        "nothing": [],
    }


def test_payoff_in_the_scene_of_its_setup_is_reported(ws: Path) -> None:
    answer = _scene_answer(ws, "s001")
    draft = _draft(ws)
    scene = answer["scenes"][0]
    units = {u["scene"]: u for u in _status(ws, "s001")["inputs"]["units"]}
    lo, hi = units[scene["scene"]]["paras"]
    scene["setups"].append(
        {
            "label": "closed",
            "side": "payoff",
            "quote": _unique_quote(draft, lo, hi, skip=1),
            "pays_off": scene["setups"][0]["label"],
        }
    )
    line = _import(ws, "s001", answer)
    assert line.startswith("ok s001: ") and "1 payoff(s) in the scene of their setup" in line


def test_scene_packet_lists_known_entities_and_speakers(ws: Path) -> None:
    ut = _entity(
        ws, kind="character", name="Utterson", aliases=["Mr. Utterson"], titles=["the lawyer"]
    )
    text = packets.render(ws, packets.load_plan(ws), "s001")
    head, _, body = text.partition("\n## ")
    for words in ("pov", "narrator (first person)", "unspecified", "same scene", "who is who"):
        assert words in head
    facts = [line for b in body.split("\n## ") for line in b.split("\n")[1:4]]
    known = [x for x in facts if x.startswith("known: ")]
    assert known and all(f"Utterson [{ut.id}]" in x for x in known)
    assert any(f"Utterson [{ut.id}] (Mr. Utterson" in x for x in known)
    others = [x for x in facts if x.startswith("other names: ")]
    assert all("Utterson" not in x for x in others)
    assert any(x.startswith("speakers: ") for x in facts)


def test_output_tokens_per_scene_recorded(ws: Path) -> None:
    answer = _scene_answer(ws, "s001")
    assert _import(ws, "s001", answer).startswith("ok s001: ")
    p = _status(ws, "s001")
    compact = json.dumps(answer, ensure_ascii=False, separators=(",", ":"))
    assert p["out_tokens"] == packets.tokens(compact)
    assert packets.output_tokens_per_scene(answer) == round(
        packets.tokens(compact) / len(answer["scenes"]), 1
    )
    assert any("out tokens/scene" in x for x in packets.status_lines(packets.load_plan(ws)))


def test_reindex_inserted_scene_mid_book_packs_only_it(tmp_path: Path) -> None:
    def edit(sc: list[list[str]]) -> list[list[str]]:
        return [*sc[:7], _scenes_of_book(30)[25], *sc[7:]]

    starts = [0, 5, 11, 16]  # the chapters keep their numbers; later scenes get new ids
    root, _first, doc, _ = _reindexed(tmp_path, edit, starts=starts)
    draft = _draft(root)
    assert len(draft.scenes) == 21
    assert _packed(doc) == [draft.scenes[7]["id"]]
    for p in [x for x in doc["packets"] if x["kind"] == "scenes"]:
        assert _import(root, p["id"], _scene_answer(root, p["id"])).startswith("ok ")
    assert len(codex.Codex(root).live("scene")) == 21


def test_reindex_moved_scene_is_not_read_again(tmp_path: Path) -> None:
    def edit(sc: list[list[str]]) -> list[list[str]]:
        moved = sc.pop(7)
        sc.insert(13, moved)
        return sc

    root, _, doc, _ = _reindexed(tmp_path, edit, starts=[0, 5, 9, 15])  # headings stay put
    assert _packed(doc) == []
    cx = codex.Codex(root)
    draft = _draft(root)
    assert len(cx.live("scene")) == 20
    assert set(cx.scenes_by_unit(draft.anchors)) == {s["id"] for s in draft.scenes}


def _names(ws: Path) -> list[str]:
    return [c["name"] for c in packets.load_draft(ws).pre["candidates"]]


def test_rejected_names_are_not_offered_again(ws: Path) -> None:
    pre = _draft(ws).pre["candidates"]
    reject = next(c for c in pre if c["count"] >= 2 and c["name"] != "Utterson")
    ents = [{"name": "Utterson", "kind": "character"}]
    assert _import(ws, "e1", {"entities": ents, "rejects": [reject["name"]]}).startswith("ok ")
    key = reject["name"].casefold()
    assert packets.load_rejects(ws)[key] == {"draft": "v001", "count": reject["count"]}
    packets.plan(ws)
    assert reject["name"] not in _names(ws)
    # A name that grew 3x and by 5 occurrences since it was rejected is offered again.
    path = packets.rejects_path(ws)
    rejects = json.loads(path.read_text("utf-8"))
    rejects[key]["count"] = max(1, (reject["count"] - 5) // 3)
    path.write_text(json.dumps(rejects), "utf-8")
    packets.plan(ws)
    grown = reject["count"] >= 3 * rejects[key]["count"] and (
        reject["count"] - rejects[key]["count"] >= 5
    )
    assert (reject["name"] in _names(ws)) == grown


def test_rejects_apply_to_changed_plans_and_return_on_growth(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "work.toml").write_text('slug = "re"\nlanguage = "en"\n', "utf-8")
    _write_book(root, _scenes_of_book(20), tmp_path)
    _index_all(root)

    def book(extra: int) -> list[list[str]]:
        sc = _scenes_of_book(20)
        sc[4] = [*sc[4], "Then Zephaniah Quillfeather came, and Zephaniah Quillfeather left."]
        sc[4] += ["Zephaniah Quillfeather spoke once more."] * extra
        return sc

    _write_book(root, book(0), tmp_path)
    sync.sync(root)
    packets.plan(root, changed=True)
    assert _names(root) == ["Zephaniah Quillfeather"]
    answer = {"entities": [], "rejects": ["Zephaniah  Quillfeather"]}
    assert _import(root, "e1", answer) == "ok e1: 0 items"
    assert packets.load_rejects(root)["zephaniah quillfeather"]["count"] == 2
    doc = packets.plan(root, changed=True)
    assert doc["stats"]["entity_packets"] == 0 and _names(root) == []
    # Seen 3x as often and 5 more times than when rejected: offered again.
    _write_book(root, book(6), tmp_path)
    sync.sync(root)
    doc = packets.plan(root, changed=True)
    assert _names(root) == ["Zephaniah Quillfeather"] and doc["stats"]["entity_packets"] == 1
    # The full plan drops a rejected name as well.
    assert _import(root, "e1", answer).startswith("ok ")
    packets.plan(root)
    assert "Zephaniah Quillfeather" not in _names(root)
