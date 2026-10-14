"""Script-measured metrics for the registry in ``checklist/metrics.toml``.

Each metric is a function ``(ctx) -> dict`` registered with ``@metric(id)``. A
result may hold ``book`` (a number or small dict), ``chapters`` / ``scenes``
(id -> value), ``items`` (located findings, each with an ``anchor``) and
``note``. A metric whose inputs are missing (Codex items, LLM
labels) returns ``{"unmeasured": reason}`` instead of guessing.
"""

from __future__ import annotations

import json
import re
import statistics
import tomllib
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import cached_property
from itertools import pairwise
from pathlib import Path
from typing import Any

from litcritic import codex, query
from litcritic import textstats as ts

Result = dict[str, Any]
REGISTRY: dict[str, Callable[[Context], Result]] = {}
DATA = Path(__file__).parent / "data"


def metric(mid: str) -> Callable[[Callable[[Context], Result]], Callable[[Context], Result]]:
    def wrap(fn: Callable[[Context], Result]) -> Callable[[Context], Result]:
        REGISTRY[mid] = fn
        return fn

    return wrap


def lexicon(lang: str) -> dict[str, Any]:
    path = DATA / f"lexicon_{lang}.toml"
    if not path.is_file():
        path = DATA / "lexicon_en.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


@dataclass
class Context:
    paragraphs: list[str]
    anchors: list[str]
    chapters: list[dict[str, Any]]  # structure.json chapters (with scenes)
    lang: str = "en"
    parts: list[dict[str, Any]] = field(default_factory=list)
    meta: list[dict[str, Any]] = field(default_factory=list)
    registers: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    scene_cards: list[dict[str, Any]] = field(default_factory=list)
    labels: dict[str, Any] = field(default_factory=dict)

    @cached_property
    def lex(self) -> dict[str, Any]:
        return lexicon(self.lang)

    @cached_property
    def words(self) -> list[list[str]]:
        return [ts.words(p) for p in self.paragraphs]

    @cached_property
    def lower(self) -> list[list[str]]:
        return [[w.casefold() for w in ws] for ws in self.words]

    @cached_property
    def sentences(self) -> list[list[str]]:
        return [ts.sentences(p, self.lang) for p in self.paragraphs]

    @cached_property
    def speech(self) -> list[list[str]]:
        return [ts.dialogue_spans(p) for p in self.paragraphs]

    @cached_property
    def speech_words(self) -> list[int]:
        return [sum(len(ts.words(s)) for s in sp) for sp in self.speech]

    @cached_property
    def wc(self) -> list[int]:
        return [len(ws) for ws in self.words]

    @cached_property
    def stop(self) -> set[str]:
        return set(self.lex.get("stopwords", []))

    def units(self, level: str) -> list[tuple[str, range]]:
        if level == "chapters":
            return [(c["id"], range(c["start"], c["end"] + 1)) for c in self.chapters]
        return [
            (s["id"], range(s["start"], s["end"] + 1)) for c in self.chapters for s in c["scenes"]
        ]

    def per_unit(self, level: str, fn: Callable[[range], Any]) -> dict[str, Any]:
        return {uid: fn(r) for uid, r in self.units(level)}

    def words_in(self, r: Iterable[int]) -> int:
        return sum(self.wc[i] for i in r)

    @property
    def all(self) -> range:
        return range(len(self.paragraphs))


def _round(x: float, n: int = 3) -> float:
    return round(x, n)


def _per_1000(count: float, words: int) -> float:
    return _round(1000 * count / words, 2) if words else 0.0


def _cv(values: list[int]) -> float:
    values = [v for v in values if v]
    if len(values) < 2:
        return 0.0
    return _round(statistics.pstdev(values) / statistics.mean(values))


def _phrase_re(phrases: Iterable[str]) -> re.Pattern[str] | None:
    items = sorted({p.casefold() for p in phrases if p}, key=len, reverse=True)
    if not items:
        return None
    return re.compile(
        r"(?<![^\W\d_])(?:" + "|".join(map(re.escape, items)) + r")(?![^\W\d_])", re.I
    )


def _count_phrases(ctx: Context, phrases: Iterable[str], r: Iterable[int]) -> Counter[str]:
    pat = _phrase_re(phrases)
    out: Counter[str] = Counter()
    if pat is None:
        return out
    for i in r:
        out.update(m.group().casefold() for m in pat.finditer(ctx.paragraphs[i]))
    return out


def _density_metric(ctx: Context, phrases: list[str]) -> Result:
    total = _count_phrases(ctx, phrases, ctx.all)
    return {
        "book": _per_1000(sum(total.values()), ctx.words_in(ctx.all)),
        "chapters": ctx.per_unit(
            "chapters",
            lambda r: _per_1000(sum(_count_phrases(ctx, phrases, r).values()), ctx.words_in(r)),
        ),
        "counts": dict(total.most_common(30)),
    }


# --- structure and length -------------------------------------------------------------


@metric("words_per_chapter")
def words_per_chapter(ctx: Context) -> Result:
    per = ctx.per_unit("chapters", ctx.words_in)
    return {"book": _round(statistics.mean(per.values()), 1) if per else 0, "chapters": per}


@metric("words_per_scene")
def words_per_scene(ctx: Context) -> Result:
    per = ctx.per_unit("scenes", ctx.words_in)
    return {"book": _round(statistics.mean(per.values()), 1) if per else 0, "scenes": per}


@metric("scene_count_per_chapter")
def scene_count_per_chapter(ctx: Context) -> Result:
    per = {c["id"]: len(c["scenes"]) for c in ctx.chapters}
    return {"book": sum(per.values()), "chapters": per}


