"""Text edits to a .docx as tracked revisions, touching nothing else.

An edit names its target by a quote (plus optional prefix and suffix
context), matched whitespace-tolerantly inside one paragraph. It must match
exactly once in the whole document, or nothing is changed. Each affected run
is split at the match boundaries: the matched text becomes a ``w:del``, and
the replacement a ``w:ins`` run with the first affected run's formatting, so
the writer can reject every change in any Word version.

The XML is edited as text, run by run, so every other byte of
``document.xml`` and every other part of the package is kept as it was. A
match that touches anything but plain text runs (fields, tabs, breaks,
existing revisions) is refused rather than guessed. This module does no disk
I/O; ``safe_edit`` owns the file.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import unescape
from itertools import pairwise
from xml.sax.saxutils import escape

DOC = "word/document.xml"
AUTHOR = "literary-critic"
W_PREFIX = re.compile(
    r'xmlns:(\w+)="http://schemas\.openxmlformats\.org/wordprocessingml/2006/main"'
)
INVISIBLE = re.compile("[­​‌‍﻿]")


class EditError(Exception):
    """An edit cannot be applied safely; nothing was changed."""

    def __init__(self, message: str, problems: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.problems = problems or {}


@dataclass
class Edit:
    id: str
    quote: str
    replace: str
    prefix: str = ""
    suffix: str = ""


@dataclass
class Match:
    para: int  # ordinal among all w:p elements, as ingest counts them
    start: int  # character offsets in the paragraph's visible text
    end: int
    text: str


@dataclass
class _Run:
    start: int  # raw offsets of <w:r ...> ... </w:r> inside document.xml
    end: int
    rpr: str
    text: str  # unescaped text of its single w:t ("" when none)
    plain: bool  # only rPr and one w:t: safe to split
    in_revision: bool
    lead: str = ""  # a w:lastRenderedPageBreak kept before the text
    harmless: bool = False  # no text and nothing that must stay next to it (soft hyphen)


@dataclass
class _Para:
    ordinal: int
    start: int  # raw offsets of the paragraph content
    end: int
    runs: list[_Run] = field(default_factory=list)
    chars: list[tuple[int, int]] = field(default_factory=list)  # (run index, offset) per char
    text: str = ""
    hazards: list[int] = field(default_factory=list)  # raw offsets of fields/revisions


# -- reading -----------------------------------------------------------------

LOCKED = {"ins", "del", "moveFrom", "moveTo", "fldSimple", "sdt"}  # runs inside: not editable
HIDDEN = {"del", "moveFrom"}  # runs inside: not visible
VISIBLE = {"tab": " ", "cr": " ", "noBreakHyphen": "-"}


def w_prefix(xml: str) -> str:
    """The prefix bound to the WordprocessingML namespace in this part."""
    m = W_PREFIX.search(xml)
    if not m:
        raise EditError("document.xml has no prefixed WordprocessingML namespace")
    return m.group(1)


def paragraph_spans(xml: str, w: str) -> list[tuple[int, int]]:
    """(content start, content end) of every w:p, in ingest's order (pre-order)."""
    tag = re.compile(rf"<{w}:p(?=[\s>/])[^>]*?(/?)>|</{w}:p>")
    spans: list[tuple[int, int]] = []
    stack: list[int] = []
    for t in tag.finditer(xml):
        if t.group(0).startswith("</"):
            if not stack:
                raise EditError("unbalanced paragraphs in document.xml")
            k = stack.pop()
            spans[k] = (spans[k][0], t.start())
        elif t.group(1) == "/":
            spans.append((t.end(), t.end()))
        else:
            spans.append((t.end(), -1))
            stack.append(len(spans) - 1)
    if stack:
        raise EditError("unbalanced paragraphs in document.xml")
    return spans


def repack(data: bytes, parts: dict[str, bytes]) -> bytes:
    """The package with ``parts`` replaced (or added); every other part copied as is."""
    src = zipfile.ZipFile(io.BytesIO(data))
    names = set(src.namelist())
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            dst.writestr(info, parts.get(info.filename, src.read(info.filename)))
        for name, payload in parts.items():
            if name not in names:
                dst.writestr(name, payload)
    return out.getvalue()


