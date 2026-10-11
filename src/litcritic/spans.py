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

For a ``changed`` or ``lost`` span the position says where to look and the
quote keeps the last text seen there; the two no longer agree until the span is
re-read and rebuilt. A later relocation still searches for that quote, so text
the writer restores is found again.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from litcritic.diff import Alignment
from litcritic.query import _bare

QUOTE_MAX = 300  # longer quotes keep head, tail, length and hash
HEAD = 150
CONTEXT = 32
TRUSTED_CONTEXT = 24  # matching context characters needed to accept a match away from home
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


def _occurrences(span: Span, text: str, lo: int = 0, hi: int = -1) -> list[tuple[int, int]]:
    """Every place in ``text[lo:hi]`` where the stored quote matches exactly."""
    needle = span.head or span.exact
    if not needle:
        raise SpanError("span has no quote (exact or head)")
    size = span.length if span.head else len(span.exact)
    hi = len(text) if hi < 0 else hi
    out = []
    g = text.find(needle, lo, hi)
    while g != -1:
        if g + size <= hi and matches(span, text, g, g + size):
            out.append((g, g + size))
        g = text.find(needle, g + 1, hi)
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


def relocate(
    span: Span,
    old: Text,
    new: Text,
    alignment: Alignment,
    draft: str,
    kept: dict[int, int] | None = None,
) -> Span:
    """The span in the new draft, or the same span marked ``changed`` / ``lost``.

    ``kept`` is ``alignment.mapping()``; pass it when relocating many spans.
    A span whose anchors are not in ``old`` (one already lost) is only searched for.
    """
    kept = alignment.mapping() if kept is None else kept
    i0, i1 = old.index.get(span.start.para), old.index.get(span.end.para)
    if old.draft and span.draft != old.draft:  # anchors are positional: never reuse them
        i0 = i1 = None
    region: set[int] = set()
    out = Span(**{**span.__dict__, "draft": draft})
    if i0 is not None and i1 is not None:
        region = {j for i in range(i0, i1 + 1) for j in alignment.old[i]["new"]}
        # Fast path: both end paragraphs kept their text; same offsets, verified.
        if i0 in kept and i1 in kept and kept[i0] <= kept[i1]:
            g0 = new.starts[kept[i0]] + span.start.off
            g1 = new.starts[kept[i1]] + span.end.off
            if matches(span, new.joined, g0, g1):
                return _placed(out, new, g0, g1, span)
    # Quote search: the old paragraphs' new home first, then the whole draft.
    found: list[tuple[int, int]] = []
    if region:
        js = sorted(region)
        lo, hi = new.starts[js[0]], new.starts[js[-1]] + len(new.paragraphs[js[-1]])
        found = _occurrences(span, new.joined, lo, hi)
    home = bool(found)
    if not found:
        found = _occurrences(span, new.joined)
    if found:
        ranked = sorted(
            ((_context_score(span, new.joined, g0, g1), g0, g1) for g0, g1 in found),
            reverse=True,
        )
        best = ranked[0]
        unique = len(ranked) == 1 or ranked[1][0] != best[0]
        # Away from home, a match must also agree with the text around it.
        if unique and (home or best[0] >= TRUSTED_CONTEXT):
            return _placed(out, new, best[1], best[2], span)
    # Not found, ambiguous or untrusted: point at where to look, flag it.
    if region or found:
        if region:
            js = sorted(region)
            first, last = js[0], js[-1]
        else:
            first = last = new.para_of(found[0][0])
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
