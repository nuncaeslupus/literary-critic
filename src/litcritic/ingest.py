"""Ingest a manuscript draft into a workspace.

``.txt``, ``.md``, ``.docx`` and ``.odt`` become normalised text: one paragraph
per line, whitespace collapsed, Unicode NFC. Layout facts that structure
detection and writer locators need (heading level, centred, page, blank lines
before, page break before) go to a sidecar ``vNNN.meta.json``. The original file
is kept as a snapshot ``manuscript/vNNN.<ext>``; ingesting an unchanged file
again is a no-op.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

FORMATS = (".txt", ".md", ".docx", ".odt")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
STYLE = "{urn:oasis:names:tc:opendocument:xmlns:style:1.0}"
FO = "{urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0}"


class IngestError(Exception):
    """The file cannot be read as a manuscript."""


@dataclass
class Para:
    text: str
    heading: int = 0  # outline level, 0 = body text
    centered: bool = False
    page: int = 0  # 1-based page where the paragraph starts; 0 = unknown
    page_break_before: bool = False
    blank_before: int = 0  # empty paragraphs/lines skipped just before this one
    style: str = ""

    def meta(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in ("heading", "centered", "page", "page_break_before", "blank_before", "style"):
            value = getattr(self, key)
            if value:
                out[key] = value
        return out


@dataclass
class Draft:
    paragraphs: list[Para]
    format: str
    pages_known: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(p.text + "\n" for p in self.paragraphs)


def clean(text: str) -> str:
    """NFC, soft hyphens and zero-width characters dropped, whitespace collapsed."""
    text = unicodedata.normalize("NFC", text)
    text = re.sub("[­​‌‍﻿]", "", text)
    return " ".join(text.split())


def _collect(raw: list[Para]) -> list[Para]:
    """Drop empty paragraphs, counting them as ``blank_before`` of the next one."""
    out: list[Para] = []
    blanks = 0
    pending_break = False
    for p in raw:
        p.text = clean(p.text)
        if not p.text:
            blanks += 1
            pending_break = pending_break or p.page_break_before
            continue
        p.blank_before = blanks
        p.page_break_before = p.page_break_before or pending_break
        out.append(p)
        blanks = 0
        pending_break = False
    return out


# --- plain text and Markdown ------------------------------------------------


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise IngestError("unknown text encoding (use UTF-8)")


def read_txt(data: bytes) -> Draft:
    """Blank-line separated blocks when lines are hard-wrapped, else one paragraph per line."""
    lines = _decode(data).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks = [b for b in re.split(r"\n[ \t]*\n", "\n".join(lines)) if b.strip()]
    wrapped = sum(b.strip("\n").count("\n") + 1 for b in blocks) / max(len(blocks), 1) > 1.5
    if not wrapped:
        return Draft(_collect([Para(line) for line in lines]), "txt")
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
    return Draft(out, "txt", notes=["hard-wrapped blocks"])


MD_EMPHASIS = re.compile(r"(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1")


def read_md(data: bytes) -> Draft:
    text = _decode(data).replace("\r\n", "\n")
    raw: list[Para] = []
    for block in re.split(r"\n[ \t]*\n", text):
        block = block.strip("\n")
        if not block.strip():
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", block)
        if m and "\n" not in block:
            raw.append(Para(m.group(2).rstrip("#"), heading=len(m.group(1))))
            continue
        # Hide escaped characters from the emphasis pass, then restore them literally.
        line = re.sub(
            r"\\([\\`*_{}\[\]()#+.!-])", lambda m: chr(0xE000 + ord(m.group(1))), block
        ).replace("\n", " ")
        if not re.fullmatch(r"[\s*_#~-]+", line):  # keep scene-break lines like "* * *"
            line = MD_EMPHASIS.sub(r"\2", line)
        raw.append(Para(re.sub("[\ue000-\ue0ff]", lambda m: chr(ord(m.group()) - 0xE000), line)))
    return Draft(_collect(raw), "md")


# --- docx -------------------------------------------------------------------


def _docx_styles(zf: zipfile.ZipFile) -> dict[str, tuple[str, int, bool]]:
    """styleId -> (name, outline level 1-9 or 0, centred), following basedOn."""
    if "word/styles.xml" not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read("word/styles.xml"))
    raw: dict[str, tuple[str, str, int, bool | None]] = {}
    for st in root.iter(f"{W}style"):
        sid = st.get(f"{W}styleId", "")
        name_el = st.find(f"{W}name")
        name = name_el.get(f"{W}val", sid) if name_el is not None else sid
        based = st.find(f"{W}basedOn")
        lvl = st.find(f"{W}pPr/{W}outlineLvl")
        jc = st.find(f"{W}pPr/{W}jc")
        level = int(lvl.get(f"{W}val", "9")) + 1 if lvl is not None else 0
        centred = jc.get(f"{W}val") == "center" if jc is not None else None
        parent = based.get(f"{W}val", "") if based is not None else ""
        raw[sid] = (name, parent, level if level <= 9 else 0, centred)

    def resolve(sid: str, depth: int = 0) -> tuple[str, int, bool]:
        name, parent, level, centred = raw[sid]
        if parent in raw and depth < 20 and (not level or centred is None):
            _, plevel, pcentred = resolve(parent, depth + 1)
            level = level or plevel
            centred = pcentred if centred is None else centred
        if not level and re.fullmatch(r"(?i)(heading|t[ií]tulo)\s*([1-9])", name.strip()):
            level = int(name.strip()[-1])
        return name, level, bool(centred)

    return {sid: resolve(sid) for sid in raw}


def read_docx(data: bytes) -> Draft:
    try:
        zf = zipfile.ZipFile(_as_file(data))
        root = ET.fromstring(zf.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise IngestError(f"not a readable .docx: {exc}") from exc
    styles = _docx_styles(zf)
    body = root.find(f"{W}body")
    if body is None:
        raise IngestError("document has no body")
    # Word records both explicit breaks and, once laid out, where pages actually
    # fell (lastRenderedPageBreak). Pages are counted from the rendered marks when
    # present, so an explicit break is not counted twice.
    state = {"page": 1, "rendered": _has_rendered_breaks(root), "break_next": False}
    raw: list[Para] = []

    def para(p: ET.Element) -> Para:
        out = Para("", page=state["page"], page_break_before=bool(state["break_next"]))
        state["break_next"] = False
        ppr = p.find(f"{W}pPr")
        if ppr is not None:
            sid_el = ppr.find(f"{W}pStyle")
            sid = sid_el.get(f"{W}val", "") if sid_el is not None else ""
            name, level, centred = styles.get(sid, (sid, 0, False))
            out.style, out.heading, out.centered = name, level, centred
            lvl = ppr.find(f"{W}outlineLvl")
            if lvl is not None and int(lvl.get(f"{W}val", "9")) < 9:
                out.heading = int(lvl.get(f"{W}val", "9")) + 1
            jc = ppr.find(f"{W}jc")
            if jc is not None:
                out.centered = jc.get(f"{W}val") == "center"
            pb = ppr.find(f"{W}pageBreakBefore")
            if pb is not None and pb.get(f"{W}val", "true") not in ("0", "false"):
                out.page_break_before = True
        else:
            out.style, out.heading, out.centered = styles.get("Normal", ("", 0, False))
        parts: list[str] = []
        seen_text = False

        def walk(el: ET.Element) -> None:
            nonlocal seen_text
            for ch in el:
                tag = ch.tag
                if tag in (f"{W}del", f"{W}moveFrom", MC_FALLBACK, f"{W}instrText", f"{W}pPr"):
                    continue
                if tag in (f"{W}txbxContent", f"{W}footnoteReference", f"{W}endnoteReference"):
                    continue
                if tag == f"{W}t":
                    parts.append(ch.text or "")
                    seen_text = seen_text or bool((ch.text or "").strip())
                elif tag in (f"{W}tab", f"{W}cr"):
                    parts.append(" ")
                elif tag == f"{W}noBreakHyphen":
                    parts.append("-")
                elif tag == f"{W}lastRenderedPageBreak":
                    state["rendered"] = True
                    _new_page(seen_text, explicit=False)
                elif tag == f"{W}br":
                    if ch.get(f"{W}type") == "page":
                        _new_page(seen_text, explicit=True)
                    else:
                        parts.append(" ")
                else:
                    walk(ch)

        def _new_page(after_text: bool, explicit: bool) -> None:
            """Rendered breaks only move the page; explicit ones also mark a break."""
            if explicit and after_text:
                state["break_next"] = True
            if not (explicit and state["rendered"]):
                state["page"] += 1
            if not after_text:
                out.page = state["page"]
                out.page_break_before = out.page_break_before or explicit

        walk(p)
        if out.page_break_before and out.page < state["page"]:
            out.page = state["page"]
        out.text = "".join(parts)
        return out

    def blocks(el: ET.Element) -> None:
        for ch in el:
            if ch.tag == f"{W}p":
                raw.append(para(ch))
                if ch.find(f"{W}pPr/{W}sectPr") is not None:
                    state["break_next"] = True
                    if not state["rendered"]:
                        state["page"] += 1
            elif ch.tag in (f"{W}tbl", f"{W}tr", f"{W}tc", f"{W}sdt", f"{W}sdtContent"):
                blocks(ch)

    blocks(body)
    draft = Draft(_collect(raw), "docx", pages_known=bool(state["rendered"]))
    if not draft.pages_known:
        for p in draft.paragraphs:
            p.page = 0
    return draft


def _has_rendered_breaks(root: ET.Element) -> bool:
    return next(root.iter(f"{W}lastRenderedPageBreak"), None) is not None


def _as_file(data: bytes) -> io.BytesIO:
    return io.BytesIO(data)


# --- odt --------------------------------------------------------------------


def _odt_centred(zf: zipfile.ZipFile, content: ET.Element) -> dict[str, bool]:
    styles: dict[str, tuple[str, bool | None]] = {}
    roots = [content]
    if "styles.xml" in zf.namelist():
        roots.append(ET.fromstring(zf.read("styles.xml")))
    for root in roots:
        for st in root.iter(f"{STYLE}style"):
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
        zf = zipfile.ZipFile(_as_file(data))
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


READERS = {".txt": read_txt, ".md": read_md, ".docx": read_docx, ".odt": read_odt}


def read(path: Path) -> Draft:
    suffix = path.suffix.lower()
    if suffix not in READERS:
        raise IngestError(f"unsupported format {suffix!r} (use {', '.join(FORMATS)})")
    return READERS[suffix](path.read_bytes())


# --- workspace snapshot -----------------------------------------------------


@dataclass
class Result:
    version: str
    unchanged: bool
    paragraphs: int
    text_path: Path


def _versions(ws_root: Path) -> list[Path]:
    return sorted(
        (p for p in (ws_root / "manuscript").glob("v[0-9][0-9][0-9].*")), key=lambda p: p.stem
    )


def ingest(path: Path, ws_root: Path) -> Result:
    """Snapshot ``path`` into the workspace and write ``text/vNNN.txt`` + meta."""
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    existing = _versions(ws_root)
    if existing:
        last = existing[-1]
        if hashlib.sha256(last.read_bytes()).hexdigest() == digest:
            text = ws_root / "text" / f"{last.stem}.txt"
            count = len(text.read_text(encoding="utf-8").splitlines()) if text.is_file() else 0
            return Result(last.stem, True, count, text)
    draft = read(path)
    if not draft.paragraphs:
        raise IngestError("no text found")
    version = f"v{len(existing) + 1:03d}"
    (ws_root / "manuscript").mkdir(parents=True, exist_ok=True)
    (ws_root / "text").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, ws_root / "manuscript" / f"{version}{path.suffix.lower()}")
    text_path = ws_root / "text" / f"{version}.txt"
    text_path.write_text(draft.text, encoding="utf-8")
    meta = {
        "schema_version": 1,
        "version": version,
        "source_name": path.name,
        "source_sha256": digest,
        "format": draft.format,
        "ingested_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pages_known": draft.pages_known,
        "words": len(draft.text.split()),
        "notes": draft.notes,
        "paragraphs": [p.meta() for p in draft.paragraphs],
    }
    (ws_root / "text" / f"{version}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=0) + "\n", encoding="utf-8"
    )
    return Result(version, False, len(draft.paragraphs), text_path)