def _run_end(xml: str, w: str, start: int) -> int:
    """End offset of the w:r opened at ``start`` (a run may hold textbox runs)."""
    tag = re.compile(rf"<{w}:r(?=[\s>/])[^>]*?(/?)>|</{w}:r>")
    depth = 0
    for t in tag.finditer(xml, start):
        if t.group(0).startswith("</"):
            depth -= 1
            if depth == 0:
                return t.end()
        elif t.group(1) != "/":
            depth += 1
        elif depth == 0:
            return t.end()
    raise EditError("unterminated run in document.xml")


def _visible(inner: str, w: str) -> str:
    """Text a reader sees in a run that is not plain (ingest's rules)."""
    inner = re.sub(rf"<{w}:txbxContent\b.*?</{w}:txbxContent>", "", inner, flags=re.S)
    inner = re.sub(r"<mc:Fallback\b.*?</mc:Fallback>", "", inner, flags=re.S)
    out = []
    for m in re.finditer(rf"<{w}:t(?:\s[^>]*)?>([^<]*)</{w}:t>|<{w}:(\w+)\b([^>]*)/>", inner):
        if m.group(1) is not None:
            out.append(unescape(m.group(1)))
        elif m.group(2) in VISIBLE:
            out.append(VISIBLE[m.group(2)])
        elif m.group(2) == "br" and 'type="page"' not in m.group(3):
            out.append(" ")
    return "".join(out)


class _Doc:
    """Paragraph spans plus what each paragraph needs to be parsed on its own."""

    def __init__(self, xml: str) -> None:
        self.xml = xml
        self.w = w_prefix(xml)
        self.spans = paragraph_spans(xml, self.w)
        self._index()

    def _index(self) -> None:
        # Children of each paragraph (textboxes), and complex-field depth at its start:
        # fields such as a TOC begin in one paragraph and end several later.
        self.children: dict[int, list[int]] = {}
        stack: list[int] = []
        order = sorted(range(len(self.spans)), key=lambda k: self.spans[k][0])
        for k in order:
            s = self.spans[k][0]
            while stack and not s < self.spans[stack[-1]][1]:
                stack.pop()
            if stack:
                self.children.setdefault(stack[-1], []).append(k)
            stack.append(k)
        marks = [
            (m.start(), 1 if m.group(1) == "begin" else -1)
            for m in re.finditer(
                rf'<{self.w}:fldChar\b[^>]*\b{self.w}:fldCharType="(begin|end)"', self.xml
            )
        ]
        self.field_at: list[int] = []
        depth, i = 0, 0
        for k in range(len(self.spans)):
            s = self.spans[k][0]
            while i < len(marks) and marks[i][0] < s:
                depth = max(depth + marks[i][1], 0)
                i += 1
            self.field_at.append(depth)

    def para(self, k: int) -> _Para:
        start, end = self.spans[k]
        nested = [self.spans[c] for c in self.children.get(k, [])]
        return _parse_para(self.xml, self.w, k, start, end, nested, self.field_at[k])

    def all(self) -> list[_Para]:
        return [self.para(k) for k in range(len(self.spans))]

    def replace(self, k: int, start: int, end: int, new: str) -> None:
        """Splice raw XML inside paragraph ``k`` (edits go right to left)."""
        self.xml = self.xml[:start] + new + self.xml[end:]
        if self.children.get(k):
            self.spans = paragraph_spans(self.xml, self.w)
            self._index()
        else:
            s, e = self.spans[k]
            self.spans[k] = (s, e + len(new) - (end - start))
            for j in range(len(self.spans)):  # ancestors (a textbox paragraph) end later too
                if j != k and self.spans[j][0] < start < self.spans[j][1]:
                    a, b = self.spans[j]
                    self.spans[j] = (a, b + len(new) - (end - start))