@metric("scene_length_cv")
def scene_length_cv(ctx: Context) -> Result:
    scene_words = ctx.per_unit("scenes", ctx.words_in)
    out: Result = {"book": _cv(list(scene_words.values()))}
    if ctx.parts:
        starts = [p["start"] for p in ctx.parts] + [len(ctx.paragraphs)]
        per_part = {}
        for k, p in enumerate(ctx.parts):
            vals = [
                ctx.words_in(r)
                for _, r in ctx.units("scenes")
                if starts[k] <= r.start < starts[k + 1]
            ]
            per_part[f"p{p['n']}"] = _cv(vals)
        out["parts"] = per_part
    return out


@metric("chapter_length_cv")
def chapter_length_cv(ctx: Context) -> Result:
    vals = [ctx.words_in(r) for cid, r in ctx.units("chapters") if not cid.endswith("c00")]
    return {"book": _cv(vals)}


@metric("paragraph_length_mean")
def paragraph_length_mean(ctx: Context) -> Result:
    vals = [w for w in ctx.wc if w]
    q = statistics.quantiles(vals, n=4) if len(vals) >= 2 else [0, 0, 0]
    return {
        "book": _round(statistics.mean(vals), 1) if vals else 0,
        "quartiles": [_round(x, 1) for x in q],
        "over_250_share": _round(sum(v > 250 for v in vals) / len(vals)) if vals else 0,
        "chapters": ctx.per_unit(
            "chapters",
            lambda r: _round(ctx.words_in(r) / max(1, sum(1 for i in r if ctx.wc[i])), 1),
        ),
    }


@metric("long_paragraph_rate")
def long_paragraph_rate(ctx: Context) -> Result:
    hits = [i for i in ctx.all if ctx.wc[i] > 250 and not ctx.speech[i]]
    total = sum(1 for w in ctx.wc if w)
    return {
        "book": _round(len(hits) / total) if total else 0,
        "items": [{"anchor": ctx.anchors[i], "words": ctx.wc[i]} for i in hits],
    }


@metric("scene_break_markers")
def scene_break_markers(ctx: Context) -> Result:
    heads = {
        i for c in ctx.chapters for i in range(c["start"], c["end"] + 1) if ".s0." in ctx.anchors[i]
    }
    markers = [
        i
        for i in ctx.all
        if ctx.paragraphs[i].strip()
        and not re.search(r"[^\W_]", ctx.paragraphs[i])
        and i not in heads
    ]
    styles = Counter(" ".join(ctx.paragraphs[i].split()) for i in markers)
    blank_breaks = [
        i for i, m in enumerate(ctx.meta) if int(m.get("blank_before", 0)) >= 2 and i not in heads
    ]
    if blank_breaks:
        styles["(blank lines)"] = len(blank_breaks)
    major = styles.most_common(1)[0][0] if styles else ""
    items = [
        {"anchor": ctx.anchors[i], "marker": " ".join(ctx.paragraphs[i].split())}
        for i in markers
        if " ".join(ctx.paragraphs[i].split()) != major
    ]
    if major != "(blank lines)":
        items += [{"anchor": ctx.anchors[i], "marker": "(blank lines)"} for i in blank_breaks]
    return {"book": dict(styles), "items": items}


@metric("heading_sequence")
def heading_sequence(ctx: Context) -> Result:
    def shape(title: str) -> str:
        """Heading format up to its number: '-IV- Title' -> '-N-', 'Capítulo 3: X' -> 'w N:'."""
        t = re.sub(r"(?<![^\W\d_])[IVXLCDM]+(?![^\W\d_])|\d+", "N", title)
        cut = t.find("N")
        if cut < 0:
            return "UPPER CASE" if title.isupper() else "text"
        return re.sub(r"[^\W\d_]{2,}", "w", t[: cut + 2]).strip()

    titled = [c for c in ctx.chapters if c.get("title") and not c["id"].endswith("c00")]
    nums = [(c["id"], query.heading_number(c["title"])) for c in titled]
    items = []
    seen: dict[int, str] = {}
    expected = None
    for cid, n in nums:
        if n is None:
            continue
        if n in seen:
            items.append({"anchor": f"{cid}.s0.p1", "problem": f"number {n} repeats {seen[n]}"})
        elif expected is not None and n != expected:
            items.append({"anchor": f"{cid}.s0.p1", "problem": f"expected {expected}, found {n}"})
        seen.setdefault(n, cid)
        expected = n + 1
    shapes = Counter(shape(c["title"]) for c in titled)
    return {
        "book": {"numbered": sum(n is not None for _, n in nums), "formats": dict(shapes)},
        "items": items,
    }


# --- sentences, readability -----------------------------------------------------------


def _sentence_lengths(ctx: Context, r: Iterable[int]) -> list[int]:
    return [len(ts.words(s)) for i in r for s in ctx.sentences[i]]


@metric("sentence_length_mean")
def sentence_length_mean(ctx: Context) -> Result:
    def mean(r: Iterable[int]) -> float:
        v = _sentence_lengths(ctx, r)
        return _round(statistics.mean(v), 2) if v else 0.0

    return {"book": mean(ctx.all), "chapters": ctx.per_unit("chapters", mean)}


@metric("sentence_length_sd")
def sentence_length_sd(ctx: Context) -> Result:
    def sd(r: Iterable[int]) -> float:
        v = _sentence_lengths(ctx, r)
        return _round(statistics.pstdev(v), 2) if len(v) > 1 else 0.0

    return {"book": sd(ctx.all), "chapters": ctx.per_unit("chapters", sd)}


@metric("long_sentence_rate")
def long_sentence_rate(ctx: Context) -> Result:
    limit = int(ctx.lex.get("long_sentence_words", 40))

    def rate(r: Iterable[int]) -> float:
        v = _sentence_lengths(ctx, r)
        return _round(sum(x > limit for x in v) / len(v)) if v else 0.0

    items = [
        {"anchor": ctx.anchors[i], "words": len(ts.words(s))}
        for i in ctx.all
        for s in ctx.sentences[i]
        if len(ts.words(s)) > limit
    ]
    return {
        "book": rate(ctx.all),
        "threshold": limit,
        "chapters": ctx.per_unit("chapters", rate),
        "items": items,
    }


