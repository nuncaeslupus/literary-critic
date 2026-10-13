import hashlib
import json
import re
from pathlib import Path

import pytest

from litcritic import corpus, synth
from litcritic.cli import main

NOTE = """title = "T"
author = "A"
year = 1900
language = "en"
origin = "o"
origin_url = "https://example.org"
retrieved = "2026-01-01"
licence = "Public domain"
processing = "none"
sha256 = "{sha}"
"""


def _text(root: Path, slug: str, body: str = "One.\n\nTwo.\n", note: str | None = None) -> Path:
    d = root / slug
    d.mkdir(parents=True)
    (d / "text.txt").write_bytes(body.encode())
    sha = hashlib.sha256(body.encode()).hexdigest()
    if note is None:
        note = NOTE.format(sha=sha)
    (d / "source.toml").write_text(note, encoding="utf-8")
    return d


def test_corpus_has_source_notes() -> None:
    texts = corpus.load()
    assert {t.meta.get("language") for t in texts} >= {"es", "en"}
    for t in texts:
        assert t.errors == [], t.slug
    assert corpus.documented_ratio(texts) == 1.0


def test_known_chapter_counts_match_headings() -> None:
    patterns = {"marianela": r"^-[IVXL]+-$", "jekyll-hyde": r"^[A-Z][A-Z .']{6,}$"}
    for slug, pat in patterns.items():
        t = corpus.get(slug)
        structure = t.meta["structure"]
        assert isinstance(structure, dict)
        headings = re.findall(pat, t.read(), flags=re.M)
        # Jekyll: the title line and one signature line are also upper case.
        extra = 2 if slug == "jekyll-hyde" else 0
        assert len(headings) - extra == structure["chapters"], slug


def test_missing_field_and_bad_checksum_fail(tmp_path: Path) -> None:
    _text(tmp_path, "ok")
    _text(tmp_path, "nofield", note=NOTE.format(sha="x").replace('licence = "Public domain"\n', ""))
    texts = {t.slug: t for t in corpus.load(tmp_path)}
    assert texts["ok"].documented
    assert "source.toml: missing licence" in texts["nofield"].errors
    assert "text.txt does not match source.toml sha256" in texts["nofield"].errors
    assert corpus.documented_ratio(list(texts.values())) == 0.5


def test_missing_note_fails(tmp_path: Path) -> None:
    (tmp_path / "bare").mkdir()
    (tmp_path / "bare" / "text.txt").write_text("x\n", encoding="utf-8")
    (t,) = corpus.load(tmp_path)
    assert t.errors == ["missing source.toml"]
    assert main(["corpus", "check", "--root", str(tmp_path)]) == 1


def _consistent(draft: synth.Draft, source: list[str]) -> None:
    for i, entry in enumerate(draft.old):
        for j in entry["new"]:  # type: ignore[attr-defined]
            assert i in draft.new[j]["old"]
        if entry["kind"] in ("unchanged", "moved"):
            (j,) = entry["new"]  # type: ignore[misc]
            assert draft.paragraphs[j] == source[i]
    for j, entry in enumerate(draft.new):
        assert (entry["kind"] == "inserted") == (entry["old"] == [])
        if entry["kind"] == "merged":
            olds = entry["old"]
            assert isinstance(olds, list)
            assert draft.paragraphs[j] == " ".join(source[i] for i in olds)


@pytest.mark.parametrize("slug", ["marianela", "jekyll-hyde"])
def test_synth_truth_is_consistent(slug: str) -> None:
    source = synth.paragraphs(corpus.get(slug).read())
    draft = synth.generate(corpus.get(slug).read(), seed=7)
    _consistent(draft, source)
    kinds = {op["kind"] for op in draft.ops}
    assert kinds == set(synth.KINDS)
    changed = sum(e["kind"] != "unchanged" for e in draft.old)
    assert 0 < changed <= 0.15 * len(source)


def test_split_parts_rejoin_to_original() -> None:
    text = "\n\n".join(
        f"First sentence {i} here now. Second sentence {i} follows it." for i in range(30)
    )
    draft = synth.generate(text, seed=1)
    source = synth.paragraphs(text)
    for i, entry in enumerate(draft.old):
        if entry["kind"] == "split":
            parts = [draft.paragraphs[j] for j in entry["new"]]  # type: ignore[attr-defined]
            assert len(parts) == 2 and " ".join(parts) == source[i]


def test_synth_is_deterministic_and_cli_writes_truth(tmp_path: Path) -> None:
    text = corpus.get("jekyll-hyde").read()
    assert synth.generate(text, 3).paragraphs == synth.generate(text, 3).paragraphs
    assert synth.generate(text, 3).paragraphs != synth.generate(text, 4).paragraphs
    assert main(["synth", "jekyll-hyde", "--seed", "3", "--out", str(tmp_path)]) == 0
    truth = json.loads((tmp_path / "truth.json").read_text(encoding="utf-8"))
    draft = (tmp_path / "draft.txt").read_text(encoding="utf-8")
    assert len(synth.paragraphs(draft)) == truth["new_count"] == len(truth["new"])


def test_synth_handles_tiny_text() -> None:
    source = ["Only one short paragraph."]
    draft = synth.generate(source[0], seed=0)
    _consistent(draft, source)
    assert all(op["kind"] != "move" for op in draft.ops)