def _parse_para(
    xml: str, w: str, ordinal: int, start: int, end: int, nested: list[tuple[int, int]], field: int
) -> _Para:
    plain = re.compile(
        rf"\s*(<{w}:rPr\b[^>]*/>|<{w}:rPr\b[^>]*>.*?</{w}:rPr>)?\s*"
        rf"(<{w}:lastRenderedPageBreak/>)?\s*"
        rf"(?:<{w}:t(?:\s[^>]*)?>([^<]*)</{w}:t>|<{w}:t\b[^>]*/>)?\s*",
        re.S,
    )
    soft = re.compile(
        rf"\s*(<{w}:rPr\b[^>]*/>|<{w}:rPr\b[^>]*>.*?</{w}:rPr>)?\s*(<{w}:softHyphen/>\s*)+", re.S
    )
    tags = re.compile(rf"<(/?){w}:(\w+)\b[^>]*?(/?)>")
    para = _Para(ordinal, start, end)
    open_: list[str] = []
    pos = start
    while pos < end:
        t = tags.search(xml, pos, end)
        if t is None:
            break
        inside = next(((a, b) for a, b in nested if a <= t.start() < b), None)
        if inside:
            pos = inside[1]
            continue
        closing, name, selfclose = t.group(1), t.group(2), t.group(3)
        if name == "r" and not closing and not selfclose:
            r_end = _run_end(xml, w, t.start())
            inner = xml[t.end() : r_end - len(f"</{w}:r>")]
            m = plain.fullmatch(inner)
            fc = re.search(rf'<{w}:fldChar\b[^>]*\b{w}:fldCharType="(\w+)"', inner)
            locked = bool(open_) or field > 0 or fc is not None
            if fc:
                para.hazards.append(t.start())
                field = max(field + {"begin": 1, "end": -1}.get(fc.group(1), 0), 0)
            text = unescape(m.group(3) or "") if m else _visible(inner, w)
            if any(n in HIDDEN for n in open_):
                text = ""
            run = _Run(
                t.start(),
                r_end,
                (m.group(1) or "") if m else "",
                text,
                m is not None,
                locked,
                (m.group(2) or "") if m else "",
                m is None and soft.fullmatch(inner) is not None,
            )
            idx = len(para.runs)
            para.runs.append(run)
            para.chars += [(idx, k if m is not None else -1) for k in range(len(text))]
            para.text += text
            pos = r_end
            continue
        if name in LOCKED:
            para.hazards.append(t.start())
            if closing:
                if name in open_:
                    del open_[len(open_) - 1 - open_[::-1].index(name)]
            elif not selfclose:
                open_.append(name)
        pos = t.end()
    return para


def _norm(text: str) -> tuple[str, list[int]]:
    """Whitespace collapsed, invisible characters dropped; maps norm index -> original."""
    out: list[str] = []
    where: list[int] = []
    space = False
    for i, ch in enumerate(text):
        if INVISIBLE.match(ch):
            continue
        if ch.isspace():
            if not space and out:
                out.append(" ")
                where.append(i)
            space = True
            continue
        space = False
        out.append(ch)
        where.append(i)
    if out and out[-1] == " ":
        out.pop()
        where.pop()
    return "".join(out), where


def _nq(text: str) -> str:
    return _norm(text)[0]


def _matches(paras: list[_Para], edit: Edit) -> list[Match]:
    quote = _nq(edit.quote)
    if not quote:
        raise EditError(f"{edit.id}: empty quote", {edit.id: "empty quote"})
    prefix, suffix = _nq(edit.prefix), _nq(edit.suffix)
    norms = [_norm(p.text) for p in paras]
    found = []
    for k, p in enumerate(paras):
        norm, where = norms[k]
        for m in re.finditer(re.escape(quote), norm):
            # Context may run into the neighbouring paragraphs.
            if prefix:
                before = (norms[k - 1][0] + " " if k else "") + norm[: m.start()]
                if not before.rstrip().endswith(prefix):
                    continue
            if suffix:
                after = norm[m.end() :] + (" " + norms[k + 1][0] if k + 1 < len(paras) else "")
                if not after.lstrip().startswith(suffix):
                    continue
            start, end = where[m.start()], where[m.end() - 1] + 1
            found.append(Match(p.ordinal, start, end, p.text[start:end]))
    return found


