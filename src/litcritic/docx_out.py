"""A copy of the writer's .docx with each action as an anchored comment.

The original file is never modified: the copy is written next to the round's
actions. Paragraphs are found by their position among the document's ``w:p``
elements, recorded at ingest time, and the XML is edited as text so every
namespace, attribute and part Word cares about is kept byte for byte. Comments
the writer already had are kept; ours get ids after theirs.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from litcritic import ingest, query, rounds, structure

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
COMMENTS_PART = "word/comments.xml"
COMMENTS_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
COMMENTS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
AUTHOR = "literary-critic"
P_TAG = re.compile(r"<w:p(?=[\s>/])[^>]*?(/?)>|</w:p>")


class DocxError(Exception):
    """The comments copy cannot be made."""


def _paragraph_spans(xml: str) -> list[tuple[int, int, int]]:
    """(start of content, end of content, depth) for every w:p, in document order."""
    spans: list[tuple[int, int, int]] = []
    stack: list[int] = []
    for m in P_TAG.finditer(xml):
        if m.group(0).startswith("</"):
            k = stack.pop()
            start, _, depth = spans[k]
            spans[k] = (start, m.start(), depth)
        elif m.group(1) == "/":
            spans.append((m.end(), m.end(), len(stack)))  # empty <w:p/>
        else:
            spans.append((m.end(), -1, len(stack)))
            stack.append(len(spans) - 1)
    return spans


def _comment_xml(cid: int, text_lines: list[str], date: str) -> str:
    paras = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>'
        for line in text_lines
    )
    return (
        f'<w:comment w:id="{cid}" w:author="{AUTHOR}" w:initials="LC" w:date="{date}">'
        f"{paras}</w:comment>"
    )


def add_comments(data: bytes, targets: dict[int, list[str]]) -> tuple[bytes, dict[int, int]]:
    """Return a new .docx with comments on the given paragraphs (by w:p ordinal).

    ``targets`` maps a paragraph ordinal to the comment's lines. The result also
    maps each new comment id to its ordinal.
    """
    src = zipfile.ZipFile(io.BytesIO(data))
    names = src.namelist()
    xml = src.read("word/document.xml").decode("utf-8")
    spans = _paragraph_spans(xml)
    existing = src.read(COMMENTS_PART).decode("utf-8") if COMMENTS_PART in names else ""
    ids = [int(x) for x in re.findall(r'<w:comment\b[^>]*\bw:id="(\d+)"', existing)]
    next_id = max(ids, default=-1) + 1
    date = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    inserts: list[tuple[int, str]] = []
    comments: list[str] = []
    placed: dict[int, int] = {}
    for ordinal in sorted(targets):
        if ordinal >= len(spans):
            raise DocxError(f"paragraph {ordinal} is not in the document")
        start, end, _ = spans[ordinal]
        cid = next_id
        next_id += 1
        content = xml[start:end]
        ppr = re.match(r"\s*<w:pPr\b.*?</w:pPr>|\s*<w:pPr\b[^>]*/>", content, re.S)
        open_at = start + (ppr.end() if ppr else 0)
        inserts.append((open_at, f'<w:commentRangeStart w:id="{cid}"/>'))
        inserts.append(
            (
                end,
                f'<w:commentRangeEnd w:id="{cid}"/><w:r><w:commentReference w:id="{cid}"/></w:r>',
            )
        )
        comments.append(_comment_xml(cid, targets[ordinal], date))
        placed[cid] = ordinal
    for pos, text in sorted(inserts, key=lambda t: t[0], reverse=True):
        xml = xml[:pos] + text + xml[pos:]
    if existing:
        comments_xml = existing.replace("</w:comments>", "".join(comments) + "</w:comments>")
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
    return out.getvalue(), placed


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
    """Write ``revisions/round-NN/<draft>-comments.docx`` for the latest round."""
    version = version or structure.latest_version(ws_root)
    snapshots = sorted((ws_root / "manuscript").glob(f"{version}.docx"))
    if not snapshots:
        raise DocxError(f"draft {version} is not a .docx; comments need a Word file")
    data = snapshots[0].read_bytes()
    draft = ingest.read_docx(data)
    ix = query.load(ws_root, version)
    if [p.text for p in draft.paragraphs] != ix.paragraphs:
        raise DocxError(f"{snapshots[0].name} no longer matches text/{version}.txt; re-ingest it")
    round_dir = rounds.latest_round(ws_root)
    actions = json.loads((round_dir / "actions.json").read_text(encoding="utf-8"))
    lang = rounds.language(ws_root)
    index_of = {a: i for i, a in enumerate(ix.anchors)}
    targets: dict[int, list[str]] = {}
    for action in actions:
        if action["status"] in ("rejected", "done"):
            continue
        anchor = action["where"]["anchor"]
        i = index_of.get(anchor)
        if i is None:
            i = query.paragraph_range(ix, anchor).start
        ordinal = draft.paragraphs[i].src
        lines = comment_lines(action, lang)
        targets[ordinal] = [*targets.get(ordinal, []), *lines]
    out_bytes, _ = add_comments(data, targets)
    out = round_dir / f"{version}-comments.docx"
    out.write_bytes(out_bytes)
    return out, len(targets)
