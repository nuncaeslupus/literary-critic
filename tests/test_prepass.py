import json
from pathlib import Path
from typing import Any

import pytest

from litcritic import corpus, prepass
from litcritic.cli import main

GOLD = Path(__file__).parent / "fixtures" / "gold"
TEXTS = {"jekyll-hyde": "en", "marianela": "es"}


@pytest.fixture(scope="module")
def works(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    out = {}
    for slug, lang in TEXTS.items():
        root = tmp_path_factory.mktemp(slug)
        (root / "work.toml").write_text(f'slug = "{slug}"\nlanguage = "{lang}"\n', "utf-8")
        assert main(["ingest", str(corpus.get(slug).path), "--workspace", str(root)]) == 0
        assert main(["anchor", "--workspace", str(root)]) == 0
        out[slug] = root
    return out


@pytest.fixture(scope="module")
def results(works: dict[str, Path]) -> dict[str, dict[str, Any]]:
    return {slug: prepass.run(root) for slug, root in works.items()}


def _gold(slug: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((GOLD / f"{slug}.json").read_text(encoding="utf-8"))
    return data


def _scenes(n: int) -> list[dict[str, Any]]:
    return [{"id": "c01.s1", "start": 0, "end": n - 1, "words": 0}]


def _names(paras: list[str], lang: str) -> dict[str, dict[str, Any]]:
    out = prepass.extract(
        paras, [f"c01.s1.p{i + 1}" for i in range(len(paras))], _scenes(len(paras)), lang
    )
    return {c["name"]: c for c in out["candidates"]}


# --- gate --------------------------------------------------------------------------


def test_prepass_recall_on_gold(results: dict[str, dict[str, Any]]) -> None:
    for slug, res in results.items():
        score = prepass.score(res["candidates"], _gold(slug))
        assert score["recall"] >= 0.92, (slug, score["missed"])


def test_candidate_list_tokens_bounded(results: dict[str, dict[str, Any]]) -> None:
    for slug, res in results.items():
        r = res["render"]
        assert r["tokens"] <= 0.12 * res["stats"]["text_tokens"], (slug, r["tokens"])
        assert r["tokens"] == -(-len(r["text"]) // 4)


# --- shape -------------------------------------------------------------------------


def test_candidates_have_counts_first_quote_and_short_snippets(
    results: dict[str, dict[str, Any]],
) -> None:
    res = results["jekyll-hyde"]
    by_name = {c["name"]: c for c in res["candidates"]}
    ut = next(c for c in res["candidates"] if "Utterson" in c["forms"])
    assert ut["count"] >= 100
    assert "Mr. Utterson" in ut["forms"]
    assert ut["first"]["quote"] and ut["first"]["para"].startswith("c")
    for c in by_name.values():
        assert 1 <= len(c["snippets"]) <= 2
        for s in c["snippets"]:
            left, _, rest = s.partition("[")
            right = rest.partition("]")[2]
            assert len(left.split()) <= 12 and len(right.split()) <= 12


def test_role_titles_and_speakers_found(results: dict[str, dict[str, Any]]) -> None:
    en = {c["name"]: c for c in results["jekyll-hyde"]["candidates"]}
    assert en["the lawyer"]["kind_hint"] == "role"
    es = {c["name"]: c for c in results["marianela"]["candidates"]}
    assert "el médico" in es
    for res in results.values():
        tags = [t for s in res["speakers"].values() for t in s]
        assert len(tags) >= 20


def test_scenes_list_words_range_and_names(results: dict[str, dict[str, Any]]) -> None:
    res = results["marianela"]
    total = sum(s["words"] for s in res["scenes"].values())
    assert total > 40000
    assert any("Nela" in s["names"] for s in res["scenes"].values())
    for s in res["scenes"].values():
        assert s["paras"][0] <= s["paras"][1]


# --- rules -------------------------------------------------------------------------


def test_connector_does_not_join_common_noun_chain() -> None:
    paras = [
        "Se fue a los Madriles del Rey de España con Ana Pérez de Castro.",
        "Volvió de los Madriles al fin; el rey estaba en España y Ana Pérez de Castro también.",
        "Un rey no es nada.",
    ]
    names = _names(paras, "es")
    assert "Madriles del Rey de España" not in names
    assert "Madriles" in names
    assert "Ana Pérez de Castro" in names


def test_stop_lists_filter_months_weekdays_and_god() -> None:
    paras = [
        "Llegó en Mayo, un Lunes, y dijo que Dios lo quería así. Vio a Ramiro.",
        "Otro Lunes de Mayo, por Dios, volvió Ramiro.",
    ]
    names = _names(paras, "es")
    assert "Ramiro" in names
    assert not {"Mayo", "Lunes", "Dios"} & set(names)
    names_en = _names(["It was in May, on a Monday, by God, that Bob came.", "So Bob left."], "en")
    assert "Bob" in names_en and not {"May", "Monday", "God"} & set(names_en)


def test_honorific_and_role_title() -> None:
    paras = [
        "Then came Dr. Ames, and the butler opened.",
        "The butler bowed; the butler smiled; the butler left.",
        '"Go," said the butler. "No," said Dr. Ames.',
    ]
    out = prepass.extract(paras, ["a.p1", "a.p2", "a.p3"], _scenes(3), "en")
    names = {c["name"]: c for c in out["candidates"]}
    assert "Dr. Ames" in names["Ames"]["forms"] or names.get("Dr. Ames")
    assert names["the butler"]["count"] == 5
    who = [t["who"] for t in out["speakers"]["c01.s1"]]
    assert "the butler" in who and any("Ames" in w for w in who)


def test_spanish_raya_speaker_tags() -> None:
    paras = [
        "—Ven aquí —dijo Remedios—. Ahora mismo.",
        "--No quiero--repuso el forastero.",
        "Remedios calló.",
    ]
    out = prepass.extract(paras, ["a.p1", "a.p2", "a.p3"], _scenes(3), "es")
    who = [t["who"] for t in out["speakers"]["c01.s1"]]
    assert who == ["Remedios", "el forastero"]


def test_render_budget_trims_snippets_of_frequent_names() -> None:
    paras = [f"Here Alba met Bruno and Ciro in Dover, day {i}." for i in range(60)]
    out = prepass.extract(paras, [f"a.p{i}" for i in range(60)], _scenes(60), "en")
    full = prepass.render(out["candidates"], budget=None)
    tight = prepass.render(out["candidates"], budget=full["tokens"] - 20)
    assert tight["tokens"] <= full["tokens"] - 20
    assert tight["text"].count("\n  ") < full["text"].count("\n  ")


def test_score_matches_forms_and_treats_minor_as_neutral() -> None:
    gold = {
        "entities": [
            {"kind": "character", "name": "Ann Lee", "aliases": ["Ann Lee", "Miss Lee"]},
            {"kind": "place", "name": "Dover", "aliases": ["Dover"]},
        ],
        "minor": [{"kind": "place", "name": "Calais"}],
    }
    cands = [
        {"name": "Lee", "forms": ["Miss Lee"]},
        {"name": "Calais", "forms": ["Calais"]},
        {"name": "Zed", "forms": ["Zed"]},
    ]
    s = prepass.score(cands, gold)
    assert s["recall"] == 0.5 and s["missed"] == ["Dover"]
    assert s["precision_strict"] == pytest.approx(1 / 3)
    assert s["precision_lenient"] == pytest.approx(2 / 3)


def test_cli_writes_prepass_json(
    works: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root = works["jekyll-hyde"]
    assert main(["index", "prepass", "--workspace", str(root), "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    data = json.loads((root / "index" / "work" / "prepass.json").read_text(encoding="utf-8"))
    assert summary["candidates"] == len(data["candidates"]) > 0
    assert set(data) >= {"candidates", "speakers", "scenes", "render", "stats"}
    assert main(["index", "prepass", "--workspace", str(root), "--version", "v009"]) == 2
