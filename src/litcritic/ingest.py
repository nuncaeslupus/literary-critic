"""Ingest a manuscript draft into a workspace.

Every manuscript is read through doc-control: a ``.docx`` directly, a ``.txt``,
``.md`` or ``.odt`` through a converted ``.docx`` copy (:mod:`litcritic.convert`,
spec D-6). The text becomes normalised text: one paragraph per line, whitespace
collapsed, Unicode NFC. Each paragraph's doc-control address (``at``) and the
layout facts structure detection and writer locators need (heading level,
centred, page, blank lines before, page break before, style) go to a sidecar
``vNNN.meta.json``. The original file is kept as a snapshot
``manuscript/vNNN.<ext>``; ingesting an unchanged file again is a no-op.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from litcritic import dc

FORMATS = (".txt", ".md", ".docx", ".odt")
META_SCHEMA = 2  # 2: each paragraph carries its doc-control address ``at``


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
    at: str = ""  # doc-control address, e.g. p142#a7b2a7b2 ("" before doc-control read it)

    @property
    def ordinal(self) -> int:
        """Position among all the document's paragraphs, from 0 (-1 when unknown)."""
        m = re.match(r"p(\d+)#", self.at)
        return int(m.group(1)) - 1 if m else -1

    def meta(self) -> dict[str, Any]:
        out: dict[str, Any] = {"at": self.at} if self.at else {}
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


# --- reading through doc-control ----------------------------------------------


def _read_docx(path: Path, fmt: str = "docx") -> Draft:
    """Every paragraph of a ``.docx`` file as doc-control reads it, in one bulk call.

    Pages count only when the file holds Word's rendered page marks (it was laid
    out by Word); otherwise every page is 0 (unknown).
    """
    try:
        with dc.open(path) as doc:
            rows = doc.paragraphs(normalized=True, pages=True)
            marks = 0
            if rows:
                head = doc.run("page.estimate", {"at": rows[0]["at"]})
                marks = int(head.get("rendered_marks") or 0)
    except dc.DocError as exc:
        raise IngestError(f"not a readable .docx: {exc}") from exc
    raw = [
        Para(
            str(row.get("normalized", row["text"])),
            heading=int(row.get("heading_level") or 0),
            centered=bool(row.get("centred")),
            page=int(row.get("page") or 0) if marks else 0,
            page_break_before=bool(row.get("page_break_before")),
            style=str(row.get("style_name") or row.get("style") or ""),
            at=str(row["at"]),
        )
        for row in rows
    ]
    return Draft(_collect(raw), fmt, pages_known=bool(marks))


@contextlib.contextmanager
def docx_of(path: Path, data: bytes | None = None) -> Iterator[tuple[Path, list[str]]]:
    """The ``.docx`` doc-control reads for the manuscript at ``path`` (or ``data``).

    A ``.docx`` is used as it is (a temporary copy when ``data`` differs from the
    file); a ``.txt``, ``.md`` or ``.odt`` is converted first. Converting the same
    bytes again rebuilds the same copy, so addresses taken from it stay valid.
    Also yields the conversion notes.
    """
    suffix = path.suffix.lower()
    if suffix not in FORMATS:
        raise IngestError(f"unsupported format {suffix!r} (use {', '.join(FORMATS)})")
    notes: list[str] = []
    if suffix == ".docx":
        if data is None or (path.is_file() and path.read_bytes() == data):
            yield path, notes
            return
        docx = data
    else:
        from litcritic import convert  # convert builds on this module's Para and Draft

        source = convert.source(path, data)
        notes = source.notes
        docx = convert.draft_to_docx(source)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / f"{path.stem or 'draft'}.docx"
        copy.write_bytes(docx)
        yield copy, notes


def read(path: Path, data: bytes | None = None) -> Draft:
    """The manuscript at ``path`` (or ``data``, its bytes) as doc-control reads it.

    A ``.txt``, ``.md`` or ``.odt`` file is converted to a ``.docx`` copy first;
    its addresses then point into that copy, which converting the same bytes
    again rebuilds identically.
    """
    with docx_of(path, data) as (docx, notes):
        suffix = path.suffix.lower()
        draft = _read_docx(docx, suffix[1:])
    draft.notes = notes
    return draft