def readability_counts(text_paragraphs: list[str], lang: str) -> tuple[int, int, int]:
    """(words, sentences, syllables) for the given paragraphs."""
    w = s = syl = 0
    for p in text_paragraphs:
        ws = ts.words(p)
        w += len(ws)
        s += len(ts.sentences(p, lang))
        syl += sum(ts.syllables(x, lang) for x in ws)
    return w, s, syl


def fernandez_huerta(words: int, sentences: int, syllables: int) -> float:
    """Fernández-Huerta with the usual transcription error corrected (Law, 2011).

    The widely quoted form subtracts 1.02 x sentences per 100 words, which makes
    longer sentences read as easier; the corrected form subtracts 1.02 x words
    per sentence, consistent with Flesch.
    """
    p = 100 * syllables / words
    return _round(206.84 - 0.60 * p - 1.02 * words / sentences, 2)


def szigriszt(words: int, sentences: int, syllables: int) -> float:
    return _round(206.835 - 62.3 * syllables / words - words / sentences, 2)


def inflesz_band(score: float) -> str:
    for limit, band in (
        (40, "muy difícil"),
        (55, "algo difícil"),
        (65, "normal"),
        (80, "bastante fácil"),
    ):
        if score < limit:
            return band
    return "muy fácil"


def flesch(words: int, sentences: int, syllables: int) -> float:
    return _round(206.835 - 1.015 * words / sentences - 84.6 * syllables / words, 2)


def _readability(ctx: Context, fn: Callable[[int, int, int], float], lang: str) -> Result:
    if ctx.lang != lang:
        return {"unmeasured": f"defined for language {lang!r} only"}

    def score(r: Iterable[int]) -> float | None:
        w, s, syl = readability_counts([ctx.paragraphs[i] for i in r], lang)
        return fn(w, s, syl) if w and s else None

    return {"book": score(ctx.all), "chapters": ctx.per_unit("chapters", score)}


@metric("readability_fernandez_huerta")
def readability_fernandez_huerta(ctx: Context) -> Result:
    return _readability(ctx, fernandez_huerta, "es")


@metric("readability_szigriszt_inflesz")
def readability_szigriszt_inflesz(ctx: Context) -> Result:
    out = _readability(ctx, szigriszt, "es")
    if "book" in out and out["book"] is not None:
        out["band"] = inflesz_band(out["book"])
    return out


@metric("readability_flesch")
def readability_flesch(ctx: Context) -> Result:
    return _readability(ctx, flesch, "en")


def mtld_score(tokens: list[str], threshold: float = 0.72) -> float:
    """McCarthy & Jarvis MTLD, mean of forward and backward passes."""

    def one_pass(seq: list[str]) -> float:
        factors, types, count = 0.0, set(), 0
        for tok in seq:
            count += 1
            types.add(tok)
            if len(types) / count <= threshold:
                factors += 1
                types, count = set(), 0
        if count:
            ttr = len(types) / count
            factors += (1 - ttr) / (1 - threshold) if ttr < 1 else 0
        return len(seq) / factors if factors else float(len(seq))

    if not tokens:
        return 0.0
    return _round((one_pass(tokens) + one_pass(tokens[::-1])) / 2, 2)


@metric("mtld")
def mtld(ctx: Context) -> Result:
    def score(r: Iterable[int]) -> float:
        return mtld_score([w for i in r for w in ctx.lower[i]])

    return {
        "book": score(ctx.all),
        "chapters": ctx.per_unit("chapters", score),
        "note": "word forms (no lemmatiser)",
    }


# --- word choice ----------------------------------------------------------------------


def _is_adverb(word: str, lex: dict[str, Any]) -> bool:
    suffix = str(lex.get("adverb_suffix", "ly"))
    exclude = lex.setdefault("_adverb_exclude_set", frozenset(lex.get("adverb_exclude", [])))
    return word.endswith(suffix) and len(word) > len(suffix) + 2 and word not in exclude


@metric("adverb_density")
def adverb_density(ctx: Context) -> Result:
    tags = set(ctx.lex.get("tag_verbs", []))

    def count(r: Iterable[int]) -> int:
        return sum(_is_adverb(w, ctx.lex) for i in r for w in ctx.lower[i])

    items = []
    for i in ctx.all:
        ws = ctx.lower[i]
        for k, w in enumerate(ws):
            if w in tags and any(_is_adverb(x, ctx.lex) for x in ws[k + 1 : k + 4]):
                items.append({"anchor": ctx.anchors[i], "tag": " ".join(ctx.words[i][k : k + 4])})
    return {
        "book": _per_1000(count(ctx.all), ctx.words_in(ctx.all)),
        "chapters": ctx.per_unit("chapters", lambda r: _per_1000(count(r), ctx.words_in(r))),
        "items": items,
    }


@metric("filter_word_density")
def filter_word_density(ctx: Context) -> Result:
    return _density_metric(ctx, ctx.lex.get("filter_words", []))


@metric("crutch_word_frequency")
def crutch_word_frequency(ctx: Context) -> Result:
    out = _density_metric(ctx, ctx.lex.get("crutch_words", []))
    content = Counter(w for ws in ctx.lower for w in ws if w not in ctx.stop and len(w) > 3)
    out["top_words"] = dict(content.most_common(20))
    return out


@metric("comparison_marker_density")
def comparison_marker_density(ctx: Context) -> Result:
    phrases = ctx.lex.get("comparison_markers", [])
    out = _density_metric(ctx, phrases)
    pat = _phrase_re(phrases)
    items = []
    for i in ctx.all:
        for s in ctx.sentences[i]:
            hits = pat.findall(s) if pat else []
            if len(hits) >= 2:
                items.append({"anchor": ctx.anchors[i], "markers": [h.casefold() for h in hits]})
    out["items"] = items
    return out


