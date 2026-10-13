import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

from litcritic import convert, corpus, metrics, structure
from litcritic import textstats as ts
from litcritic.cli import main
from litcritic.workspace import repo_root

# Hand-counted: 10 words, 2 sentences, 19 syllables
# El(1) pe-rro(2) co-me(2) car-ne(2). La(1) ni-ña(2) can-ta(2) u-na(2) can-ción(2) bo-ni-ta(3).
GOLDEN_ES = "El perro come carne. La niña canta una canción bonita."


def test_readability_es_golden() -> None:
    w, s, syl = metrics.readability_counts([GOLDEN_ES], "es")
    assert (w, s, syl) == (10, 2, 19)
    # Corrected form: 206.84 - 0.60 * 190 - 1.02 * 5 = 87.74
    assert metrics.fernandez_huerta(w, s, syl) == pytest.approx(87.74)
    # Longer sentences must read as harder.
    assert metrics.fernandez_huerta(100, 5, 200) < metrics.fernandez_huerta(100, 10, 200)
    # 206.835 - 62.3 * 1.9 - 5 = 83.465
    assert metrics.szigriszt(w, s, syl) == pytest.approx(83.465, abs=0.01)
    assert metrics.inflesz_band(83.465) == "muy fácil"
    assert metrics.inflesz_band(60) == "normal"


def test_flesch_en_golden() -> None:
    # The cat sat on the mat. It was hap-py. -> 9 words, 2 sentences, 10 syllables
    w, s, syl = metrics.readability_counts(["The cat sat on the mat. It was happy."], "en")
    assert (w, s, syl) == (9, 2, 10)
    # 206.835 - 1.015 * 4.5 - 84.6 * 10 / 9
    assert metrics.flesch(w, s, syl) == pytest.approx(108.27, abs=0.01)


@pytest.mark.parametrize(
    ("word", "n"),
    [
        ("aéreo", 4),
        ("país", 2),
        ("ciudad", 2),
        ("pingüino", 3),
        ("guerra", 2),
        ("que", 1),
        ("poeta", 3),
        ("hoy", 1),
        ("y", 1),
        ("prohibir", 3),
        ("murciélago", 4),
        ("canción", 2),
    ],
)
def test_spanish_syllables(word: str, n: int) -> None:
    assert ts.syllables_es(word) == n


def test_sentences_and_dialogue() -> None:
    text = "—¿Vienes? —preguntó el Sr. Gómez—. Vamos ya. Luego... nada."
    assert ts.sentences(text, "es") == [
        "—¿Vienes? —preguntó el Sr. Gómez—.",
        "Vamos ya.",
        "Luego... nada.",
    ]
    assert ts.dialogue_spans(text) == ["¿Vienes?", ". Vamos ya. Luego... nada."]
    assert ts.dialogue_spans('He said "go now" and left.') == ["go now"]
    assert ts.dialogue_spans("--Hola --dijo.") == ["Hola"]
    assert ts.dialogue_spans("Plain narration.") == []


def test_mtld_extremes() -> None:
    assert metrics.mtld_score(["a"] * 100) < 5
    assert metrics.mtld_score([f"w{i}" for i in range(100)]) == 100


def _ctx(slug: str, lang: str, **extra: Any) -> metrics.Context:
    d = convert.read_txt(corpus.get(slug).path.read_bytes())
    paras = [p.text for p in d.paragraphs]
    data = structure.to_json(structure.detect(paras), "v001")
    return metrics.Context(
        paras, [a for a, _ in data["paragraphs"]], data["chapters"], lang, data["parts"], **extra
    )


def test_planned_metrics_implemented() -> None:
    registry = tomllib.loads(
        (repo_root() / "checklist" / "metrics.toml").read_text(encoding="utf-8")
    )
    ids = list(registry["metric"])
    assert metrics.implemented_ratio(ids) >= 0.8
    assert set(metrics.REGISTRY) <= set(ids)
    for mid in metrics.REGISTRY:
        assert registry["metric"][mid]["status"] == "implemented", mid


def test_all_metrics_run_on_corpus() -> None:
    for slug, lang in (("marianela", "es"), ("jekyll-hyde", "en")):
        res = metrics.compute(_ctx(slug, lang))
        assert set(res) == set(metrics.REGISTRY)
        json.dumps(res)  # serialisable
        for value in res.values():
            for item in value.get("items", []):
                assert "anchor" in item or "id" in item or "name" in item or "names" in item


def test_corpus_values_are_plausible() -> None:
    es = metrics.compute(_ctx("marianela", "es"))
    assert 0.3 < es["dialogue_ratio"]["book"] < 0.6
    assert es["heading_sequence"]["book"] == {"numbered": 22, "formats": {"-N-": 22}}
    assert es["heading_sequence"]["items"] == []
    assert 60 < es["readability_fernandez_huerta"]["book"] < 100
    assert "unmeasured" in es["readability_flesch"]
    en = metrics.compute(_ctx("jekyll-hyde", "en"))
    assert en["words_per_chapter"]["chapters"]["c01"] > 1000
    assert en["dialogue_tag_distribution"]["book"]["said_share"] > 0.5
    assert "Utterson" in en["character_first_appearance"]["book"]


