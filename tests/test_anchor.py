import json
import random
import re
from pathlib import Path
from typing import Any

import docgen
import pytest

from litcritic import corpus, ingest, structure
from litcritic.cli import main

Variant = tuple[list[str], list[dict[str, Any]], set[int], set[int]]


def _paras(slug: str) -> list[str]:
    return [p.text for p in ingest.read_txt(corpus.get(slug).path.read_bytes()).paragraphs]


def _truth_chapters(slug: str, paras: list[str]) -> set[int]:
    if slug == "marianela":
        return {i for i, t in enumerate(paras) if re.fullmatch(r"-[IVXL]+-", t)}
    caps = [i for i, t in enumerate(paras) if re.fullmatch(r"[A-Z][A-Z .']{6,}", t)]
    return set(caps[1:]) - {i for i in caps if paras[i] == "HASTIE LANYON"}


def _with_breaks(
    paras: list[str], chapters: set[int], seed: int
) -> tuple[list[str], set[int], set[int]]:
    """Insert '* * *' lines inside chapter bodies; return text, chapter starts, scene starts."""
    rng = random.Random(seed)
    out: list[str] = []
    ch: set[int] = set()
    scenes: set[int] = set()
    since = 99
    for i, t in enumerate(paras):
        if i in chapters:
            ch.add(len(out))
            since = 0
        elif since > 4 and len(t.split()) > 20 and rng.random() < 0.04:
            out.append("* * *")
            scenes.add(len(out))
            since = 0
        out.append(t)
        since += 1
    return out, ch, scenes


def variants() -> dict[str, Variant]:
    v: dict[str, Variant] = {}
    for slug in ("marianela", "jekyll-hyde"):
        paras = _paras(slug)
        truth = _truth_chapters(slug, paras)
        v[f"{slug}-txt"] = (paras, [{} for _ in paras], truth, set())
        text, ch, sc = _with_breaks(paras, truth, seed=3)
        v[f"{slug}-breaks"] = (text, [{} for _ in text], ch, sc)
        md = "\n\n".join(f"## {t}" if i in ch else t for i, t in enumerate(text))
        d = ingest.read_md(md.encode())
        v[f"{slug}-md"] = ([p.text for p in d.paragraphs], [p.meta() for p in d.paragraphs], ch, sc)
        docx = ingest.read_docx(docgen.docx([(t, i in ch) for i, t in enumerate(text)], seed=4))
        v[f"{slug}-docx"] = (
            [p.text for p in docx.paragraphs],
            [p.meta() for p in docx.paragraphs],
            ch,
            sc,
        )
    # Style-only chapters, as many writers do: no title line, the first paragraph of
    # each chapter has a "Chapter start" style and an explicit page break.
    paras = _paras("marianela")
    truth = _truth_chapters("marianela", paras)
    body = [(t, i - 1 in truth or i - 2 in truth) for i, t in enumerate(paras) if i not in truth]
    text = [t for t, _ in body]
    meta = [{"style": "Chapter start", "page_break_before": True} if s else {} for _, s in body]
    starts = {k for k, (_, s) in enumerate(body) if s}
    starts = {k for k in starts if k - 1 not in starts}  # title line merged into the start
    meta = [m if k in starts else {} for k, m in enumerate(meta)]
    v["marianela-style-only"] = (text, meta, starts, set())
    return v


def _f1(expected: set[tuple[str, int]], got: set[tuple[str, int]]) -> float:
    tp = len(expected & got)
    if not tp:
        return 0.0
    p, r = tp / len(got), tp / len(expected)
    return 2 * p * r / (p + r)


def _detected(text: list[str], meta: list[dict[str, Any]]) -> tuple[set[int], set[int]]:
    s = structure.detect(text, meta)
    chapters = {c.start for c in s.chapters if c.reason != "front"}
    first_body = {c.heading[-1] + 1 if c.heading else c.start for c in s.chapters}
    return chapters, s.scene_starts - first_body


def scene_boundary_f1() -> tuple[float, dict[str, float]]:
    per: dict[str, float] = {}
    tot_exp: set[tuple[str, str, int]] = set()
    tot_got: set[tuple[str, str, int]] = set()
    for name, (text, meta, ch, sc) in variants().items():
        got_ch, got_sc = _detected(text, meta)
        exp = {("c", i) for i in ch} | {("s", i) for i in sc}
        got = {("c", i) for i in got_ch} | {("s", i) for i in got_sc}
        per[name] = round(_f1(exp, got), 4)
        tot_exp |= {(name, k, i) for k, i in exp}
        tot_got |= {(name, k, i) for k, i in got}
    tp = len(tot_exp & tot_got)
    p, r = tp / len(tot_got), tp / len(tot_exp)
    return 2 * p * r / (p + r), per