@metric("cliche_list_hits")
def cliche_list_hits(ctx: Context) -> Result:
    phrases = ctx.lex.get("cliches", [])
    out = _density_metric(ctx, phrases)
    pat = _phrase_re(phrases)
    out["items"] = [
        {"anchor": ctx.anchors[i], "phrase": m.group()}
        for i in ctx.all
        for m in (pat.finditer(ctx.paragraphs[i]) if pat else [])
    ]
    return out


@metric("sensory_word_density")
def sensory_word_density(ctx: Context) -> Result:
    senses: dict[str, list[str]] = ctx.lex.get("sensory", {})
    book = {
        k: _per_1000(sum(_count_phrases(ctx, v, ctx.all).values()), ctx.words_in(ctx.all))
        for k, v in senses.items()
    }
    scenes = ctx.per_unit(
        "scenes",
        lambda r: {k: sum(_count_phrases(ctx, v, r).values()) for k, v in senses.items()},
    )
    return {"book": book, "scenes": scenes}


@metric("repeated_ngram_rate")
def repeated_ngram_rate(ctx: Context) -> Result:
    tokens: list[tuple[str, int]] = [(w, i) for i in ctx.all for w in ctx.lower[i]]
    total = 0
    repeated = 0
    top: list[tuple[int, str, list[int]]] = []
    for n in range(3, 7):
        where: dict[tuple[str, ...], list[int]] = defaultdict(list)
        for k in range(len(tokens) - n + 1):
            gram = tuple(t for t, _ in tokens[k : k + n])
            if all(g in ctx.stop for g in gram):
                continue
            where[gram].append(tokens[k][1])
        total += sum(len(v) for v in where.values())
        repeated += sum(len(v) for v in where.values() if len(v) > 1)
        if n >= 4:
            top += [(len(v), " ".join(g), v) for g, v in where.items() if len(v) > 1]
    top.sort(key=lambda t: (-t[0], t[1]))
    items = [
        {
            "anchor": ctx.anchors[locs[0]],
            "ngram": g,
            "count": c,
            "anchors": [ctx.anchors[x] for x in locs[:5]],
        }
        for c, g, locs in top[:40]
    ]
    return {"book": _round(repeated / total) if total else 0, "items": items}


@metric("word_echo_count")
def word_echo_count(ctx: Context, window: int = 50) -> Result:
    items = []
    tokens = [(w, i) for i in ctx.all for w in ctx.lower[i]]
    last: dict[str, int] = {}
    for k, (w, i) in enumerate(tokens):
        if w in ctx.stop or len(w) < 4:
            continue
        if w in last and k - last[w] <= window:
            items.append({"anchor": ctx.anchors[i], "word": w, "gap": k - last[w]})
        last[w] = k
    per = Counter(str(it["anchor"]).split(".s")[0] for it in items)
    return {"book": len(items), "chapters": dict(per), "items": items[:500]}


@metric("suffix_echo_count")
def suffix_echo_count(ctx: Context, window: int = 12) -> Result:
    items = []
    for i in ctx.all:
        ws = [w for w in ctx.lower[i] if len(w) >= 5 and w not in ctx.stop]
        for k in range(len(ws)):
            group = {w for w in ws[k : k + window] if w[-3:] == ws[k][-3:]}
            if len(group) >= 3:
                items.append(
                    {"anchor": ctx.anchors[i], "suffix": ws[k][-3:], "words": sorted(group)}
                )
                break
    return {"book": len(items), "items": items}


@metric("exclamation_ellipsis_density")
def exclamation_ellipsis_density(ctx: Context) -> Result:
    marks = {"exclamation": r"!", "question": r"\?", "ellipsis": r"…|\.\.\."}

    def density(r: Iterable[int]) -> dict[str, float]:
        w = ctx.words_in(r)
        return {
            k: _per_1000(sum(len(re.findall(p, ctx.paragraphs[i])) for i in r), w)
            for k, p in marks.items()
        }

    return {"book": density(ctx.all), "chapters": ctx.per_unit("chapters", density)}


@metric("sentence_opener_repetition")
def sentence_opener_repetition(ctx: Context) -> Result:
    same = total = 0
    items = []
    for i in ctx.all:
        firsts = [ts.words(s)[0].casefold() for s in ctx.sentences[i] if ts.words(s)]
        run = 1
        for k in range(1, len(firsts)):
            total += 1
            if firsts[k] == firsts[k - 1]:
                same += 1
                run += 1
                if run == 3:
                    items.append({"anchor": ctx.anchors[i], "opener": firsts[k]})
            else:
                run = 1
    return {"book": _round(same / total) if total else 0, "items": items}


@metric("spelling_variety_mix")
def spelling_variety_mix(ctx: Context) -> Result:
    counts: dict[str, dict[str, int]] = {}
    items = []
    for pair in ctx.lex.get("spelling_pairs", []):
        c = _count_phrases(ctx, pair, ctx.all)
        found = {p: c.get(p.casefold(), 0) for p in pair}
        if sum(1 for v in found.values() if v) < 2:
            continue
        counts[" / ".join(pair)] = found
        minority = min(found, key=lambda k: found[k])
        pat = _phrase_re([minority])
        items += [
            {"anchor": ctx.anchors[i], "form": minority}
            for i in ctx.all
            if pat and pat.search(ctx.paragraphs[i])
        ]
    return {"book": counts, "items": items}


# --- dialogue -------------------------------------------------------------------------


