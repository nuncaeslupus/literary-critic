"""Stopgap conversion of non-Word manuscripts to a minimal ``.docx`` (spec D-6).

doc-control reads ``.docx``, ``.txt`` and ``.md`` itself, but not ``.odt``: an
``.odt`` file is turned into a bare ``.docx`` copy that doc-control can read; the
writer's file is never changed. ``read_odt`` reads its paragraphs, which are written
out one Word paragraph per source paragraph, with heading level (built-in
``Heading N`` styles), centring, page break before, paragraph style name, blank
lines as empty paragraphs, and, where the source knows its pages (soft page
breaks), a rendered page mark where each page starts. ``draft_to_docx`` also
writes paragraphs held in memory, with their layout facts, for structure detection
(:func:`litcritic.structure.detect`).

Delete a format's reader, and its row in ``READERS``, as soon as doc-control reads
that format natively. This is the one module allowed to write ``word/`` parts, and
the only one that reads ``.odt`` layout.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

from litcritic import dc
from litcritic.ingest import Draft, IngestError, Para, _collect

TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
STYLE = "{urn:oasis:names:tc:opendocument:xmlns:style:1.0}"
FO = "{urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0}"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
WML = "application/vnd.openxmlformats-officedocument.wordprocessingml"

CONTENT_TYPES = (
    f'{XML_HEAD}<Types xmlns="{CT_NS}">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    f'<Override PartName="/word/document.xml" ContentType="{WML}.document.main+xml"/>'
    f'<Override PartName="/word/styles.xml" ContentType="{WML}.styles+xml"/>'
    "</Types>"
)
ROOT_RELS = (
    f'{XML_HEAD}<Relationships xmlns="{REL_NS}">'
    f'<Relationship Id="rId1" Type="{R_NS}/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)
DOC_RELS = (
    f'{XML_HEAD}<Relationships xmlns="{REL_NS}">'
    f'<Relationship Id="rId1" Type="{R_NS}/styles" Target="styles.xml"/>'
    "</Relationships>"
)


def _style_ids(draft: Draft) -> dict[str, str]:
    """A Word style id for each paragraph style name the draft uses (headings aside)."""
    names = sorted({p.style for p in draft.paragraphs if p.style and not p.heading})
    return {name: f"LcStyle{k}" for k, name in enumerate(names, 1)}


def _styles(custom: dict[str, str] | None = None) -> str:
    out = [
        f'{XML_HEAD}<w:styles xmlns:w="{W_NS}">',
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/></w:style>',
    ]
    for level in range(1, 10):
        out.append(
            f'<w:style w:type="paragraph" w:styleId="Heading{level}">'
            f'<w:name w:val="heading {level}"/><w:basedOn w:val="Normal"/>'
            '<w:next w:val="Normal"/><w:qFormat/>'
            f'<w:pPr><w:keepNext/><w:outlineLvl w:val="{level - 1}"/></w:pPr></w:style>'
        )
    for name, sid in (custom or {}).items():
        out.append(
            f'<w:style w:type="paragraph" w:customStyle="1" w:styleId="{sid}">'
            f"<w:name w:val={quoteattr(name)}/>"
            '<w:basedOn w:val="Normal"/></w:style>'
        )
    out.append("</w:styles>")
    return "".join(out)


def _paragraph(p: Para, new_pages: int = 0, style_id: str = "") -> str:
    props = ""
    if p.heading:
        props += f'<w:pStyle w:val="Heading{min(max(p.heading, 1), 9)}"/>'
    elif style_id:
        props += f'<w:pStyle w:val="{style_id}"/>'
    if p.page_break_before:
        props += "<w:pageBreakBefore/>"
    if p.centered:
        props += '<w:jc w:val="center"/>'
    ppr = f"<w:pPr>{props}</w:pPr>" if props else ""
    marks = "<w:r><w:lastRenderedPageBreak/></w:r>" * new_pages
    return f'<w:p>{ppr}{marks}<w:r><w:t xml:space="preserve">{escape(p.text)}</w:t></w:r></w:p>'


def draft_to_docx(draft: Draft) -> bytes:
    """A minimal ``.docx`` holding ``draft``'s paragraphs and layout facts."""
    body: list[str] = []
    page = 1
    custom = _style_ids(draft)
    for p in draft.paragraphs:
        body.extend("<w:p/>" for _ in range(p.blank_before))
        new_pages = max(0, p.page - page) if draft.pages_known else 0
        page += new_pages
        body.append(_paragraph(p, new_pages, "" if p.heading else custom.get(p.style, "")))
    document = (
        f'{XML_HEAD}<w:document xmlns:w="{W_NS}"><w:body>{"".join(body)}</w:body></w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", ROOT_RELS)
        zf.writestr("word/document.xml", document)
        zf.writestr("word/styles.xml", _styles(custom))
        zf.writestr("word/_rels/document.xml.rels", DOC_RELS)
    return buf.getvalue()


# --- plain text, one paragraph per line ---------------------------------------


def txt_lines_docx(data: bytes) -> bytes:
    """A ``.txt`` as a ``.docx`` with one paragraph per line, empty lines as empty
    paragraphs: doc-control's ``lines`` mode, which it picks by itself only when no
    empty line sits between two lines of text (verse has them between stanzas).

    Delete it once doc-control takes the reading mode in the request. Decoding is
    doc-control's.
    """
    try:
        text = dc.decode_text(data)
    except ValueError as exc:
        raise IngestError(f"not a readable .txt file: {exc}") from exc
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # the final line end closes the last line
    return draft_to_docx(Draft([Para(line) for line in lines], "txt"))


# --- odt --------------------------------------------------------------------


def _odt_centred(zf: zipfile.ZipFile, content: ET.Element) -> dict[str, bool]:
    styles: dict[str, tuple[str, bool | None]] = {}
    roots = [ET.fromstring(zf.read("styles.xml"))] if "styles.xml" in zf.namelist() else []
    roots.append(content)  # the body's automatic styles win over same-named ones in styles.xml
    for root in roots:
        for st in root.iter(f"{STYLE}style"):
            if st.get(f"{STYLE}family", "paragraph") != "paragraph":
                continue
            props = st.find(f"{STYLE}paragraph-properties")
            align = props.get(f"{FO}text-align") if props is not None else None
            centred = align == "center" if align else None
            styles[st.get(f"{STYLE}name", "")] = (st.get(f"{STYLE}parent-style-name", ""), centred)

    def resolve(name: str, depth: int = 0) -> bool:
        parent, centred = styles.get(name, ("", None))
        if centred is None and parent and depth < 20:
            return resolve(parent, depth + 1)
        return bool(centred)

    return {name: resolve(name) for name in styles}


def read_odt(data: bytes) -> Draft:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        root = ET.fromstring(zf.read("content.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise IngestError(f"not a readable .odt: {exc}") from exc
    centred = _odt_centred(zf, root)
    body = root.find(f"{OFFICE}body/{OFFICE}text")
    if body is None:
        raise IngestError("document has no text body")
    state = {"page": 1, "soft": False}
    raw: list[Para] = []
    skip = {f"{TEXT}note", f"{OFFICE}annotation", f"{TEXT}tracked-changes", f"{TEXT}sequence-decls"}

    def para(p: ET.Element) -> Para:
        style = p.get(f"{TEXT}style-name", "")
        out = Para("", page=state["page"], style=style, centered=centred.get(style, False))
        if p.tag == f"{TEXT}h":
            out.heading = int(p.get(f"{TEXT}outline-level", "1"))
        parts: list[str] = [p.text or ""]

        def walk(el: ET.Element) -> None:
            for ch in el:
                if ch.tag in skip:
                    pass
                elif ch.tag == f"{TEXT}s":
                    parts.append(" " * int(ch.get(f"{TEXT}c", "1")))
                elif ch.tag in (f"{TEXT}tab", f"{TEXT}line-break"):
                    parts.append(" ")
                elif ch.tag == f"{TEXT}soft-page-break":
                    state["page"] += 1
                    state["soft"] = True
                    if not "".join(parts).strip():
                        out.page = state["page"]
                else:
                    if ch.text:
                        parts.append(ch.text)
                    walk(ch)
                if ch.tail:
                    parts.append(ch.tail)

        walk(p)
        out.text = "".join(parts)
        return out

    def blocks(el: ET.Element) -> None:
        for ch in el:
            if ch.tag in (f"{TEXT}p", f"{TEXT}h"):
                raw.append(para(ch))
            elif ch.tag == f"{TEXT}soft-page-break":
                state["page"] += 1
                state["soft"] = True
            elif ch.tag not in skip:
                blocks(ch)

    blocks(body)
    draft = Draft(_collect(raw), "odt", pages_known=bool(state["soft"]))
    if not draft.pages_known:
        for p in draft.paragraphs:
            p.page = 0
    return draft


READERS: dict[str, Callable[[bytes], Draft]] = {".odt": read_odt}


def source(path: Path, data: bytes | None = None) -> Draft:
    """The paragraphs and layout facts of an ``.odt`` manuscript."""
    suffix = path.suffix.lower()
    if suffix not in READERS:
        raise IngestError(f"cannot convert {suffix!r} to .docx (use {', '.join(READERS)})")
    try:
        return READERS[suffix](path.read_bytes() if data is None else data)
    except (ET.ParseError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        if isinstance(exc, IngestError):
            raise
        raise IngestError(f"not a readable {suffix} file: {exc}") from exc


def to_docx(path: Path, data: bytes | None = None) -> bytes:
    """The ``.docx`` bytes for an ``.odt`` manuscript."""
    return draft_to_docx(source(path, data))
