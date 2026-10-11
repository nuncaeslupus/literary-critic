"""Build .docx/.odt test fixtures from paragraphs, with the markup quirks real files have.

Each paragraph is split into several runs at random points; some get a tracked
deletion, a field code, a soft hyphen or a footnote reference that must not
reach the text. Headings use a style that only declares its outline level in
styles.xml. Page breaks are rendered before every heading.
"""

from __future__ import annotations

import io
import random
import zipfile
from xml.sax.saxutils import escape

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/xml"/></Types>'
)
STYLES = (
    f'<w:styles xmlns:w="{W_NS}">'
    '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Chap"><w:name w:val="Chapter title"/>'
    '<w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:outlineLvl w:val="0"/></w:pPr>'
    "</w:style></w:styles>"
)


def _runs(text: str, rng: random.Random) -> str:
    cuts = sorted(rng.sample(range(1, len(text)), k=min(3, len(text) - 1))) if len(text) > 4 else []
    pieces = [text[a:b] for a, b in zip([0, *cuts], [*cuts, len(text)], strict=True)]
    out = []
    for i, piece in enumerate(pieces):
        out.append(f'<w:r><w:t xml:space="preserve">{escape(piece)}</w:t></w:r>')
        roll = rng.random()
        if i == 0 and roll < 0.1:
            out.append("<w:del><w:r><w:delText>borrado </w:delText></w:r></w:del>")
        elif i == 0 and roll < 0.2:
            out.append("<w:r><w:instrText> PAGE </w:instrText></w:r>")
        elif i == 0 and roll < 0.3:
            out.append("<w:r><w:softHyphen/></w:r>")
        elif i == 0 and roll < 0.35:
            out.append('<w:r><w:footnoteReference w:id="1"/></w:r>')
    return "".join(out)


def docx(paragraphs: list[tuple[str, bool]], seed: int = 0) -> bytes:
    """``paragraphs`` are (text, is_heading)."""
    rng = random.Random(seed)
    body = []
    for text, heading in paragraphs:
        if heading:
            body.append(
                '<w:p><w:pPr><w:pStyle w:val="Chap"/><w:pageBreakBefore/></w:pPr>'
                f"<w:r><w:lastRenderedPageBreak/></w:r>{_runs(text, rng)}</w:p>"
            )
            body.append("<w:p/>")  # empty spacer paragraph
        else:
            body.append(f"<w:p>{_runs(text, rng)}</w:p>")
    doc = f'<w:document xmlns:w="{W_NS}"><w:body>{"".join(body)}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", CT)
        zf.writestr("word/document.xml", doc)
        zf.writestr("word/styles.xml", STYLES)
    return buf.getvalue()


ODT_NS = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
    'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"'
)


def odt(paragraphs: list[tuple[str, bool]], seed: int = 0) -> bytes:
    rng = random.Random(seed)
    body = []
    for text, heading in paragraphs:
        words = escape(text).split(" ")
        cut = rng.randrange(len(words))
        inner = " ".join(words[:cut]) + (" " if cut else "")
        if rng.random() < 0.2 and " " in inner:
            inner = inner.replace(" ", "<text:s/>", 1)
        inner += f'<text:span text:style-name="T1">{" ".join(words[cut:])}</text:span>'
        if rng.random() < 0.1:
            inner += "<text:note><text:note-body><text:p>nota</text:p></text:note-body></text:note>"
        if heading:
            body.append(
                "<text:soft-page-break/>"
                f'<text:h text:outline-level="1" text:style-name="Centre">{inner}</text:h>'
            )
        else:
            body.append(f'<text:p text:style-name="Body">{inner}</text:p>')
    content = (
        f"<office:document-content {ODT_NS}><office:automatic-styles>"
        '<style:style style:name="Centre" style:family="paragraph">'
        '<style:paragraph-properties fo:text-align="center"/></style:style>'
        "</office:automatic-styles><office:body><office:text>"
        f"{''.join(body)}</office:text></office:body></office:document-content>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        zf.writestr("content.xml", content)
    return buf.getvalue()
