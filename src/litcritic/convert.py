"""Stopgap conversion of non-Word manuscripts to a minimal ``.docx`` (spec D-6).

doc-control reads only Word documents, so ``.txt``, ``.md`` and ``.odt`` files are
turned into a bare ``.docx`` copy that doc-control can read; the writer's file is
never changed. The paragraphs come from the readers in :mod:`litcritic.ingest`; this
module only writes them out, one Word paragraph per source paragraph, with heading
level (built-in ``Heading N`` styles), centring, page break before, and blank lines
as empty paragraphs.

Each format has its own small function (``txt_to_docx``, ``md_to_docx``,
``odt_to_docx``). Delete a function, and its row in ``CONVERTERS``, as soon as
doc-control reads that format natively. This is the one module allowed to write
``word/`` parts.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from litcritic import ingest
from litcritic.ingest import Draft, IngestError, Para

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


def _styles() -> str:
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
    out.append("</w:styles>")
    return "".join(out)


def _paragraph(p: Para) -> str:
    props = ""
    if p.heading:
        props += f'<w:pStyle w:val="Heading{min(max(p.heading, 1), 9)}"/>'
    if p.page_break_before:
        props += "<w:pageBreakBefore/>"
    if p.centered:
        props += '<w:jc w:val="center"/>'
    ppr = f"<w:pPr>{props}</w:pPr>" if props else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(p.text)}</w:t></w:r></w:p>'


def _docx(draft: Draft) -> bytes:
    body: list[str] = []
    for p in draft.paragraphs:
        body.extend("<w:p/>" for _ in range(p.blank_before))
        body.append(_paragraph(p))
    document = (
        f'{XML_HEAD}<w:document xmlns:w="{W_NS}"><w:body>{"".join(body)}</w:body></w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", ROOT_RELS)
        zf.writestr("word/document.xml", document)
        zf.writestr("word/styles.xml", _styles())
        zf.writestr("word/_rels/document.xml.rels", DOC_RELS)
    return buf.getvalue()


def txt_to_docx(data: bytes) -> bytes:
    return _docx(ingest.read_txt(data))


def md_to_docx(data: bytes) -> bytes:
    return _docx(ingest.read_md(data))


def odt_to_docx(data: bytes) -> bytes:
    return _docx(ingest.read_odt(data))


CONVERTERS = {".txt": txt_to_docx, ".md": md_to_docx, ".odt": odt_to_docx}


def to_docx(path: Path, data: bytes | None = None) -> bytes:
    """The ``.docx`` bytes for a ``.txt``, ``.md`` or ``.odt`` manuscript."""
    suffix = path.suffix.lower()
    if suffix not in CONVERTERS:
        raise IngestError(f"cannot convert {suffix!r} to .docx (use {', '.join(CONVERTERS)})")
    return CONVERTERS[suffix](path.read_bytes() if data is None else data)