@metric("dialogue_ratio")
def dialogue_ratio(ctx: Context) -> Result:
    def ratio(r: Iterable[int]) -> float:
        w = ctx.words_in(r)
        return _round(sum(ctx.speech_words[i] for i in r) / w) if w else 0.0

    return {
        "book": ratio(ctx.all),
        "chapters": ctx.per_unit("chapters", ratio),
        "scenes": ctx.per_unit("scenes", ratio),
    }


def _narration(ctx: Context, i: int) -> list[str]:
    """Words of a dialogue paragraph outside its speech spans (tags and action)."""
    text = ctx.paragraphs[i]
    for s in ctx.speech[i]:
        text = text.replace(s, " ", 1)
    return [w.casefold() for w in ts.words(text)]


@metric("dialogue_tag_distribution")
def dialogue_tag_distribution(ctx: Context) -> Result:
    tags = set(ctx.lex.get("tag_verbs", []))
    said = set(ctx.lex.get("said_verbs", []))
    found: Counter[str] = Counter()
    with_adverb = 0
    for i in ctx.all:
        if not ctx.speech[i]:
            continue
        nar = _narration(ctx, i)
        for k, w in enumerate(nar):
            if w in tags:
                found[w] += 1
                if any(_is_adverb(x, ctx.lex) for x in nar[k + 1 : k + 3]):
                    with_adverb += 1
    total = sum(found.values())
    return {
        "book": {
            "tags": total,
            "said_share": _round(sum(v for k, v in found.items() if k in said) / total)
            if total
            else 0,
            "adverb_share": _round(with_adverb / total) if total else 0,
        },
        "counts": dict(found.most_common()),
    }


@metric("long_speech_count")
def long_speech_count(ctx: Context) -> Result:
    hits = [i for i in ctx.all if ctx.speech_words[i] > 150]
    per = Counter(ctx.anchors[i].split(".s")[0] for i in hits)
    return {
        "book": len(hits),
        "chapters": dict(per),
        "items": [{"anchor": ctx.anchors[i], "words": ctx.speech_words[i]} for i in hits],
    }


@metric("dialogue_run_length")
def dialogue_run_length(ctx: Context, threshold: int = 8) -> Result:
    scenes: dict[str, int] = {}
    items = []
    for sid, r in ctx.units("scenes"):
        run = longest = 0
        start = r.start
        for i in r:
            pure = bool(ctx.speech[i]) and not _narration(ctx, i)
            if pure:
                if run == 0:
                    start = i
                run += 1
                longest = max(longest, run)
                if run == threshold + 1:
                    items.append({"anchor": ctx.anchors[start], "scene": sid})
            else:
                run = 0
        scenes[sid] = longest
    return {
        "book": max(scenes.values(), default=0),
        "threshold": threshold,
        "scenes": scenes,
        "items": items,
    }


@metric("quote_style_consistency")
def quote_style_consistency(ctx: Context) -> Result:
    patterns = {
        "dialogue em dash": r"^\s*—",
        "dialogue en dash": r"^\s*–",
        "dialogue hyphen": r"^\s*-\s?\S",
        "guillemets «»": r"«",
        "curly double “”": r"“",
        'straight double "': r'"',
        "curly single ‘’": r"‘",
        "straight apostrophe '": r"[^\W\d_]'[^\W\d_]",
        "curly apostrophe ’": r"[^\W\d_]’[^\W\d_]",
        "ellipsis character …": r"…",
        "three dots ...": r"\.\.\.",
        "spaced dash —": r"\s—\s",
    }
    counts = {k: sum(len(re.findall(p, t)) for t in ctx.paragraphs) for k, p in patterns.items()}
    return {"book": {k: v for k, v in counts.items() if v}}


@metric("dialogue_punctuation_anomalies")
def dialogue_punctuation_anomalies(ctx: Context) -> Result:
    items = []
    led = Counter(
        "hyphen" if re.match(r"^\s*-", t) else "dash"
        for t in ctx.paragraphs
        if re.match(r"^\s*[-—–]", t)
    )
    hyphen_is_convention = led["hyphen"] > led["dash"]
    for i in ctx.all:
        t = ctx.paragraphs[i]
        problems = []
        if ctx.lang == "es":
            if re.match(r"^\s*—\s", t):
                problems.append("space after opening dash")
            if re.match(r"^\s*-[^-\s]", t) and not hyphen_is_convention:
                problems.append("hyphen instead of dash")
            if re.search(r"(?<![.…])\.—", t):
                problems.append("full stop before closing dash")
            if re.search(
                r"\s—(?:Dijo|Preguntó|Respondió|Contestó|Exclamó|Murmuró|Susurró|Gritó)\b", t
            ):
                problems.append("capital letter in dialogue tag")
        elif not ts.continues_speech(t):
            if t.count('"') % 2 or t.count("“") != t.count("”"):
                problems.append("unbalanced quotes")
            if re.search(r'["”],', t):
                problems.append("comma outside closing quote")
        if problems:
            items.append({"anchor": ctx.anchors[i], "problems": problems})
    return {"book": len(items), "items": items}


# --- characters, names and terms ------------------------------------------------------


def _names_from_register(ctx: Context) -> dict[str, list[str]]:
    return {
        e["name"]: [e["name"], *e.get("aliases", [])] for e in ctx.registers.get("characters", [])
    }


def _proper_nouns(ctx: Context, min_count: int = 3) -> dict[str, int]:
    """Capitalised words not at sentence start and never seen in lower case."""
    caps: Counter[str] = Counter()
    abbreviations = ts.ABBREVIATIONS["en"] | ts.ABBREVIATIONS.get(ctx.lang, set())
    plain = {w.casefold() for ws in ctx.words for w in ws if w[:1].islower()}
    for i in ctx.all:
        for s in ctx.sentences[i]:
            ws = ts.words(s)
            for w in ws[1:]:
                if (
                    w[:1].isupper()
                    and not w.isupper()
                    and w.casefold() not in ctx.stop
                    and w.casefold() not in abbreviations
                ):
                    caps[w] += 1
    return {w: c for w, c in caps.items() if c >= min_count and w.casefold() not in plain}


