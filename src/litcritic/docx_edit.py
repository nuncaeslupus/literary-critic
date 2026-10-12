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


def _prefix(xml: str) -> str:
    m = W_PREFIX.search(xml)
    if not m:
        raise EditError("document.xml has no prefixed WordprocessingML namespace")
    return m.group(1)


def _paragraph_spans(xml: str, w: str) -> list[tuple[int, int]]:
    """(content start, content end) of every w:p, in ingest's order (pre-order)."""
    tag = re.compile(rf"<{w}:p(?=[\s>/])[^>]*?(/?)>|</{w}:p>")
    spans: list[tuple[int, int]] = []
    stack: list[int] = []
    for t in tag.finditer(xml):
        if t.group(0).startswith("</"):
            k = stack.pop()
            spans[k] = (spans[k][0], t.start())
        elif t.group(1) == "/":
            spans.append((t.end(), t.end()))
        else:
            spans.append((t.end(), -1))
            stack.append(len(spans) - 1)
    return spans


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


def _paragraphs(xml: str) -> list[_Para]:
    """Every w:p with its top-level runs and a character map of its visible text."""
    w = _prefix(xml)
    plain = re.compile(
        rf"\s*(<{w}:rPr\b[^>]*/>|<{w}:rPr\b[^>]*>.*?</{w}:rPr>)?\s*"
        rf"(?:<{w}:t(?:\s[^>]*)?>([^<]*)</{w}:t>|<{w}:t\b[^>]*/>)?\s*",
        re.S,
    )
    tags = re.compile(rf"<(/?){w}:(\w+)\b[^>]*?(/?)>")
    spans = _paragraph_spans(xml, w)
    paras = []
    for ordinal, (start, end) in enumerate(spans):
        para = _Para(ordinal, start, end)
        nested = [(a, b) for a, b in spans if start < a and b <= end]
        open_: list[str] = []
        field = 0  # depth inside complex fields (fldChar begin .. end)
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
                    field += {"begin": 1, "end": -1}.get(fc.group(1), 0)
                    field = max(field, 0)
                text = unescape(m.group(2) or "") if m else _visible(inner, w)
                if any(n in HIDDEN for n in open_):
                    text = ""
                run = _Run(
                    t.start(), r_end, (m.group(1) or "") if m else "", text, m is not None, locked
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
                        open_.reverse()
                        open_.remove(name)
                        open_.reverse()
                elif not selfclose:
                    open_.append(name)
            pos = t.end()
        paras.append(para)
    return paras


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
    found = []
    for p in paras:
        norm, where = _norm(p.text)
        for m in re.finditer(re.escape(quote), norm):
            before, after = norm[: m.start()].rstrip(), norm[m.end() :].lstrip()
            if prefix and not (before.endswith(prefix) or prefix.endswith(before)):
                continue
            if suffix and not (after.startswith(suffix) or suffix.startswith(after)):
                continue
            start, end = where[m.start()], where[m.end() - 1] + 1
            found.append(Match(p.ordinal, start, end, p.text[start:end]))
    return found


# -- writing -----------------------------------------------------------------


def _revision_ids(xml: str) -> int:
    ids = [int(x) for x in re.findall(r'\b\w+:id="(\d+)"', xml)]
    return max(ids, default=0) + 1


def _run_xml(w: str, rpr: str, text: str, deleted: bool = False) -> str:
    tag = "delText" if deleted else "t"
    return f'<{w}:r>{rpr}<{w}:{tag} xml:space="preserve">{escape(text)}</{w}:{tag}></{w}:r>'


def _apply_one(
    xml: str, para: _Para, match: Match, replace: str, ids: list[int], author: str, date: str
) -> str:
    w = _prefix(xml)
    affected = sorted({para.chars[i][0] for i in range(match.start, match.end)})
    for i in range(match.start, match.end):
        if para.chars[i][1] < 0:
            raise EditError("the passage crosses a tab, break or field; edit it by hand")
    runs = [para.runs[k] for k in affected]
    if any(not r.plain or r.in_revision for r in runs):
        raise EditError("the passage crosses formatting Word marks specially; edit it by hand")
    lo, hi = runs[0].start, runs[-1].end
    if any(lo < h < hi for h in para.hazards):
        raise EditError("the passage crosses a field or an existing tracked change")
    pieces: list[tuple[int, int, str]] = []
    for n, k in enumerate(affected):
        r = para.runs[k]
        offs = [para.chars[i][1] for i in range(match.start, match.end) if para.chars[i][0] == k]
        a, b = min(offs), max(offs) + 1
        out = ""
        if a > 0:
            out += _run_xml(w, r.rpr, r.text[:a])
        rid = ids[0]
        ids[0] += 1
        out += (
            f'<{w}:del {w}:id="{rid}" {w}:author="{escape(author)}" {w}:date="{date}">'
            f"{_run_xml(w, r.rpr, r.text[a:b], deleted=True)}</{w}:del>"
        )
        if n == len(affected) - 1 and replace:
            rid = ids[0]
            ids[0] += 1
            out += (
                f'<{w}:ins {w}:id="{rid}" {w}:author="{escape(author)}" {w}:date="{date}">'
                f"{_run_xml(w, runs[0].rpr, replace)}</{w}:ins>"
            )
        if b < len(r.text):
            out += _run_xml(w, r.rpr, r.text[b:])
        pieces.append((r.start, r.end, out))
    for start, end, out in reversed(pieces):
        xml = xml[:start] + out + xml[end:]
    return xml


def _repack(data: bytes, xml: str) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            payload = xml.encode("utf-8") if info.filename == DOC else src.read(info.filename)
            dst.writestr(info, payload)
    return out.getvalue()


def _read(data: bytes) -> str:
    try:
        return zipfile.ZipFile(io.BytesIO(data)).read(DOC).decode("utf-8")
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
        raise EditError(f"not a readable .docx: {exc}") from exc


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# -- public ------------------------------------------------------------------


def texts(data: bytes) -> list[str]:
    """Visible text of every w:p, by ordinal (fields and deletions excluded)."""
    return [p.text for p in _paragraphs(_read(data))]


def find(data: bytes, quote: str, prefix: str = "", suffix: str = "") -> list[Match]:
    return _matches(_paragraphs(_read(data)), Edit("find", quote, "", prefix, suffix))


def apply(
    data: bytes, edits: list[Edit], author: str = AUTHOR, date: str | None = None
) -> tuple[bytes, list[Match]]:
    """All edits as tracked revisions, or none: raises EditError naming each failure."""
    xml = _read(data)
    paras = _paragraphs(xml)
    problems: dict[str, str] = {}
    planned: list[tuple[Edit, Match]] = []
    for e in edits:
        found = _matches(paras, e)
        if len(found) != 1:
            problems[e.id] = "not found" if not found else f"found {len(found)} times; add context"
            continue
        planned.append((e, found[0]))
    spots = sorted((m.para, m.start, m.end) for _, m in planned)
    for (p1, _, e1), (p2, s2, _) in pairwise(spots):
        if p1 == p2 and s2 < e1:
            problems["overlap"] = "two edits overlap"
    if problems:
        raise EditError("; ".join(f"{k}: {v}" for k, v in problems.items()), problems)
    ids = [_revision_ids(xml)]
    when = date or _now()
    # Right to left, so earlier offsets stay valid; re-read each paragraph after an edit.
    for e, m in sorted(planned, key=lambda t: (t[1].para, t[1].start), reverse=True):
        para = _paragraphs(xml)[m.para]
        try:
            xml = _apply_one(xml, para, m, e.replace, ids, author, when)
        except EditError as exc:
            raise EditError(f"{e.id}: {exc}", {e.id: str(exc)}) from exc
    return _repack(data, xml), [m for _, m in planned]


def _cased(found: str, new: str) -> str:
    if found.isupper() and len(found) > 1:
        return new.upper()
    if found[:1].isupper() and new[:1].islower():
        return new[:1].upper() + new[1:]
    return new


def rename_matches(data: bytes, old: str, case_sensitive: bool = False) -> list[Match]:
    """Whole-word occurrences of ``old`` (whitespace-tolerant), document order."""
    pat = re.compile(
        r"(?<!\w)" + re.escape(_nq(old)).replace(r"\ ", " ") + r"(?!\w)",
        0 if case_sensitive else re.IGNORECASE,
    )
    out = []
    for p in _paragraphs(_read(data)):
        norm, where = _norm(p.text)
        for m in pat.finditer(norm):
            start, end = where[m.start()], where[m.end() - 1] + 1
            out.append(Match(p.ordinal, start, end, p.text[start:end]))
    return out


def rename(
    data: bytes,
    old: str,
    new: str,
    case_sensitive: bool = False,
    author: str = AUTHOR,
    date: str | None = None,
) -> tuple[bytes, list[Match]]:
    """Every whole-word occurrence of ``old`` replaced by ``new`` as tracked revisions."""
    found = rename_matches(data, old, case_sensitive)
    if not found:
        raise EditError(f"{old!r} does not appear in the document", {"rename": "not found"})
    xml = _read(data)
    ids = [_revision_ids(xml)]
    when = date or _now()
    for m in sorted(found, key=lambda t: (t.para, t.start), reverse=True):
        para = _paragraphs(xml)[m.para]
        try:
            xml = _apply_one(xml, para, m, _cased(m.text, new), ids, author, when)
        except EditError as exc:
            raise EditError(f"paragraph {m.para}: {exc}", {"rename": str(exc)}) from exc
    return _repack(data, xml), found
