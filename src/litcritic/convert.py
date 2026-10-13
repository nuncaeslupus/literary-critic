"""Paragraphs held in memory written to a minimal ``.docx``.

doc-control reads every manuscript format itself (``.docx``, ``.odt``, ``.txt``,
``.md``). What still needs a file is a draft that exists only in memory, with its
layout facts, for structure detection (:func:`litcritic.structure.detect`) and
test fixtures: ``draft_to_docx`` writes one Word paragraph per paragraph, with
heading level (built-in ``Heading N`` styles), centring, page break before,
paragraph style name, blank lines as empty paragraphs and, where pages are
known, a rendered page mark where each page starts. This is the one module
allowed to write ``word/`` parts.
"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape, quoteattr

from litcritic.ingest import Draft, Para

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