def _mentions(ctx: Context, terms: list[str], r: Iterable[int]) -> int:
    pat = re.compile(r"(?<![^\W\d_])(?:" + "|".join(map(re.escape, terms)) + r")(?![^\W\d_])")
    return sum(len(pat.findall(ctx.paragraphs[i])) for i in r)


@metric("character_presence_matrix")
def character_presence_matrix(ctx: Context) -> Result:
    names = _names_from_register(ctx)
    if not names:
        return {"unmeasured": "needs character entities in the Codex"}
    matrix = {}
    for n, terms in names.items():

        def count(r: range, t: list[str] = terms) -> int:
            return _mentions(ctx, t, r)

        matrix[n] = ctx.per_unit("chapters", count)
    summary = {}
    for n, row in matrix.items():
        present = [c for c, v in row.items() if v]
        summary[n] = {
            "first": present[0] if present else None,
            "last": present[-1] if present else None,
        }
    return {"book": summary, "matrix": matrix}


@metric("character_first_appearance")
def character_first_appearance(ctx: Context) -> Result:
    names = _names_from_register(ctx) or {n: [n] for n in _proper_nouns(ctx)}
    total = ctx.words_in(ctx.all)
    first = {}
    for n, terms in names.items():
        pat = re.compile(r"(?<![^\W\d_])(?:" + "|".join(map(re.escape, terms)) + r")(?![^\W\d_])")
        before = 0
        for i in ctx.all:
            if pat.search(ctx.paragraphs[i]):
                first[n] = {
                    "anchor": ctx.anchors[i],
                    "percent": _round(100 * before / total, 1) if total else 0,
                }
                break
            before += ctx.wc[i]
    per = Counter(str(v["anchor"]).split(".s")[0] for v in first.values())
    source = "register" if _names_from_register(ctx) else "capitalised-word heuristic"
    return {"book": first, "chapters": dict(per), "note": f"names from {source}"}


@metric("new_term_density")
def new_term_density(ctx: Context) -> Result:
    seen: set[str] = set()
    proper = set(_proper_nouns(ctx, min_count=1))
    per: dict[str, float] = {}
    for cid, r in ctx.units("chapters"):
        new = {w for i in r for w in ctx.words[i] if w in proper and w not in seen}
        seen |= new
        per[cid] = _per_1000(len(new), ctx.words_in(r))
    return {"book": _per_1000(len(seen), ctx.words_in(ctx.all)), "chapters": per}


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


@metric("name_similarity_pairs")
def name_similarity_pairs(ctx: Context) -> Result:
    names = list(_names_from_register(ctx)) or sorted(_proper_nouns(ctx))
    items = []
    for k, a in enumerate(names):
        for b in names[k + 1 :]:
            fa, fb = ts.strip_accents(a).casefold(), ts.strip_accents(b).casefold()
            if fa == fb:
                continue
            close = _edit_distance(fa, fb) <= 2 or (fa[:3] == fb[:3] and len(fa) > 3)
            if close and fa[0] == fb[0]:
                both = sum(
                    1
                    for _, r in ctx.units("chapters")
                    if _mentions(ctx, [a], r) and _mentions(ctx, [b], r)
                )
                items.append({"names": [a, b], "chapters_together": both})
    return {"book": len(items), "items": items}


def _fold_keep_length(text: str) -> str:
    """Case- and accent-folded, one character per input character (keeps offsets)."""
    return "".join((ts.strip_accents(c).casefold() or c)[:1] for c in text)


@metric("name_variant_count")
def name_variant_count(ctx: Context) -> Result:
    names = _names_from_register(ctx) or {n: [n] for n in _proper_nouns(ctx)}
    forms: dict[str, Counter[str]] = defaultdict(Counter)
    folded = {_fold_keep_length(t): n for n, terms in names.items() for t in terms}
    if folded:
        pat = re.compile(
            r"(?<![^\W\d_])(?:"
            + "|".join(map(re.escape, sorted(folded, key=len, reverse=True)))
            + r")(?![^\W\d_])"
        )
        for text in ctx.paragraphs:
            for m in pat.finditer(_fold_keep_length(text)):
                forms[folded[m.group()]][text[m.start() : m.end()]] += 1
    variants = {n: dict(c) for n, c in forms.items() if len([f for f in c if not f.islower()]) > 1}
    return {"book": len(variants), "items": [{"name": n, "forms": f} for n, f in variants.items()]}


@metric("pov_distribution")
def pov_distribution(ctx: Context) -> Result:
    if not ctx.scene_cards:
        return {"unmeasured": "needs scene items in the Codex"}
    scene_words = dict(ctx.per_unit("scenes", ctx.words_in))
    words: Counter[str] = Counter()
    scenes: Counter[str] = Counter()
    for card in ctx.scene_cards:
        pov = str(card.get("pov", "?"))
        scenes[pov] += 1
        words[pov] += scene_words.get(str(card.get("anchor")), 0)
    return {"book": {"words": dict(words), "scenes": dict(scenes)}}


@metric("motif_occurrences")
def motif_occurrences(ctx: Context) -> Result:
    motifs = ctx.registers.get("motifs", [])
    if not motifs:
        return {"unmeasured": "needs motif entities in the Codex"}
    book = {}
    for m in motifs:
        terms = [m["name"], *m.get("aliases", [])]

        def count(r: range, t: list[str] = terms) -> int:
            return _count_phrases(ctx, t, r).total()

        book[m["name"]] = ctx.per_unit("chapters", count)
    return {"book": book}


def _chapter_index(ctx: Context) -> dict[str, int]:
    return {c["id"]: k for k, c in enumerate(ctx.chapters)}