# -- writing -----------------------------------------------------------------


def _attr(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def _revision_ids(xml: str) -> int:
    ids = [int(x) for x in re.findall(r'\b\w+:id="(\d+)"', xml)]
    return max(ids, default=0) + 1


def _run_xml(w: str, rpr: str, text: str, deleted: bool = False, lead: str = "") -> str:
    tag = "delText" if deleted else "t"
    return f'<{w}:r>{rpr}{lead}<{w}:{tag} xml:space="preserve">{escape(text)}</{w}:{tag}></{w}:r>'


def _apply_one(
    doc: _Doc, match: Match, replace: str, ids: list[int], author: str, date: str
) -> None:
    w = doc.w
    para = doc.para(match.para)
    for i in range(match.start, match.end):
        if para.chars[i][1] < 0:
            raise EditError("the passage crosses a tab, break or field; edit it by hand")
    affected = sorted({para.chars[i][0] for i in range(match.start, match.end)})
    span = range(affected[0], affected[-1] + 1)
    if any(
        not (para.runs[k].plain or para.runs[k].harmless) or para.runs[k].in_revision for k in span
    ):
        raise EditError(
            "the passage crosses a note mark, picture or other special run; edit it by hand"
        )
    lo, hi = para.runs[affected[0]].start, para.runs[affected[-1]].end
    if any(lo < h < hi for h in para.hazards):
        raise EditError("the passage crosses a field or an existing tracked change")
    first = para.runs[affected[0]]
    pieces: list[tuple[int, int, str]] = []
    for n, k in enumerate(affected):
        r = para.runs[k]
        offs = [para.chars[i][1] for i in range(match.start, match.end) if para.chars[i][0] == k]
        a, b = min(offs), max(offs) + 1
        out = ""
        if a > 0:
            out += _run_xml(w, r.rpr, r.text[:a], lead=r.lead)
        elif r.lead:
            out += f"<{w}:r>{r.rpr}{r.lead}</{w}:r>"  # keep the page mark where it was
        rid = ids[0]
        ids[0] += 1
        out += (
            f'<{w}:del {w}:id="{rid}" {w}:author="{_attr(author)}" {w}:date="{date}">'
            f"{_run_xml(w, r.rpr, r.text[a:b], deleted=True)}</{w}:del>"
        )
        if n == len(affected) - 1 and replace:
            rid = ids[0]
            ids[0] += 1
            out += (
                f'<{w}:ins {w}:id="{rid}" {w}:author="{_attr(author)}" {w}:date="{date}">'
                f"{_run_xml(w, first.rpr, replace)}</{w}:ins>"
            )
        if b < len(r.text):
            out += _run_xml(w, r.rpr, r.text[b:])
        pieces.append((r.start, r.end, out))
    for start, end, out in reversed(pieces):
        doc.replace(match.para, start, end, out)


def _read(data: bytes) -> str:
    try:
        return zipfile.ZipFile(io.BytesIO(data)).read(DOC).decode("utf-8")
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
        raise EditError(f"not a readable .docx: {exc}") from exc


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _apply_all(
    data: bytes,
    planned: list[tuple[Match, str]],
    author: str,
    date: str | None,
    skipped: list[tuple[Match, str]] | None = None,
) -> bytes:
    """Apply right to left. With ``skipped``, unsafe matches are listed there and left alone;
    without it, the first unsafe match aborts everything (nothing is written)."""
    doc = _Doc(_read(data))
    ids = [_revision_ids(doc.xml)]
    when = date or _now()
    # Right to left: earlier offsets stay valid, only the touched paragraph is re-read.
    for m, replace in sorted(planned, key=lambda t: (t[0].para, t[0].start), reverse=True):
        try:
            _apply_one(doc, m, replace, ids, author, when)  # raises before changing anything
        except EditError as exc:
            if skipped is None:
                raise EditError(f"paragraph {m.para}: {exc}", {str(m.para): str(exc)}) from exc
            skipped.append((m, str(exc)))
    if skipped:
        skipped.sort(key=lambda t: (t[0].para, t[0].start))
    return repack(data, {DOC: doc.xml.encode("utf-8")})


# -- public ------------------------------------------------------------------


def texts(data: bytes) -> list[str]:
    """Visible text of every w:p, by ordinal (fields and deletions excluded)."""
    return [p.text for p in _Doc(_read(data)).all()]


def find(data: bytes, quote: str, prefix: str = "", suffix: str = "") -> list[Match]:
    return _matches(_Doc(_read(data)).all(), Edit("find", quote, "", prefix, suffix))


def apply(
    data: bytes, edits: list[Edit], author: str = AUTHOR, date: str | None = None
) -> tuple[bytes, list[Match]]:
    """All edits as tracked revisions, or none: raises EditError naming each failure."""
    paras = _Doc(_read(data)).all()
    problems: dict[str, str] = {}
    planned: list[tuple[Edit, Match]] = []
    for e in edits:
        try:
            found = _matches(paras, e)
        except EditError as exc:
            problems.update(exc.problems)
            continue
        if len(found) != 1:
            problems[e.id] = "not found" if not found else f"found {len(found)} times; add context"
            continue
        planned.append((e, found[0]))
    spots = sorted((m.para, m.start, m.end, e.id) for e, m in planned)
    for (p1, _, e1, a), (p2, s2, _, b) in pairwise(spots):
        if p1 == p2 and s2 < e1:
            problems[b] = f"overlaps {a}"
    if problems:
        raise EditError("; ".join(f"{k}: {v}" for k, v in problems.items()), problems)
    try:
        out = _apply_all(data, [(m, e.replace) for e, m in planned], author, date)
    except EditError as exc:
        by_para = {str(m.para): e.id for e, m in planned}
        named = {by_para.get(k, k): v for k, v in exc.problems.items()}
        raise EditError("; ".join(f"{k}: {v}" for k, v in named.items()), named) from exc
    return out, [m for _, m in planned]


def _cased(found: str, new: str) -> str:
    if found.isupper() and len(found) > 1:
        return new.upper()
    if found.islower():
        return new.lower()
    if found[:1].isupper() and new[:1].islower():
        return new[:1].upper() + new[1:]
    return new


def rename_matches(data: bytes, old: str, case_sensitive: bool = True) -> list[Match]:
    """Whole-word occurrences of ``old`` (whitespace-tolerant), document order."""
    target = _nq(old)
    if not target:
        raise EditError("nothing to rename: the old name is empty", {"rename": "empty name"})
    pat = re.compile(
        r"(?<!\w)" + re.escape(target).replace(r"\ ", " ") + r"(?!\w)",
        0 if case_sensitive else re.IGNORECASE,
    )
    out = []
    for p in _Doc(_read(data)).all():
        norm, where = _norm(p.text)
        for m in pat.finditer(norm):
            start, end = where[m.start()], where[m.end() - 1] + 1
            out.append(Match(p.ordinal, start, end, p.text[start:end]))
    return out


def rename(
    data: bytes,
    old: str,
    new: str,
    case_sensitive: bool = True,
    author: str = AUTHOR,
    date: str | None = None,
) -> tuple[bytes, list[Match], list[tuple[Match, str]]]:
    """Every whole-word occurrence of ``old`` replaced by ``new`` as tracked revisions.

    Case-sensitive by default, so a name that is also a common word ("Will")
    leaves the word alone; with ``case_sensitive=False`` the case of each
    occurrence is carried over to the new name. Occurrences that cannot be
    edited safely (next to a note mark, inside a field) are left as they are
    and returned with the reason, for the writer to change by hand.
    """
    found = rename_matches(data, old, case_sensitive)
    if not found:
        raise EditError(f"{old!r} does not appear in the document", {"rename": "not found"})
    planned = [(m, new if case_sensitive else _cased(m.text, new)) for m in found]
    skipped: list[tuple[Match, str]] = []
    out = _apply_all(data, planned, author, date, skipped)
    gone = {(m.para, m.start) for m, _ in skipped}
    return out, [m for m in found if (m.para, m.start) not in gone], skipped
