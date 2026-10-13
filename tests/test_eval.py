"""`lc index eval`, `lc index compare`, `lc index cost` (index T5)."""

import io
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from litcritic import codex, corpus, index_eval, packets
from litcritic.cli import main

FIX = Path(__file__).parent / "fixtures"
GOLD = FIX / "gold"
ANSWERS = FIX / "answers"
TEXTS = {"jekyll-hyde": "en", "marianela": "es"}


def _build(root: Path, slug: str) -> Path:
    root.mkdir()
    (root / "work.toml").write_text(f'slug = "{slug}"\nlanguage = "{TEXTS[slug]}"\n', "utf-8")
    assert main(["ingest", str(corpus.get(slug).path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    packets.plan(root)
    return root


@pytest.fixture(scope="module")
def planned(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return {s: _build(tmp_path_factory.mktemp(s) / "ws", s) for s in TEXTS}


def _gold(slug: str) -> dict[str, Any]:
    out: dict[str, Any] = json.loads((GOLD / f"{slug}.json").read_text("utf-8"))
    return out


def _recorded(slug: str) -> list[Path]:
    return sorted(ANSWERS.glob(f"{slug}-e*.json"))


@pytest.fixture(scope="module")
def imported(planned: dict[str, Path], tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """The recorded strong-tier answers to every entity packet, imported."""
    out = {}
    for slug, base in planned.items():
        root = tmp_path_factory.mktemp(f"{slug}-imp") / "ws"
        shutil.copytree(base, root)
        doc = packets.load_plan(root)
        ids = [p["id"] for p in doc["packets"] if p["kind"] == "entities"]
        assert [f.stem.split("-")[-1] for f in _recorded(slug)] == ids, slug
        for f in _recorded(slug):
            pid = f.stem.split("-")[-1]
            line = packets.import_answer(root, pid, f.read_text("utf-8"))
            assert line.startswith(f"ok {pid}: "), line
        out[slug] = root
    return out


# --- the gate ----------------------------------------------------------------------

# What the recorded answers score, computed once and pinned: jekyll-hyde 12/12 gold
# entities and no false entity (5 more match minor gold entries); marianela misses six
# places and groups mentioned in passing (España, Europa, Cantabria, Poniente, the
# Escolapios) and Ulises Bull, and counts Nela's dead mother as a split of Nela (her
# name normalises onto the gold alias "la de la Canela").
EXPECTED = {
    "jekyll-hyde": {
        "true": 12,
        "false": 0,
        "neutral": 5,
        "reached": 12,
        "gold_entities": 12,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "alias_merge_errors": 0,
        "reference_recall": 0.9917,
    },
    "marianela": {
        "true": 32,
        "false": 0,
        "neutral": 1,
        "reached": 31,
        "gold_entities": 37,
        "precision": 1.0,
        "recall": 0.8378,
        "f1": 0.9117,
        "alias_merge_errors": 1,
        "reference_recall": 0.9676,
    },
}


def test_eval_scores_against_gold(imported: dict[str, Path]) -> None:
    for slug, root in imported.items():
        rep = index_eval.evaluate(root, _gold(slug))
        got = {k: rep[k] for k in EXPECTED[slug] if k != "reference_recall"}
        got["reference_recall"] = rep["reference_recall"]["recall"]
        assert got == EXPECTED[slug], slug
        assert rep["precision"] == rep["true"] / (rep["true"] + rep["false"])
        assert rep["recall"] == round(rep["reached"] / rep["gold_entities"], 4)
    mn = index_eval.evaluate(imported["marianela"], _gold("marianela"))
    assert mn["splits"] == [{"gold": "Nela", "entities": ["Marianela", "la Canela"]}]
    assert mn["merges"] == [] and mn["kind_errors"] == []


# --- scoring rules -----------------------------------------------------------------


def _e(name: str, kind: str = "character", **more: Any) -> dict[str, Any]:
    return {"name": name, "kind": kind, **more}


GOLD_TOY = {
    "entities": [
        {"kind": "character", "name": "Ann Lee", "aliases": ["Mrs. Lee", "Ann"]},
        {"kind": "character", "name": "Bo", "aliases": ["the doctor"]},
        {"kind": "place", "name": "Rome", "aliases": ["Rome"]},
        {"kind": "character", "name": "Cy Lee", "aliases": ["Cy", "the son of Lee"]},
    ],
    "minor": [{"kind": "character", "name": "Old Tom Wells"}],
}


def test_entity_scores_rules() -> None:
    ents = [
        _e("Ann", aliases=["Mrs. Lee"]),  # hit: forms equal after dropping honorifics
        _e("Zed"),  # no gold form: false
        _e("Doc", titles=["the doctor"]),  # hit through a title
        _e("Bo", kind="place"),  # hit, wrong kind, and a split of Bo
        _e("Tom Wells"),  # inside a minor entry: neutral
        _e("Rome", kind="motif"),  # a kind the gold never uses: out of scope
        _e("Cy", aliases=["Ann Lee"]),  # reaches Cy and Ann: a merge, and splits Ann
    ]
    rep = index_eval.entity_scores(ents, GOLD_TOY)
    assert (rep["true"], rep["false"], rep["neutral"], rep["scored"]) == (4, 1, 1, 6)
    assert rep["precision"] == 0.8 and rep["recall"] == 0.75 and rep["missed"] == ["Rome"]
    assert rep["f1"] == round(2 * 0.8 * 0.75 / 1.55, 4)
    assert rep["out_of_scope"] == ["Rome"] and rep["false_positives"] == ["Zed"]
    assert rep["splits"] == [
        {"gold": "Ann Lee", "entities": ["Ann", "Cy"]},
        {"gold": "Bo", "entities": ["Bo", "Doc"]},
    ]
    assert rep["merges"] == [{"entity": "Cy", "gold": ["Ann Lee", "Cy Lee"]}]
    assert rep["alias_merge_errors"] == 3
    assert rep["kind_errors"] == [{"entity": "Bo", "kind": "place"}]


def test_exact_forms_take_precedence_over_normalised() -> None:
    gold = {
        "entities": [
            {"kind": "character", "name": "Mr. Centeno", "aliases": ["Centeno"]},
            {"kind": "character", "name": "Ana", "aliases": ["the wife of Centeno"]},
        ]
    }
    # "Mrs. Centeno" and "Mr. Centeno" both normalise to (centeno)
    rep = index_eval.entity_scores([_e("Centeno"), _e("Ana")], gold)
    assert rep["alias_merge_errors"] == 0 and rep["recall"] == 1.0
    gold["entities"][1]["aliases"] = ["Mrs. Centeno"]
    rep = index_eval.entity_scores([_e("Mr. Centeno"), _e("Ana", aliases=["Mrs. Centeno"])], gold)
    assert rep["merges"] == [] and rep["splits"] == []  # each shares an exact form
    rep = index_eval.entity_scores([_e("Centeno Senior", aliases=["Mrs. Centeno"])], gold)
    assert rep["merges"] == []  # exact "mrs. centeno" is Ana's only
    rep = index_eval.entity_scores([_e("Don Centeno")], gold)
    assert rep["merges"] == [{"entity": "Don Centeno", "gold": ["Mr. Centeno", "Ana"]}]


def test_reference_recall_counts_mentions_of_matching_entities(
    planned: dict[str, Path], tmp_path: Path
) -> None:
    root = tmp_path / "ws"
    shutil.copytree(planned["jekyll-hyde"], root)
    cx = codex.Codex(root)
    cx.add("entity", "Poole", {"kind": "character", "name": "Poole"})
    gold = {"entities": [{"kind": "character", "name": "Poole", "aliases": [], "occurrences": 70}]}
    rep = index_eval.evaluate(root, gold)
    found = rep["reference_recall"]["hits"]
    assert 0 < found < 70 and rep["reference_recall"]["recall"] == round(found / 70, 4)
    gold["entities"][0]["occurrences"] = 5
    assert index_eval.evaluate(root, gold)["reference_recall"]["hits"] == 5  # capped
    assert "reference_recall" not in index_eval.evaluate(root, gold, references=False)
    with pytest.raises(index_eval.EvalError):
        index_eval.evaluate(root, {"entities": []})


# --- comparing tiers (D-4) ---------------------------------------------------------


def test_compare_entities() -> None:
    ref = {
        "entities": [
            _e("Ann Lee", aliases=["Ann"]),
            _e("Bo"),
            _e("Rome", kind="place"),
            _e("Cy"),
        ]
    }
    assert index_eval.compare(ref, ref)["min_agreement"] == 1.0
    ans = {
        "entities": [
            _e("Mrs. Lee", aliases=["Ann"]),
            _e("Ann Lee"),  # a split of Ann Lee
            _e("Rome", kind="object"),  # kind disagrees
            _e("Zed"),  # not in the reference
        ]
    }
    rep = index_eval.compare(ans, ref)
    assert (rep["recall"], rep["precision"], rep["kind_agreement"]) == (0.5, 0.75, 0.6667)
    assert (rep["splits"], rep["merges"]) == (1, 0)
    assert rep["min_agreement"] == 0.5 and rep["agrees"] is False


def _scene(sid: str, **more: Any) -> dict[str, Any]:
    base = {"scene": sid, "summary": "One two three.", "pov": "Ann", "location": "the hall"}
    return {**base, "time": "night", **more}


def test_compare_scenes() -> None:
    ref = {
        "scenes": [
            _scene("c01.s1", setups=[{"label": "a", "side": "setup", "quote": "x"}]),
            _scene("c01.s2", pov="Bo"),
            _scene("c01.s3", time="dawn"),
        ]
    }
    ans = {
        "scenes": [
            _scene("c01.s1", location="Hall", summary="One two."),  # article and case dropped
            _scene("c01.s2", pov="Ann"),
            _scene("c01.s3", time="Dawn.", entities=[{"name": "Zed", "kind": "character"}]),
        ]
    }
    rep = index_eval.compare(ans, ref)
    assert rep["common_scenes"] == 3
    assert (rep["pov_agreement"], rep["location_agreement"], rep["time_agreement"]) == (
        0.6667,
        1.0,
        1.0,
    )
    assert (rep["setups_answer"], rep["setups_reference"]) == (0, 1)
    assert (rep["summary_words_answer"], rep["summary_words_reference"]) == (2.7, 3.0)
    assert (rep["new_entities_answer"], rep["new_entities_reference"]) == (1, 0)
    assert rep["min_agreement"] == 0.6667 and not rep["agrees"]
    short = {"scenes": [ans["scenes"][0], ans["scenes"][2]]}
    assert index_eval.compare(short, ref)["min_agreement"] == 0.6667  # coverage 2/3
    with pytest.raises(index_eval.EvalError):
        index_eval.compare(ans, {"entities": []})
    with pytest.raises(index_eval.EvalError):
        index_eval.compare({"x": 1}, ref)


# --- cost --------------------------------------------------------------------------


def test_cost_records_tokens_calls_and_wall_time(
    planned: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "ws"
    shutil.copytree(planned["jekyll-hyde"], root)
    w = ["--workspace", str(root)]
    before = index_eval.cost(root)
    t = before["total"]
    doc = packets.load_plan(root)
    assert t["in_tokens"] == sum(p["tokens"] for p in doc["packets"])
    assert t["calls_planned"] == 2 * len(doc["packets"]) and t["calls_recorded"] == 0
    assert t["calls_planned_chained"] == len(doc["packets"]) + 1
    assert t["in_tokens_per_1k_text_tokens"] == round(1000 * t["in_tokens"] / t["text_tokens"], 1)
    assert t["wall_seconds_sum"] is None and t["out_tokens_per_scene"] is None
    assert main(["index", "packet", "e1", *w]) == 0
    capsys.readouterr()
    answer = (ANSWERS / "jekyll-hyde-e1.json").read_text("utf-8")
    assert main(["index", "import", "e1", "--file", str(ANSWERS / "jekyll-hyde-e1.json"), *w]) == 0
    assert capsys.readouterr().out.startswith("ok e1: ")
    rep = index_eval.cost(root)
    e1 = rep["packets"][0]
    assert e1["id"] == "e1" and e1["status"] == "done" and e1["calls"] == 2
    assert e1["out_tokens"] == packets.tokens(packets._compact(json.loads(answer)))
    assert e1["seconds"] is not None and e1["seconds"] >= 0
    t = rep["total"]
    assert t["out_tokens"] == e1["out_tokens"] and t["calls_recorded"] == 2
    assert t["timed_packets"] == 1 and t["wall_seconds_span"] == e1["seconds"]
    # a refused answer is one more recorded call; a re-plan keeps the record
    assert packets.import_answer(root, "s001", "[]").startswith("error ")
    packets.plan(root)
    rep = index_eval.cost(root)
    assert rep["packets"][0]["calls"] == 2 and rep["total"]["calls_recorded"] == 3
    assert main(["index", "cost", *w]) == 0
    out = capsys.readouterr().out
    assert out.startswith("e1 entities strong done: in ~") and "wall time: " in out


# --- commands ----------------------------------------------------------------------


def test_cli_eval_compare_and_cost(
    imported: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = imported["jekyll-hyde"]
    w = ["--workspace", str(root)]
    gold = str(GOLD / "jekyll-hyde.json")
    assert main(["index", "eval", *w, "--gold", gold, "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["f1"] == 1.0 and rep["reference_recall"]["gold"] == 601
    assert main(["index", "eval", *w, "--gold", gold]) == 0
    assert capsys.readouterr().out.startswith("entities: precision 1.0 (12 hits, 0 false")
    bad = tmp_path / "bad.json"
    bad.write_text("{", "utf-8")
    assert main(["index", "eval", *w, "--gold", str(bad)]) == 2
    assert "not valid JSON" in capsys.readouterr().err
    a = str(ANSWERS / "marianela-e1.json")
    assert main(["index", "compare", "--answers", a, "--reference", a]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("entities: entities 23, reference_entities 23, recall 1.0")
    assert out[1].startswith("agrees with the reference (lowest agreement 1.0")
    b = str(ANSWERS / "marianela-e2.json")
    assert main(["index", "compare", "--answers", b, "--reference", a, "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["agrees"] is False and rep["precision"] == round(2 / 12, 4)
    assert main(["index", "cost", *w, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["total"]["packets_done"] == 1
    assert main(["index", "cost", "--workspace", str(tmp_path / "none")]) == 2


def test_import_next_marks_the_next_packet_started(
    planned: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "ws"
    shutil.copytree(planned["jekyll-hyde"], root)
    monkeypatch.setattr("sys.stdin", io.StringIO((ANSWERS / "jekyll-hyde-e1.json").read_text()))
    w = ["--workspace", str(root)]
    assert main(["index", "import", "e1", "--file", "-", "--next", *w]) == 0
    doc = packets.load_plan(root)
    e1, s1 = doc["packets"][0], doc["packets"][1]
    assert "started" not in e1 and "finished" in e1  # imported without a recorded print
    assert s1["prints"] == 1 and "started" in s1 and s1["status"] == "todo"