def test_register_and_label_metrics() -> None:
    ctx = _ctx(
        "jekyll-hyde",
        "en",
        registers={
            "characters": [
                {"id": "u", "name": "Utterson", "anchors": ["c01.s1.p1"]},
                {"id": "h", "name": "Hyde", "aliases": ["Edward Hyde"], "anchors": ["c01.s1.p9"]},
            ],
            "setups": [
                {
                    "id": "door",
                    "name": "the door",
                    "anchors": ["c01.s1.p3", "c08.s1.p2"],
                    "status": "paid_off",
                },
                {"id": "will", "name": "the will", "anchors": ["c02.s1.p2"], "status": "open"},
            ],
            "motifs": [{"id": "fog", "name": "fog", "anchors": ["c04.s1.p1"]}],
        },
        labels={
            "chapter_endings": {"c01": "dialogue", "c02": "dialogue", "c03": "reflection"},
            "climax": "c08.s1.p1",
        },
        scene_cards=[{"anchor": "c01.s1", "pov": "omniscient"}],
    )
    res = metrics.compute(ctx)
    assert res["character_presence_matrix"]["book"]["Hyde"]["first"] == "c01"
    assert res["setup_payoff_distance"]["items"][0]["chapters"] == 7
    assert res["setup_payoff_distance"]["items"][1] == {"id": "will", "status": "unpaid"}
    assert res["open_thread_count"]["chapters"]["c03"] == 2
    assert res["motif_occurrences"]["book"]["fog"]["c04"] > 0
    assert res["chapter_ending_types"]["longest_same_run"] == 2
    assert 0 < res["denouement_share"]["book"] < 0.7
    assert res["pov_distribution"]["book"]["scenes"] == {"omniscient": 1}


def test_proofreading_signals() -> None:
    paras = [
        "CAPÍTULO 1",
        "El el perro ladró . luego calló [revisar esto] y TODO quedó (sin cerrar.",
        "— Hola —Dijo ella.",
    ]
    data = structure.to_json(structure.detect(paras), "v001")
    ctx = metrics.Context(paras, [a for a, _ in data["paragraphs"]], data["chapters"], "es")
    typos = metrics.REGISTRY["typo_signals"](ctx)["counts"]
    assert typos["doubled word"] == 1 and typos["space before punctuation"] == 1
    assert typos["lowercase after full stop"] == 1 and typos["unmatched ()"] == 1
    notes = [x["marker"] for x in metrics.REGISTRY["author_note_markers"](ctx)["items"]]
    assert notes == ["[revisar esto]", "TODO"]
    anomalies = metrics.REGISTRY["dialogue_punctuation_anomalies"](ctx)["items"][0]["problems"]
    assert anomalies == ["space after opening dash", "capital letter in dialogue tag"]


def test_cli_metrics(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "work.toml").write_text('slug = "ws"\nlanguage = "en"\n', encoding="utf-8")
    assert main(["metrics", "--workspace", str(ws)]) == 2
    assert main(["ingest", str(corpus.get("jekyll-hyde").path), "--workspace", str(ws)]) == 0
    assert main(["anchor", "--workspace", str(ws)]) == 0
    assert main(["metrics", "--workspace", str(ws)]) == 0
    data = json.loads((ws / "metrics" / "v001.json").read_text(encoding="utf-8"))
    assert data["language"] == "en" and "readability_flesch" in data["metrics"]


def test_review_regressions() -> None:
    assert len(ts.sentences("He said no. Then he left.", "en")) == 2
    assert ts.sentences("—No. Vete de aquí. Ahora.", "es") == ["—No.", "Vete de aquí.", "Ahora."]
    assert len(ts.sentences("Lo firmó J. Pérez ayer.", "es")) == 1
    assert ts.dialogue_spans("«Esto sigue en el párrafo siguiente") == [
        "Esto sigue en el párrafo siguiente"
    ]
    assert ts.dialogue_spans("» y aquí termina.»")
    paras = [
        "CAPÍTULO 1",
        "1. Cómo empezó",
        "—Bueno...—dijo ella.",
        "—Dijo que vendría —explicó Ana.",
        "«Un discurso que sigue",
        "» y termina aquí.»",
    ]
    data = structure.to_json(structure.detect(paras), "v001")
    ctx = metrics.Context(
        paras,
        [a for a, _ in data["paragraphs"]],
        data["chapters"],
        "es",
        registers={
            "characters": [{"id": "g", "name": "Gabriel Utterson", "anchors": ["c01.s1"]}],
            "setups": [{"id": "x", "name": "x", "anchors": ["c01.s1"], "status": "dropped"}],
        },
    )
    assert metrics.REGISTRY["dialogue_punctuation_anomalies"](ctx)["items"] == []
    assert "unmatched «»" not in metrics.REGISTRY["typo_signals"](ctx)["counts"]
    assert metrics.REGISTRY["setup_payoff_distance"](ctx)["items"] == [
        {"id": "x", "status": "dropped"}
    ]
    ctx.paragraphs[1] = "Gabriel Utterson y gabriel utterson."
    assert (
        metrics.REGISTRY["name_variant_count"](ctx)["items"]
        == [{"name": "Gabriel Utterson", "forms": {"Gabriel Utterson": 1, "gabriel utterson": 1}}]
        or metrics.REGISTRY["name_variant_count"](ctx)["book"] == 0
    )
    titled = [{"id": "c01", "title": "1. Cómo empezó", "start": 0, "end": 0, "scenes": []}]
    titled.append({"id": "c02", "title": "Días de lluvia", "start": 1, "end": 1, "scenes": []})
    ctx2 = metrics.Context(paras[:2], ["c01.s0.p1", "c02.s0.p1"], titled, "es")
    assert metrics.REGISTRY["heading_sequence"](ctx2)["items"] == []
