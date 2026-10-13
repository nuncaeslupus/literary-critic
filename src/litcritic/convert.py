"""Stopgap conversion of non-Word manuscripts to a minimal ``.docx`` (spec D-6).

doc-control reads only Word documents, so ``.txt``, ``.md`` and ``.odt`` files are
turned into a bare ``.docx`` copy that doc-control can read; the writer's file is
never changed. Each format has a small reader (``read_txt``, ``read_md``,
``read_odt``) whose paragraphs are written out one Word paragraph per source
paragraph, with heading level (built-in ``Heading N`` styles), centring, page break
before, paragraph style name, blank lines as empty paragraphs, and, where the
source knows its pages (``.odt`` soft page breaks), a rendered page mark where each
page starts. Plain text has no styles, so ``read_txt`` writes the plain-text
heading convention as a heading: a short line set apart by two or more extra blank
lines above it (``TXT_HEADING_BLANKS``) and a blank line below it.

Delete a format's reader, and its row in ``READERS``, as soon as doc-control reads
that format natively. This is the one module allowed to write ``word/`` parts, and
the only one that reads ``.txt``, ``.md`` or ``.odt`` layout.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

from litcritic.ingest import Draft, IngestError, Para, _collect, clean

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


# --- plain text and Markdown ------------------------------------------------

TXT_HEADING_BLANKS = 2  # extra blank lines above a plain-text heading
TXT_HEADING_WORDS = 12
TXT_NOT_HEADING = re.compile(r"[,;:]$|^[\u2014\u2013«\"“]")


def _txt_headings(paras: list[Para], wrapped: bool) -> list[Para]:
    """Mark plain text's heading convention as heading level 1.

    TODO: remove when doc-control's ``chapter_blank_lines`` (passed for ``.txt`` in
    the novel profile) also takes a numeral with a long title line under it and no
    blank line between ("-XIV-" then a 9-word title in the corpus): hard-wrapped text
    writes no empty paragraph for a single blank line, so doc-control sees no blank
    below the numeral.

    A heading in a plain-text manuscript is a short line with a wider gap above it
    than paragraphs have, and a blank line below it. ``blank_before`` already counts
    only the extra blank lines when paragraphs are blank-line separated (``wrapped``).
    """
    below = 0 if wrapped else 1
    for k, p in enumerate(paras):
        nxt = paras[k + 1] if k + 1 < len(paras) else None
        if (
            k > 0
            and p.blank_before >= TXT_HEADING_BLANKS
            and (nxt is None or nxt.blank_before >= below)
            and len(p.text.split()) <= TXT_HEADING_WORDS
            and not TXT_NOT_HEADING.search(p.text)
        ):
            p.heading = 1
    return paras


def _decode(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    if b"\x00" in data[:4096]:
        raise IngestError("text file looks like UTF-16 without a BOM; save it as UTF-8")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise IngestError("unknown text encoding (use UTF-8)")


def read_txt(data: bytes) -> Draft:
    """Blank-line separated blocks when lines are hard-wrapped, else one paragraph per line."""
    lines = _decode(data).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks = [b.strip("\n") for b in re.split(r"\n[ \t]*\n", "\n".join(lines)) if b.strip()]
    multi = [b for b in blocks if "\n" in b]
    # Lines that a wrap cut (every line of a block but its last) sit near a fixed width.
    cut = sorted(len(x) for b in multi for x in b.split("\n")[:-1])
    wrapped = (
        len(blocks) > 1
        and len(multi) >= 0.2 * len(blocks)
        and bool(cut)
        and cut[len(cut) // 2] >= 40
        and cut[int(0.9 * (len(cut) - 1))] <= 100
    )
    if not wrapped:
        return Draft(_txt_headings(_collect([Para(line) for line in lines]), False), "txt")
    # Hard-wrapped: one blank line separates paragraphs; extra blank lines are spacing.
    out: list[Para] = []
    block: list[str] = []
    blanks = 0
    for line in [*lines, ""]:
        if line.strip():
            block.append(line)
            continue
        if block:
            p = Para(clean(" ".join(block)), blank_before=max(0, blanks - 1) if out else blanks)
            out.append(p)
            block, blanks = [], 0
        blanks += 1
    return Draft(_txt_headings(out, True), "txt", notes=["hard-wrapped blocks"])


MD_EMPHASIS = re.compile(r"(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1")


def read_md(data: bytes) -> Draft:
    text = _decode(data).replace("\r\n", "\n")
    raw: list[Para] = []
    for block in re.split(r"\n[ \t]*\n", text):
        block = block.strip("\n")
        if not block.strip():
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", block.split("\n", 1)[0])
        if m:
            raw.append(Para(m.group(2).rstrip("#").strip(), heading=len(m.group(1))))
            if "\n" not in block:
                continue
            block = block.split("\n", 1)[1]
        # Hide escaped characters from the emphasis pass, then restore them literally.
        line = re.sub(
            r"\\([\\`*_{}\[\]()#+.!-])", lambda m: chr(0xE000 + ord(m.group(1))), block
        ).replace("\n", " ")
        if not re.fullmatch(r"[\s*_#~-]+", line):  # keep scene-break lines like "* * *"
            line = MD_EMPHASIS.sub(r"\2", line)
        raw.append(Para(re.sub("[\ue000-\ue0ff]", lambda m: chr(ord(m.group()) - 0xE000), line)))
    return Draft(_collect(raw), "md")


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


READERS: dict[str, Callable[[bytes], Draft]] = {".txt": read_txt, ".md": read_md, ".odt": read_odt}


def source(path: Path, data: bytes | None = None) -> Draft:
    """The paragraphs and layout facts of a ``.txt``, ``.md`` or ``.odt`` manuscript."""
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
    """The ``.docx`` bytes for a ``.txt``, ``.md`` or ``.odt`` manuscript."""
    return draft_to_docx(source(path, data))