def test_structure_detects_chapters_and_breaks() -> None:
    f1, per = scene_boundary_f1()
    assert f1 >= 0.95, per
    assert min(per.values()) >= 0.9, per


def test_known_corpus_structure() -> None:
    for slug, n in (("marianela", 22), ("jekyll-hyde", 10)):
        s = structure.detect(_paras(slug))
        assert len([c for c in s.chapters if c.reason != "front"]) == n
        assert s.chapters[0].reason == "front"
    s = structure.detect(_paras("marianela"))
    assert s.chapters[1].title == "-I- Perdido"


def test_anchors_unique_and_readable() -> None:
    text, meta, _, _ = variants()["marianela-breaks"]
    s = structure.detect(text, meta)
    anchors = s.anchors()
    assert len(set(anchors)) == len(anchors) == len(text)
    assert all(re.fullmatch(r"c\d\d\.s\d+\.p\d+", a) for a in anchors)
    first = next(c for c in s.chapters if c.reason != "front")
    assert anchors[first.start] == "c01.s0.p1" and anchors[first.heading[-1] + 1] == "c01.s1.p1"
    assert anchors[text.index("* * *")].startswith("c")


def test_parts_prefix_anchors() -> None:
    text = ["Parte primera", *["Uno " * 60] * 2, "Capítulo 1", *["Dos " * 60] * 3]
    text += ["Parte segunda", "Capítulo 2", *["Tres " * 60] * 3, "Capítulo 3", "Cuatro " * 200]
    s = structure.detect(text)
    assert [p.title for p in s.parts] == ["Parte primera", "Parte segunda"]
    anchors = s.anchors()
    assert anchors[0].startswith("p1.") and anchors[text.index("Capítulo 2")] == "p2.c02.s0.p2"


def test_thin_caps_lines_are_not_chapters() -> None:
    body = "word " * 300
    text = ["A TITLE", "by Someone", "ONE", body, "SIGNED NAME", "TWO", body, "THREE", body]
    s = structure.detect(text)
    assert [c.start for c in s.chapters] == [0, 2, 5, 7]


def test_overrides_validated_then_applied(tmp_path: Path) -> None:
    text = ["CHAPTER ONE", "x " * 200, "y " * 200, "CHAPTER TWO", "z " * 200, "*", "*"]
    s = structure.detect(text)
    fp = structure.fingerprint
    assert structure.apply_overrides(s, {"chapter_starts": [fp("nope")]}) == [
        f"chapter_starts: {fp('nope')} not found"
    ]
    assert "matches 2 paragraphs" in structure.apply_overrides(s, {"scene_starts": [fp("*")]})[0]
    assert structure.apply_overrides(s, {"bogus": []}) == ["unknown key 'bogus'"]
    assert (
        structure.apply_overrides(
            s, {"chapter_starts": [fp(text[2])], "not_chapter": [fp(text[3])]}
        )
        == []
    )
    assert [c.start for c in s.chapters] == [0, 2]


def test_fingerprint_ignores_case_accents_spacing() -> None:
    assert structure.fingerprint("Él  dijo") == structure.fingerprint("el dijo")
    assert len(structure.fingerprint("x")) == 12


def test_cli_anchor_writes_structure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "workspace.toml").write_text('slug = "ws"\n', encoding="utf-8")
    assert main(["anchor", "--workspace", str(ws)]) == 2
    assert main(["ingest", str(corpus.get("jekyll-hyde").path), "--workspace", str(ws)]) == 0
    assert main(["anchor", "--workspace", str(ws)]) == 0
    data = json.loads((ws / "index" / "v001" / "structure.json").read_text(encoding="utf-8"))
    assert len(data["chapters"]) == 11 and data["chapters"][1]["id"] == "c01"
    assert data["chapters"][1]["title"] == "STORY OF THE DOOR"
    assert sum(c["words"] for c in data["chapters"]) == len(
        corpus.get("jekyll-hyde").read().split()
    )
    (ws / "analysis").mkdir()
    (ws / "analysis" / "structure-overrides.json").write_text('{"not_chapter": ["000000000000"]}')
    assert main(["anchor", "--workspace", str(ws)]) == 1
    assert "override rejected" in capsys.readouterr().err