@metric("setup_payoff_distance")
def setup_payoff_distance(ctx: Context) -> Result:
    setups = ctx.registers.get("setups", [])
    if not setups:
        return {"unmeasured": "needs setup items in the Codex"}
    idx = _chapter_index(ctx)
    pos = {a: k for k, a in enumerate(ctx.anchors)}
    total = ctx.words_in(ctx.all)
    cum = [0]
    for w in ctx.wc:
        cum.append(cum[-1] + w)
    items = []
    for e in setups:
        anchors = e.get("anchors", [])
        status = e.get("status", "open")
        if status == "dropped":
            items.append({"id": e["id"], "status": "dropped"})
            continue
        if status != "paid_off":
            items.append({"id": e["id"], "status": "unpaid"})
            continue
        if len(anchors) < 2:
            items.append({"id": e["id"], "status": "unplanted"})  # payoff with no setup
            continue
        a, b = anchors[0], anchors[-1]
        ca, cb = idx.get(a.split(".s")[0].split(".p")[0], 0), idx.get(b.split(".s")[0], 0)
        pa, pb = pos.get(a), pos.get(b)
        pct = (
            _round(100 * (cum[pb] - cum[pa]) / total, 1)
            if pa is not None and pb is not None and total
            else None
        )
        items.append({"id": e["id"], "chapters": cb - ca, "percent": pct})
    return {"book": sum(1 for x in items if "chapters" in x), "items": items}