# --- documents read -----------------------------------------------------------
#
# Which documents the tool has read, and their bytes then: `lc docx` writes only
# to a document the tool has read (doc-control refuses one changed since), and
# defaults to the one read last.


def _read_state(ws_root: Path) -> Path:
    return ws_root / "state" / "documents.json"


def _load_reads(ws_root: Path) -> dict[str, dict[str, Any]]:
    f = _read_state(ws_root)
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def record_read(ws_root: Path, doc: Path, data: bytes | None = None) -> str:
    """Remember the document as the tool last saw it; returns its hash."""
    data = doc.read_bytes() if data is None else data
    digest = hashlib.sha256(data).hexdigest()
    state = _load_reads(ws_root)
    seq = max((int(r.get("seq", 0)) for r in state.values()), default=0) + 1
    state[str(doc.resolve())] = {
        "path": str(doc),
        "sha256": digest,
        "seq": seq,  # read order (read_at has one-second resolution)
        "read_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    f = _read_state(ws_root)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, f)
    return digest


def last_read(ws_root: Path, doc: Path) -> str:
    """The hash of the document when the tool last read it ("" when never)."""
    return str(_load_reads(ws_root).get(str(doc.resolve()), {}).get("sha256", ""))


def is_last_read(ws_root: Path, doc: Path, digest: str) -> bool:
    """These bytes are what the tool last read, and this is the last document read."""
    state = _load_reads(ws_root)
    top = max((int(r.get("seq", 0)) for r in state.values()), default=0)
    known = state.get(str(doc.resolve()), {})
    return known.get("sha256") == digest and int(known.get("seq", 0)) == top


def known_documents(ws_root: Path, suffix: str = "") -> list[Path]:
    """Documents the tool has read, oldest read first."""
    rows = sorted(_load_reads(ws_root).values(), key=lambda r: int(r.get("seq", 0)))
    paths = [Path(str(r.get("path", ""))) for r in rows]
    return [d for d in paths if not suffix or d.suffix.lower() == suffix.lower()]


# --- workspace snapshot -----------------------------------------------------


@dataclass
class Result:
    version: str
    unchanged: bool
    paragraphs: int
    text_path: Path


def _versions(ws_root: Path) -> list[Path]:
    found = [p for p in (ws_root / "manuscript").glob("v*.*") if re.fullmatch(r"v\d{3,}", p.stem)]
    return sorted(found, key=lambda p: int(p.stem[1:]))


def ingest(path: Path, ws_root: Path) -> Result:
    """Snapshot ``path`` into the workspace and write ``text/vNNN.txt`` + meta."""
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    existing = _versions(ws_root)
    draft = read(path, data)
    if not draft.paragraphs:
        raise IngestError("no text found")
    if path.suffix.lower() == ".docx" and not is_last_read(ws_root, path.resolve(), digest):
        # What the tool has seen: `lc docx` refuses to edit a file saved since.
        record_read(ws_root, path.resolve(), data)
        # doc-control backs the file up and notes it in its history; in a read-only
        # folder it cannot, and every write backs the file up again anyway.
        with contextlib.suppress(dc.DocError):
            dc.run("open", {"doc": str(path.resolve())})
    version = f"v{int(existing[-1].stem[1:]) + 1:03d}" if existing else "v001"
    if existing and hashlib.sha256(existing[-1].read_bytes()).hexdigest() == digest:
        version = existing[-1].stem
        text = ws_root / "text" / f"{version}.txt"
        if text.is_file() and (ws_root / "text" / f"{version}.meta.json").is_file():
            return Result(version, True, len(draft.paragraphs), text)
        # A previous run stopped after the snapshot: finish writing text and meta.
    (ws_root / "manuscript").mkdir(parents=True, exist_ok=True)
    (ws_root / "text").mkdir(parents=True, exist_ok=True)
    (ws_root / "manuscript" / f"{version}{path.suffix.lower()}").write_bytes(data)
    text_path = ws_root / "text" / f"{version}.txt"
    text_path.write_text(draft.text, encoding="utf-8")
    meta = {
        "schema_version": META_SCHEMA,
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
