"""Text spans that keep their place while the writer edits.

A span is a stretch of a draft of any length: a word, a sentence, a dialogue,
a scene, a two-page digression. It is stored the way web annotations are
(W3C Web Annotation, as Hypothesis does): a position (paragraph anchor plus
character offset, at both ends) for speed, and a text quote (the exact text
with a little context before and after) for truth. Long quotes keep only their
head, tail, length and hash.

``relocate`` moves a span to a new draft. Spans whose paragraphs kept their
text keep their offsets (checked against the quote); the others are looked up
with doc-control's ``anchor.resolve`` in exact mode, never fuzzily. A span is
placed only where its exact text is found again. When the text changed, or more
than one place fits equally well, the span is marked ``changed`` (or ``lost``
when the paragraphs it lived in are gone) and is never moved silently.

For a ``changed`` or ``lost`` span the position says where to look and the
quote keeps the last text seen there; the two no longer agree until the span is
re-read and rebuilt. A later relocation still searches for that quote, so text
the writer restores is found again.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from litcritic import dc, diff
from litcritic.diff import Alignment
from litcritic.query import _bare

QUOTE_MAX = 300  # longer quotes keep head, tail, length and hash
HEAD = 150
CONTEXT = 32
# doc-control's score (quote and context, 0-1) a match away from the span's old
# paragraphs needs; the same bar doc-control sets for a far match (FAR_MIN_SCORE)
AWAY_MIN_SCORE = 0.85
ADDRESS = re.compile(r"p(\d+)#([^:.]+)")  # a doc-control paragraph address
RANGE = re.compile(r"p(\d+)#[^:]*:(\d+)-(\d+)")  # a doc-control range in one paragraph
STATES = ("ok", "moved", "changed", "lost")


class SpanError(ValueError):
    """A span cannot be built as asked."""


@dataclass
class Pos:
    para: str
    off: int


@dataclass
class Span:
    draft: str
    start: Pos
    end: Pos  # exclusive
    prefix: str = ""
    suffix: str = ""
    exact: str = ""
    head: str = ""
    tail: str = ""
    length: int = 0
    sha1: str = ""
    state: str = "ok"

    def as_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "draft": self.draft,
            "start": {"para": self.start.para, "off": self.start.off},
            "end": {"para": self.end.para, "off": self.end.off},
            "prefix": self.prefix,
            "suffix": self.suffix,
            "state": self.state,
        }
        if self.head:
            out.update(head=self.head, tail=self.tail, len=self.length, sha1=self.sha1)
        else:
            out["exact"] = self.exact
        return out

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Span:
        if not d.get("exact") and not d.get("head"):
            raise SpanError("span has no quote (exact or head)")
        return cls(
            draft=d["draft"],
            start=Pos(d["start"]["para"], int(d["start"]["off"])),
            end=Pos(d["end"]["para"], int(d["end"]["off"])),
            prefix=d.get("prefix", ""),
            suffix=d.get("suffix", ""),
            exact=d.get("exact", ""),
            head=d.get("head", ""),
            tail=d.get("tail", ""),
            length=int(d.get("len", 0)),
            sha1=d.get("sha1", ""),
            state=d.get("state", "ok"),
        )


@dataclass
class Text:
    """One draft's paragraphs and anchors, joined with newlines for offsets."""

    paragraphs: list[str]
    anchors: list[str]
    draft: str = ""  # when set, spans from another draft are not read by position
    joined: str = field(init=False)
    starts: list[int] = field(init=False)
    index: dict[str, int] = field(init=False)

    def __post_init__(self) -> None:
        if len(self.paragraphs) != len(self.anchors):
            raise SpanError("paragraphs and anchors differ in number")
        self.joined = "\n".join(self.paragraphs)
        self.starts = []
        g = 0
        for p in self.paragraphs:
            self.starts.append(g)
            g += len(p) + 1
        self.index = {a: i for i, a in enumerate(self.anchors)}

    def gpos(self, anchor: str, off: int) -> int:
        i = self.index.get(anchor)
        if i is None:
            raise SpanError(f"no paragraph {anchor!r}")
        if not 0 <= off <= len(self.paragraphs[i]):
            raise SpanError(f"offset {off} outside paragraph {anchor!r}")
        return self.starts[i] + off

    def para_of(self, g: int) -> int:
        lo, hi = 0, len(self.starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.starts[mid] <= g:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def local(self, g: int) -> Pos:
        i = self.para_of(g)
        return Pos(self.anchors[i], g - self.starts[i])


def _quote(span: Span, text: str, g0: int, g1: int) -> None:
    body = text[g0:g1]
    span.prefix = text[max(0, g0 - CONTEXT) : g0]
    span.suffix = text[g1 : g1 + CONTEXT]
    if len(body) > QUOTE_MAX:
        span.exact = ""
        span.head, span.tail = body[:HEAD], body[-HEAD:]
        span.length = len(body)
        span.sha1 = hashlib.sha1(body.encode("utf-8")).hexdigest()
    else:
        span.exact, span.head, span.tail, span.length, span.sha1 = body, "", "", 0, ""


def make(text: Text, draft: str, start: str, start_off: int, end: str, end_off: int) -> Span:
    """A span from ``start``/``start_off`` to ``end``/``end_off`` (exclusive)."""
    g0, g1 = text.gpos(start, start_off), text.gpos(end, end_off)
    if g1 <= g0:
        raise SpanError("a span must end after it starts")
    span = Span(draft, Pos(start, start_off), Pos(end, end_off))
    _quote(span, text.joined, g0, g1)
    return span


def from_quote(text: Text, draft: str, quote: str, within: str = "") -> Span:
    """A span for the one place ``quote`` occurs (optionally inside one anchor prefix)."""
    if not quote:
        raise SpanError("empty quote")
    hits = []
    unit = _bare(within) if within else ""
    g = text.joined.find(quote)
    while g != -1:
        bare = _bare(text.anchors[text.para_of(g)])
        if not unit or bare == unit or bare.startswith(unit + "."):
            hits.append(g)
        g = text.joined.find(quote, g + 1)
    if len(hits) != 1:
        where = f" in {within}" if within else ""
        raise SpanError(f"quote found {len(hits)} times{where}; give more words or --within")
    g0, g1 = hits[0], hits[0] + len(quote)
    a, b = text.local(g0), text.local(g1)
    return make(text, draft, a.para, a.off, b.para, b.off)


def matches(span: Span, text: str, g0: int, g1: int) -> bool:
    """Whether the stored quote is exactly ``text[g0:g1]``."""
    if span.head:
        if g1 - g0 != span.length:
            return False
        body = text[g0:g1]
        return (
            body.startswith(span.head)
            and body.endswith(span.tail)
            and hashlib.sha1(body.encode("utf-8")).hexdigest() == span.sha1
        )
    return text[g0:g1] == span.exact


@dataclass(frozen=True)
class Hit:
    """A place doc-control gave for a quote: offset into ``Text.joined``, score, match kind."""

    g: int
    score: float
    kind: str


class Resolver:
    """A draft as doc-control sees it, for ``anchor.resolve`` in exact mode.

    The draft's paragraphs are written to a plain-text file on first use (most spans
    never need it: their paragraphs kept their text) and held open until ``close``.
    Answers are cached per anchor. ``fuzzy`` counts places doc-control gave as fuzzy
    matches: exact mode never should, and they are never used.
    """

    def __init__(self, text: Text) -> None:
        self.text = text
        self.calls = 0
        self.fuzzy = 0
        self._stack: ExitStack | None = None
        self._doc: dc.Document | None = None
        self._numbers: list[int] = []  # doc-control paragraph number of each text paragraph
        self._fps: list[str] = []
        self._index: dict[int, int] = {}
        self._cache: dict[tuple[tuple[str, str], ...], tuple[str, list[Hit]]] = {}

    def __enter__(self) -> Resolver:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._stack is not None:
            self._stack.close()
        self._stack = self._doc = None

    def _open(self) -> dc.Document:
        if self._doc is None:
            with ExitStack() as stack:
                folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
                self._doc, ats = stack.enter_context(
                    diff.as_document(self.text.paragraphs, folder, "draft", normalized=False)
                )
                self._stack = stack.pop_all()
            self._numbers, self._fps, self._index = [], [], {}
            for k, at in enumerate(ats):
                m = ADDRESS.fullmatch(at)
                if m is None:
                    raise SpanError(f"not a doc-control paragraph address: {at!r}")
                self._numbers.append(int(m[1]))
                self._fps.append(m[2])
                self._index[int(m[1])] = k
        return self._doc

    def near(self, j: int) -> dict[str, str]:
        """The ``hint`` and ``fingerprint`` that name paragraph ``j`` as the quote's home."""
        self._open()
        return {"hint": f"p{self._numbers[j]}", "fingerprint": self._fps[j]}

    def resolve(self, anchor: dict[str, str]) -> tuple[str, list[Hit]]:
        """``found`` (one hit), ``ambiguous`` (the tied hits) or ``not_found`` (none)."""
        key = tuple(sorted(anchor.items()))
        if key in self._cache:
            return self._cache[key]
        doc = self._open()
        self.calls += 1
        try:
            status, rows = (
                "found",
                [
                    doc.run(
                        "anchor.resolve",
                        {"anchor": anchor, "mode": "exact", "match_level": "exact"},
                    )
                ],
            )
        except dc.DocError as exc:
            if exc.code == "ANCHOR_AMBIGUOUS":
                status, rows = "ambiguous", list(exc.details.get("candidates") or [])
            elif exc.code == "ANCHOR_NOT_FOUND":
                status, rows = "not_found", []
            else:
                raise
        hits = []
        for row in rows:
            m = RANGE.fullmatch(str(row["at"]))
            if row.get("match") == "fuzzy" or m is None or int(m[1]) not in self._index:
                self.fuzzy += row.get("match") == "fuzzy"
                continue
            g = self.text.starts[self._index[int(m[1])]] + int(m[2])
            hits.append(Hit(g, float(row.get("score", 0.0)), str(row.get("match", "exact"))))
        out = (status if hits else "not_found", hits)
        self._cache[key] = out
        return out


def _piece(needle: str) -> tuple[int, str]:
    """The quote's first line with text in it, and where it starts in the quote.

    doc-control anchors quote one paragraph; the rest of the span is checked here.
    """
    k = 0
    for line in needle.split("\n"):
        if line.strip():
            return k, line
        k += len(line) + 1
    return 0, ""


def relocate(
    span: Span,
    old: Text,
    new: Text,
    alignment: Alignment,
    draft: str,
    kept: dict[int, int] | None = None,
    resolver: Resolver | None = None,
) -> Span:
    """The span in the new draft, or the same span marked ``changed`` / ``lost``.

    ``kept`` is ``alignment.mapping()`` and ``resolver`` a ``Resolver`` of ``new``; pass
    both when relocating many spans. A span whose anchors are not in ``old`` (one already
    lost) is only searched for.
    """
    kept = alignment.mapping() if kept is None else kept
    i0, i1 = old.index.get(span.start.para), old.index.get(span.end.para)
    if old.draft and span.draft != old.draft:  # anchors are positional: never reuse them
        i0 = i1 = None
    region: set[int] = set()
    out = Span(**{**span.__dict__, "draft": draft})
    home: int | None = None
    if i0 is not None and i1 is not None:
        region = {j for i in range(i0, i1 + 1) for j in alignment.old[i]["new"]}
        home = kept[i0] if i0 in kept else min(region, default=None)
        # Fast path: both end paragraphs kept their text; same offsets, verified.
        if i0 in kept and i1 in kept and kept[i0] <= kept[i1]:
            g0 = new.starts[kept[i0]] + span.start.off
            g1 = new.starts[kept[i1]] + span.end.off
            if matches(span, new.joined, g0, g1):
                return _placed(out, new, g0, g1, span)
    if resolver is None:
        with Resolver(new) as own:
            return _search(span, out, new, region, home, own)
    if resolver.text is not new:
        raise SpanError("the resolver reads another draft")
    return _search(span, out, new, region, home, resolver)


def _search(
    span: Span, out: Span, new: Text, region: set[int], home: int | None, rs: Resolver
) -> Span:
    """Find the quote with doc-control's ``anchor.resolve`` (exact mode), or flag the span.

    The anchor is the quote's first line, with the stored context; every place doc-control
    gives is checked against the whole stored quote. One verified place is taken when it
    is where the old paragraphs went, or when elsewhere doc-control scores its context at
    least ``AWAY_MIN_SCORE``; a tie is taken only when one tied place is at home.
    """
    needle = span.head or span.exact
    if not needle:
        raise SpanError("span has no quote (exact or head)")
    size = span.length if span.head else len(span.exact)
    k, piece = _piece(needle)
    status, places = "not_found", []
    if piece:
        rest = needle[k + len(piece) :]
        anchor = {
            "exact": piece,
            "prefix": (span.prefix + needle[:k])[-CONTEXT:],
            "suffix": rest[:CONTEXT] if rest or span.head else span.suffix,
        }
        if home is not None:
            anchor |= rs.near(home)
        status, hits = rs.resolve(anchor)
        for h in hits:
            g0 = h.g - k
            if g0 >= 0 and matches(span, new.joined, g0, g0 + size):
                at_home = new.para_of(g0) in region
                trusted = at_home or (status == "found" and h.score >= AWAY_MIN_SCORE)
                places.append((g0, g0 + size, trusted))
    trusted_places = [p for p in places if p[2]]
    if len(trusted_places) == 1:
        return _placed(out, new, trusted_places[0][0], trusted_places[0][1], span)
    # Not found, ambiguous or untrusted: point at where to look, flag it.
    if region or places:
        if region:
            js = sorted(region)
            first, last = js[0], js[-1]
        else:
            first = last = new.para_of(places[0][0])
        out.start = Pos(new.anchors[first], 0)
        out.end = Pos(new.anchors[last], len(new.paragraphs[last]))
        out.state = "changed"
    else:
        out.draft = span.draft  # keeps the coordinates of the draft it was last seen in
        out.state = "lost"
    return out


def _placed(out: Span, new: Text, g0: int, g1: int, old_span: Span) -> Span:
    out.start, out.end = new.local(g0), new.local(g1)
    out.prefix = new.joined[max(0, g0 - CONTEXT) : g0]
    out.suffix = new.joined[g1 : g1 + CONTEXT]
    same = (out.start, out.end) == (old_span.start, old_span.end)
    out.state = "ok" if same else "moved"
    return out
