"""Text spans that keep their place while the writer edits.

A span is a stretch of a draft of any length: a word, a sentence, a dialogue,
a scene, a two-page digression. It is stored the way web annotations are
(W3C Web Annotation, as Hypothesis does): a position (paragraph anchor plus
character offset, at both ends) for speed, and a text quote (the exact text
with a little context before and after) for truth. Long quotes keep only their
head, tail, length and hash.

``relocate`` moves a span to a new draft. A span is placed only where its
exact text is found again. When the text changed, or more than one place fits
equally well, the span is marked ``changed`` (or ``lost`` when the paragraphs
it lived in are gone) and is never moved silently.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from litcritic.diff import Alignment

QUOTE_MAX = 300  # longer quotes keep head, tail, length and hash
HEAD = 150
CONTEXT = 32
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
    g = text.joined.find(quote)
    while g != -1:
        if not within or text.anchors[text.para_of(g)].startswith(within):
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


def _occurrences(span: Span, text: str) -> list[tuple[int, int]]:
    needle = span.head or span.exact
    size = span.length if span.head else len(span.exact)
    out = []
    g = text.find(needle)
    while g != -1:
        if matches(span, text, g, g + size):
            out.append((g, g + size))
        g = text.find(needle, g + 1)
    return out


def _context_score(span: Span, text: str, g0: int, g1: int) -> int:
    before, after = text[max(0, g0 - CONTEXT) : g0], text[g1 : g1 + CONTEXT]
    score = 0
    for a, b in zip(reversed(span.prefix), reversed(before), strict=False):
        if a != b:
            break
        score += 1
    for a, b in zip(span.suffix, after, strict=False):
        if a != b:
            break
        score += 1
    return score


def relocate(span: Span, old: Text, new: Text, alignment: Alignment, draft: str) -> Span:
    """The span in the new draft, or the same span marked ``changed`` / ``lost``."""
    i0, i1 = old.index.get(span.start.para), old.index.get(span.end.para)
    if i0 is None or i1 is None:
        raise SpanError(f"span is not in the old draft ({span.start.para}..{span.end.para})")
    region = {j for i in range(i0, i1 + 1) for j in alignment.old[i]["new"]}
    out = Span(**{**span.__dict__, "draft": draft})
    # Fast path: both end paragraphs kept their text; same offsets, verified.
    e0, e1 = alignment.old[i0], alignment.old[i1]
    if e0["status"] in ("unchanged", "moved") and e1["status"] in ("unchanged", "moved"):
        j0, j1 = e0["new"][0], e1["new"][0]
        if j0 <= j1:
            g0 = new.starts[j0] + span.start.off
            g1 = new.starts[j1] + span.end.off
            if matches(span, new.joined, g0, g1):
                return _placed(out, new, g0, g1, span)
    # Quote search: exact text anywhere; prefer the old paragraphs' new home, then context.
    found = _occurrences(span, new.joined)
    if found:
        ranked = sorted(
            (
                (new.para_of(g0) in region, _context_score(span, new.joined, g0, g1), g0, g1)
                for g0, g1 in found
            ),
            reverse=True,
        )
        best = ranked[0]
        if len(ranked) == 1 or ranked[1][:2] != best[:2]:
            return _placed(out, new, best[2], best[3], span)
    # Not found, or ambiguous: point at where it was, flag it.
    if region:
        js = sorted(region)
        out.start = Pos(new.anchors[js[0]], 0)
        out.end = Pos(new.anchors[js[-1]], len(new.paragraphs[js[-1]]))
        out.state = "changed"
    else:
        out.draft = span.draft
        out.state = "lost"
    return out


def _placed(out: Span, new: Text, g0: int, g1: int, old_span: Span) -> Span:
    out.start, out.end = new.local(g0), new.local(g1)
    out.prefix = new.joined[max(0, g0 - CONTEXT) : g0]
    out.suffix = new.joined[g1 : g1 + CONTEXT]
    same = (out.start, out.end) == (old_span.start, old_span.end)
    out.state = "ok" if same else "moved"
    return out
