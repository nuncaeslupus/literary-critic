"""A copy of the writer's .docx with each action as an anchored comment.

The original file is never modified: the copy is written next to the round's
actions. Paragraphs are found by their position among the document's ``w:p``
elements, recorded at ingest time, and the XML is edited as text so every
namespace, attribute and part Word cares about is kept byte for byte. Comments
the writer already had are kept; ours get ids after theirs.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from litcritic import ingest, query, rounds
from litcritic.codex import Codex

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
COMMENTS_PART = "word/comments.xml"
COMMENTS_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
COMMENTS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
AUTHOR = "literary-critic"
W_PREFIX = re.compile(
    r'xmlns:(\w+)="http://schemas\.openxmlformats\.org/wordprocessingml/2006/main"'
)


class DocxError(Exception):
    """The comments copy cannot be made."""


def _paragraph_spans(xml: str) -> tuple[str, list[tuple[int, int, bool]]]:
    """The main-namespace prefix, and (content start, content end, empty) per w:p in order."""
    m = W_PREFIX.search(xml)
    if not m:
        raise DocxError("document.xml has no prefixed WordprocessingML namespace")
    w = m.group(1)
    tag = re.compile(rf"<{w}:p(?=[\s>/])[^>]*?(/?)>|</{w}:p>")
    spans: list[tuple[int, int, bool]] = []
    stack: list[int] = []
    for t in tag.finditer(xml):
        if t.group(0).startswith("</"):
            k = stack.pop()
            spans[k] = (spans[k][0], t.start(), False)
        elif t.group(1) == "/":
            spans.append((t.end(), t.end(), True))  # empty <w:p/>
        else:
            spans.append((t.end(), -1, False))
            stack.append(len(spans) - 1)
    return w, spans


def _comment_xml(cid: int, text_lines: list[str], date: str, w: str = "w") -> str:
    paras = "".join(
        f'<{w}:p><{w}:r><{w}:t xml:space="preserve">{escape(line)}</{w}:t></{w}:r></{w}:p>'
        for line in text_lines
    )
    return (
        f'<{w}:comment {w}:id="{cid}" {w}:author="{AUTHOR}" {w}:initials="LC" {w}:date="{date}">'
        f"{paras}</{w}:comment>"
    )


def add_comments(data: bytes, targets: dict[int, list[str]]) -> bytes:
    """Return a new .docx with comments on the given paragraphs (by w:p ordinal).

    ``targets`` maps a paragraph ordinal (as counted by ingest) to the
    comment's lines.
    """
    src = zipfile.ZipFile(io.BytesIO(data))
    names = src.namelist()
    xml = src.read("word/document.xml").decode("utf-8")
    w, spans = _paragraph_spans(xml)
    expected = sum(1 for _ in ET.fromstring(xml.encode("utf-8")).iter(f"{{{W_NS}}}p"))
    if len(spans) != expected:
        raise DocxError("could not map the document's paragraphs safely; no comments added")
    existing = src.read(COMMENTS_PART).decode("utf-8") if COMMENTS_PART in names else ""
    if existing:
        existing = re.sub(r"<(\w+):comments\b([^>]*)/>", r"<\1:comments\2></\1:comments>", existing)
        if not re.search(r"</\w+:comments>", existing):
            raise DocxError("the document's comments part is not in a form we can extend")
    cm = W_PREFIX.search(existing)
    cw = cm.group(1) if cm else "w"
    ids = [int(x) for x in re.findall(r'<\w+:comment\b[^>]*\b\w+:id="(\d+)"', existing)]
    next_id = max(ids, default=-1) + 1
    date = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    inserts: list[tuple[int, str]] = []
    comments: list[str] = []
    for ordinal in sorted(targets):
        if ordinal >= len(spans):
            raise DocxError(f"paragraph {ordinal} is not in the document")
        start, end, empty = spans[ordinal]
        if empty:
            raise DocxError(f"paragraph {ordinal} is empty; nothing to comment on")
        cid = next_id
        next_id += 1
        content = xml[start:end]
        ppr = re.match(rf"\s*<{w}:pPr\b[^>]*/>", content) or re.match(
            rf"\s*<{w}:pPr\b[^>]*>.*?</{w}:pPr>", content, re.S
        )
        inserts.append(
            (start + (ppr.end() if ppr else 0), f'<{w}:commentRangeStart {w}:id="{cid}"/>')
        )
        inserts.append(
            (
                end,
                f'<{w}:commentRangeEnd {w}:id="{cid}"/>'
                f'<{w}:r><{w}:commentReference {w}:id="{cid}"/></{w}:r>',
            )
        )
        comments.append(_comment_xml(cid, targets[ordinal], date, cw if existing else "w"))
    for pos, text in sorted(inserts, key=lambda t: t[0], reverse=True):
        xml = xml[:pos] + text + xml[pos:]
    if existing:
        closing = list(re.finditer(r"</\w+:comments>", existing))[-1]
        comments_xml = existing[: closing.start()] + "".join(comments) + existing[closing.start() :]
    else:
        comments_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:comments xmlns:w="{W_NS}">{"".join(comments)}</w:comments>'
        )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            name = info.filename
            if name == "word/document.xml":
                dst.writestr(info, xml.encode("utf-8"))
            elif name == COMMENTS_PART:
                dst.writestr(info, comments_xml.encode("utf-8"))
            elif name == "[Content_Types].xml" and not existing:
                dst.writestr(
                    info, _with_content_type(src.read(name).decode("utf-8")).encode("utf-8")
                )
            elif name == "word/_rels/document.xml.rels" and not existing:
                dst.writestr(
                    info, _with_relationship(src.read(name).decode("utf-8")).encode("utf-8")
                )
            else:
                dst.writestr(info, src.read(name))
        if not existing:
            dst.writestr(COMMENTS_PART, comments_xml.encode("utf-8"))
            if "word/_rels/document.xml.rels" not in names:
                dst.writestr("word/_rels/document.xml.rels", _with_relationship(""))
            if "[Content_Types].xml" not in names:
                dst.writestr("[Content_Types].xml", _with_content_type(""))
    return out.getvalue()


def _with_content_type(xml: str) -> str:
    override = f'<Override PartName="/{COMMENTS_PART}" ContentType="{COMMENTS_TYPE}"/>'
    if not xml:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f"{override}</Types>"
        )
    return xml if COMMENTS_PART in xml else xml.replace("</Types>", override + "</Types>")


def _with_relationship(xml: str) -> str:
    rel = f'<Relationship Id="rIdLitcriticComments" Type="{COMMENTS_REL}" Target="comments.xml"/>'
    if not xml:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{rel}</Relationships>"
        )
    return xml.replace("</Relationships>", rel + "</Relationships>")


def comment_lines(action: dict[str, Any], lang: str) -> list[str]:
    t = rounds.TEXT.get(lang, rounds.TEXT["en"])
    return [
        f"[{action['id']}] {action['what']}",
        f"{t['why']}: {action['why']}",
        f"{t['options']}: " + " / ".join(action["options"]),
    ]


def build(ws_root: Path, version: str | None = None) -> tuple[Path, int]:
    """Write ``revisions/round-NN/<draft>-comments.docx`` for the latest round.

    Comments go on the Codex's synced draft, where the issues' spans point;
    actions whose passage is gone, or that the writer already closed, get none.
    """
    round_dir = rounds.latest_round(ws_root)
    cx = Codex(ws_root)
    version = cx.draft
    snapshot = ws_root / "manuscript" / f"{version}.docx"
    if not snapshot.is_file():
        raise DocxError(f"draft {version} is not a .docx; comments need a Word file")
    data = snapshot.read_bytes()
    try:
        draft = ingest.read_docx(data)
        ix = query.load(ws_root, version)
    except (ingest.IngestError, zipfile.BadZipFile) as exc:
        raise DocxError(str(exc)) from exc
    if [p.text for p in draft.paragraphs] != ix.paragraphs:
        raise DocxError(f"{snapshot.name} no longer matches text/{version}.txt; re-ingest it")
    lang = rounds.language(ws_root)
    index_of = {a: i for i, a in enumerate(ix.anchors)}
    targets: dict[int, list[str]] = {}
    for action in rounds.round_actions(ws_root, round_dir, cx):
        if action["status"] not in ("pending", "accepted") or not action["where"]:
            continue
        anchor = action["where"]["anchor"]
        if anchor not in index_of:
            raise DocxError(f"{action['id']}: {anchor} is not in {version}")
        ordinal = draft.paragraphs[index_of[anchor]].src
        targets[ordinal] = [*targets.get(ordinal, []), *comment_lines(action, lang)]
    out = round_dir / f"{version}-comments.docx"
    out.write_bytes(add_comments(data, targets))
    return out, len(targets)