@metric("open_thread_count")
def open_thread_count(ctx: Context) -> Result:
    setups = ctx.registers.get("setups", [])
    if not setups:
        return {"unmeasured": "needs setup items in the Codex"}
    idx = _chapter_index(ctx)
    per: dict[str, int] = {}
    stale = []
    span = max(3, len(ctx.chapters) // 4)
    for c in ctx.chapters:
        k = idx[c["id"]]
        n = 0
        for e in setups:
            chs = sorted(idx.get(a.split(".s")[0], 0) for a in e.get("anchors", []))
            if not chs or chs[0] > k:
                continue
            if e.get("status") in ("paid_off", "dropped") and chs[-1] <= k:
                continue
            n += 1
        per[c["id"]] = n
    for e in setups:
        chs = sorted(idx.get(a.split(".s")[0], 0) for a in e.get("anchors", []))
        gaps = [b - a for a, b in pairwise(chs)]
        if e.get("status", "open") == "open" and (
            max(gaps, default=0) > span or (chs and len(ctx.chapters) - 1 - chs[-1] > span)
        ):
            stale.append({"id": e["id"], "last": e["anchors"][-1] if e.get("anchors") else None})
    return {"book": max(per.values(), default=0), "chapters": per, "items": stale}


# --- LLM-labelled, script-aggregated --------------------------------------------------


@metric("chapter_ending_types")
def chapter_ending_types(ctx: Context) -> Result:
    labels: dict[str, str] = ctx.labels.get("chapter_endings", {})
    if not labels:
        return {"unmeasured": "needs labels.chapter_endings (analysis/labels.json)"}
    seq = [labels[c["id"]] for c in ctx.chapters if c["id"] in labels]
    longest, run = 1, 1
    for a, b in pairwise(seq):
        run = run + 1 if a == b else 1
        longest = max(longest, run)
    return {"book": dict(Counter(seq)), "variety": len(set(seq)), "longest_same_run": longest}


@metric("scene_summary_ratio")
def scene_summary_ratio(ctx: Context) -> Result:
    marked = set(ctx.labels.get("summary_passages", []))
    if not marked:
        return {"unmeasured": "needs labels.summary_passages (anchors of summary-mode paragraphs)"}

    def ratio(r: Iterable[int]) -> float:
        w = ctx.words_in(r)
        return _round(sum(ctx.wc[i] for i in r if ctx.anchors[i] in marked) / w) if w else 0.0

    return {"book": ratio(ctx.all), "chapters": ctx.per_unit("chapters", ratio)}


@metric("denouement_share")
def denouement_share(ctx: Context) -> Result:
    climax = ctx.labels.get("climax")
    if climax not in ctx.anchors:
        return {"unmeasured": "needs labels.climax (anchor of the climax paragraph)"}
    k = ctx.anchors.index(climax)
    total = ctx.words_in(ctx.all)
    return {"book": _round(ctx.words_in(range(k, len(ctx.paragraphs))) / total) if total else 0}


@metric("opening_hook_span")
def opening_hook_span(ctx: Context) -> Result:
    start = next((c["start"] for c in ctx.chapters if not c["id"].endswith("c00")), 0)
    confirmed = ctx.labels.get("opening_hook")
    cues = _phrase_re(
        ["pero", "sin embargo", "de pronto", "de repente", "but", "however", "suddenly", "no"]
    )
    words = 0
    for i in range(start, len(ctx.paragraphs)):
        if (confirmed and ctx.anchors[i] == confirmed) or (
            not confirmed
            and ".s0." not in ctx.anchors[i]
            and (
                ctx.speech[i]
                or re.search(r"[?!¿¡]", ctx.paragraphs[i])
                or (cues and cues.search(ctx.paragraphs[i]))
            )
        ):
            return {
                "book": words,
                "anchor": ctx.anchors[i],
                "source": "label" if confirmed else "candidate",
            }
        words += ctx.wc[i]
    return {"book": words, "anchor": None, "source": "none found"}


# --- proofreading ---------------------------------------------------------------------


@metric("author_note_markers")
def author_note_markers(ctx: Context) -> Result:
    markers = ctx.lex.get("note_markers", [])
    pat = re.compile(
        r"\[[^\]]*\]|\{[^}]*\}|(?<![^\W\d_])(?:"
        + "|".join(map(re.escape, markers))
        + r")(?![^\W\d_])|\?\?"
    )
    items = [
        {"anchor": ctx.anchors[i], "marker": m.group()[:40]}
        for i in ctx.all
        for m in pat.finditer(ctx.paragraphs[i])
    ]
    titles = Counter(c.get("title") for c in ctx.chapters if c.get("title"))
    items += [
        {"anchor": "", "marker": f"duplicated heading: {t}"} for t, n in titles.items() if n > 1
    ]
    return {"book": len(items), "items": items}


@metric("typo_signals")
def typo_signals(ctx: Context) -> Result:
    checks = {
        "doubled word": re.compile(r"(?<![^\W\d_])([^\W\d_]{2,})\s+\1(?![^\W\d_])", re.I),
        "space before punctuation": re.compile(r"[^\W\d_]\s+[,.;:!?](?!\.)"),
        "lowercase after full stop": re.compile(r"[^.]\.\s+[a-zà-ÿ]"),
    }
    items = []
    for i in ctx.all:
        t = ctx.paragraphs[i]
        for name, pat in checks.items():
            for m in pat.finditer(t):
                items.append({"anchor": ctx.anchors[i], "signal": name, "text": m.group()[:30]})
        for a, b in ("()", "[]", "«»", "“”", "¿?", "¡!"):
            if a in "«“" and ts.continues_speech(t):
                continue  # a speech running over several paragraphs
            if t.count(a) != t.count(b) and (a not in "¿¡" or ctx.lang == "es"):
                items.append({"anchor": ctx.anchors[i], "signal": f"unmatched {a}{b}", "text": ""})
    return {
        "book": len(items),
        "counts": dict(Counter(x["signal"] for x in items)),
        "items": items[:500],
    }


# --- runner ---------------------------------------------------------------------------


def compute(ctx: Context, only: Iterable[str] | None = None) -> dict[str, Result]:
    out: dict[str, Result] = {}
    for mid in only or REGISTRY:
        out[mid] = REGISTRY[mid](ctx)
    return out


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def codex_registers(
    ws_root: Path, version: str, anchors: list[str]
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Characters, motifs, setups and scenes from the Codex, when it is synced to ``version``.

    Names that differ only in case or accents are one entry. Setups pair with
    payoffs through ``pays_off`` links; their anchors are paragraph anchors of
    the draft, in text order. A payoff with no live setup is listed on its own.
    """
    cx = codex.synced(ws_root, version)
    if cx is None:
        return {}, []
    pos = {a: i for i, a in enumerate(anchors)}
    registers: dict[str, list[dict[str, Any]]] = {}
    named: dict[tuple[str, str], dict[str, Any]] = {}
    for e in cx.live("entity"):
        kind = {"character": "characters", "motif": "motifs"}.get(e.fields["kind"])
        if not kind:
            continue
        key = (kind, " ".join(ts.strip_accents(e.fields["name"]).casefold().split()))
        if key not in named:
            named[key] = {"name": e.fields["name"], "aliases": []}
            registers.setdefault(kind, []).append(named[key])
        entry = named[key]
        for alias in [e.fields["name"], *e.fields.get("aliases", [])]:
            if alias != entry["name"] and alias not in entry["aliases"]:
                entry["aliases"].append(alias)
    setups = {i.id: i for i in cx.live("setup")}
    labels: Counter[str] = Counter(i.fields["label"] for i in setups.values())

    def anchored(*items: Any) -> list[str]:
        paras = {sp.start.para for x in items for sp in x.spans} & pos.keys()
        return sorted(paras, key=pos.__getitem__)

    for item in setups.values():
        label = item.fields["label"]
        uid = label if labels[label] == 1 else f"{label} ({item.id})"
        if item.fields["side"] == "setup":
            payoffs = [
                i for i, rel in cx.linked_to(item.id) if rel == "pays_off" and i.id in setups
            ]
            status = "paid_off" if payoffs else "open"
            entry = {"id": uid, "anchors": anchored(item, *payoffs), "status": status}
        elif not any(lk["rel"] == "pays_off" and lk["to"] in setups for lk in item.links):
            entry = {"id": uid, "anchors": anchored(item), "status": "paid_off"}
        else:
            continue
        registers.setdefault("setups", []).append(entry)
    cards = [
        {"anchor": unit, "pov": item.fields.get("pov", "?")}
        for unit, item in cx.scenes_by_unit(anchors).items()
    ]
    return registers, cards


def context_for(ws_root: Path, version: str, lang: str) -> Context:
    text = (ws_root / "text" / f"{version}.txt").read_text(encoding="utf-8")
    paras = text.split("\n")[:-1] if text.endswith("\n") else text.split("\n")
    struct = _load_json(ws_root / "index" / version / "structure.json")
    if struct is None:
        raise FileNotFoundError(f"no structure for {version}; run `lc anchor` first")
    meta = (_load_json(ws_root / "text" / f"{version}.meta.json") or {}).get("paragraphs", [])
    registers, cards = codex_registers(ws_root, version, [a for a, _ in struct["paragraphs"]])
    labels = _load_json(ws_root / "analysis" / "labels.json") or {}
    return Context(
        paragraphs=paras,
        anchors=[a for a, _ in struct["paragraphs"]],
        chapters=struct["chapters"],
        lang=lang,
        parts=struct.get("parts", []),
        meta=meta,
        registers=registers,
        scene_cards=cards,
        labels=labels,
    )


def build(ws_root: Path, version: str, lang: str) -> tuple[Path, dict[str, Result]]:
    ctx = context_for(ws_root, version, lang)
    results = compute(ctx)
    out = ws_root / "metrics" / f"{version}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "version": version, "language": lang, "metrics": results}
    out.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    return out, results


def implemented_ratio(registry_ids: Iterable[str]) -> float:
    ids = list(registry_ids)
    return sum(1 for m in ids if m in REGISTRY) / len(ids) if ids else 0.0
