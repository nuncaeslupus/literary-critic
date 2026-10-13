import functools
import random

import pytest

from litcritic import corpus, diff, spans, synth


def _text(paras: list[str], draft: str = "v001") -> spans.Text:
    return spans.Text(paras, [f"c01.s1.p{i + 1}" for i in range(len(paras))], draft)


def _random_spans(old: spans.Text, rng: random.Random, n: int) -> list[spans.Span]:
    """Words, sentences, whole paragraphs and multi-paragraph stretches."""
    out: list[spans.Span] = []
    paras = old.paragraphs
    if not any(len(p) >= 40 for p in paras):
        raise ValueError("no paragraph long enough to sample spans from")
    while len(out) < n:
        kind = rng.choice(("words", "sentence", "paragraph", "multi"))
        i = rng.randrange(len(paras))
        p = paras[i]
        if len(p) < 40:
            continue
        if kind == "words":
            a = rng.randrange(0, len(p) - 30)
            b = a + rng.randint(15, 30)
            out.append(spans.make(old, "v001", old.anchors[i], a, old.anchors[i], b))
        elif kind == "sentence":
            a = rng.randrange(0, len(p) // 2)
            b = min(len(p), a + rng.randint(60, 200))
            out.append(spans.make(old, "v001", old.anchors[i], a, old.anchors[i], b))
        elif kind == "paragraph":
            out.append(spans.make(old, "v001", old.anchors[i], 0, old.anchors[i], len(p)))
        else:
            k = min(len(paras) - 1, i + rng.randint(1, 4))
            out.append(spans.make(old, "v001", old.anchors[i], 0, old.anchors[k], len(paras[k])))
    return out


def _new_of(entry: dict[str, object]) -> list[int]:
    targets = entry["new"]
    assert isinstance(targets, list)
    return targets


def _measure(slug: str, seed: int, rate: float) -> tuple[int, int, int]:
    """(spans with a known new home, of those found there, misplaced spans)."""
    rng = random.Random(seed)
    source = corpus.get(slug).read()
    old = _text(synth.paragraphs(source))
    draft = synth.generate(source, seed, rate)
    new = _text(draft.paragraphs, "v002")
    al = diff.align(old.paragraphs, new.paragraphs)
    kept = al.mapping()
    known = found = misplaced = 0
    for span in _random_spans(old, rng, 400):
        i0, i1 = old.index[span.start.para], old.index[span.end.para]
        truth = sorted({j for i in range(i0, i1 + 1) for j in _new_of(draft.old[i])})
        homes = []
        if truth:
            lo = new.starts[truth[0]]
            hi = new.starts[truth[-1]] + len(new.paragraphs[truth[-1]])
            homes = [h for h in spans._occurrences(span, new.joined) if lo <= h[0] and h[1] <= hi]
        moved = spans.relocate(span, old, new, al, "v002", kept)
        if moved.state in ("ok", "moved"):
            g0 = new.gpos(moved.start.para, moved.start.off)
            g1 = new.gpos(moved.end.para, moved.end.off)
            if (g0, g1) not in homes:
                misplaced += 1
        if len(homes) == 1:
            known += 1
            if moved.state in ("ok", "moved"):
                g0 = new.gpos(moved.start.para, moved.start.off)
                found += (g0, new.gpos(moved.end.para, moved.end.off)) == homes[0]
    return known, found, misplaced


# The gate's measurement: both corpus texts, five seeds, edit rates 0.05-0.3.
RUNS = ((1, 0.05), (2, 0.1), (3, 0.2), (4, 0.1), (5, 0.3))


@functools.cache
def _totals(slug: str) -> tuple[int, int, int]:
    results = [_measure(slug, seed, rate) for seed, rate in RUNS]
    return (
        sum(r[0] for r in results),
        sum(r[1] for r in results),
        sum(r[2] for r in results),
    )


@pytest.mark.parametrize("slug", ["marianela", "jekyll-hyde"])
def test_spans_unchanged_text_relocated_after_edits(slug: str) -> None:
    known, found, _ = _totals(slug)
    assert known > 1000
    assert found / known >= 0.98, (found, known)


@pytest.mark.parametrize("slug", ["marianela", "jekyll-hyde"])
def test_spans_changed_text_never_silently_moved(slug: str) -> None:
    assert _totals(slug)[2] == 0


def test_spans_long_quote_keeps_hash_and_relocates() -> None:
    paras = ["a" * 10 + " intro.", "x " * 300, "end."]
    old = _text(paras)
    span = spans.make(old, "v001", old.anchors[0], 0, old.anchors[2], 4)
    assert span.head and span.sha1 and not span.exact
    new = _text(["Inserted first.", *paras])
    moved = spans.relocate(span, old, new, diff.align(old.paragraphs, new.paragraphs), "v002")
    assert moved.state == "moved" and moved.start.para == new.anchors[1]
    assert spans.Span.from_json(moved.as_json()) == moved


def test_spans_from_quote_needs_one_match() -> None:
    old = _text(["The cat sat.", "The dog sat.", "A cat ran."])
    assert spans.from_quote(old, "v001", "dog sat").start.para == old.anchors[1]
    with pytest.raises(spans.SpanError):
        spans.from_quote(old, "v001", "sat")
    span = spans.from_quote(old, "v001", "cat", within=old.anchors[2])
    assert span.start == spans.Pos(old.anchors[2], 2)


def test_spans_edited_text_is_flagged_changed() -> None:
    old = _text(["One two three four five six.", "Seven eight nine ten."])
    span = spans.from_quote(old, "v001", "three four")
    new = _text(["One two THREE four five six.", "Seven eight nine ten."])
    moved = spans.relocate(span, old, new, diff.align(old.paragraphs, new.paragraphs), "v002")
    assert moved.state == "changed" and moved.start.para == new.anchors[0]


def test_spans_lone_match_elsewhere_without_context_is_not_trusted() -> None:
    # The edited paragraph stays at home (modified in place); the quote turns up
    # only in an unrelated new paragraph, with other text around it.
    old = _text(
        ["Alpha beta gamma delta she said nothing at all. Epsilon.", "Filler text here.", "Other."]
    )
    span = spans.from_quote(old, "v001", "she said nothing at all.")
    new = _text(
        [
            "Alpha beta gamma delta she spoke at last. Epsilon.",
            "Filler text here.",
            "Zeta she said nothing at all.",
        ]
    )
    moved = spans.relocate(span, old, new, diff.align(old.paragraphs, new.paragraphs), "v002")
    assert moved.state == "changed" and moved.start.para == new.anchors[0]


def test_spans_lost_span_survives_the_next_sync() -> None:
    old = _text(["Keep this one.", "Doomed paragraph with words.", "Last one."])
    span = spans.from_quote(old, "v001", "Doomed paragraph")
    mid = _text(["Keep this one.", "Last one."], "v002")
    lost = spans.relocate(span, old, mid, diff.align(old.paragraphs, mid.paragraphs), "v002")
    assert lost.state == "lost" and lost.draft == "v001"
    new = _text(["Keep this one.", "Last one.", "Brand new."], "v003")
    again = spans.relocate(lost, mid, new, diff.align(mid.paragraphs, new.paragraphs), "v003")
    assert again.state == "lost"


def test_spans_restored_text_is_found_again() -> None:
    old = _text(["One two three four five six.", "Seven eight nine ten."])
    span = spans.from_quote(old, "v001", "three four")
    mid = _text(["One two THREE four five six.", "Seven eight nine ten."], "v002")
    changed = spans.relocate(span, old, mid, diff.align(old.paragraphs, mid.paragraphs), "v002")
    assert changed.state == "changed"
    restored = _text(old.paragraphs, "v003")
    back = spans.relocate(
        changed, mid, restored, diff.align(mid.paragraphs, old.paragraphs), "v003"
    )
    assert back.state in ("ok", "moved") and back.start == spans.Pos(old.anchors[0], 8)


def test_spans_within_matches_whole_units_and_part_prefixes() -> None:
    paras = ["A cat.", *[f"Filler {i}." for i in range(10)], "Another cat."]
    text = spans.Text(paras, [f"p1.c01.s1.p{i + 1}" for i in range(len(paras))])
    assert spans.from_quote(text, "v001", "cat", within="c01.s1.p1").start.para == "p1.c01.s1.p1"
    with pytest.raises(spans.SpanError):
        spans.from_quote(text, "v001", "Another", within="c01.s1.p1")


def test_spans_without_quote_are_rejected() -> None:
    with pytest.raises(spans.SpanError):
        spans.Span.from_json(
            {"draft": "v001", "start": {"para": "a", "off": 0}, "end": {"para": "a", "off": 1}}
        )
