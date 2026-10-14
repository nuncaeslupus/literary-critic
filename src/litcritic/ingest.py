"""Ingest a manuscript draft into a workspace.

Every manuscript (``.docx``, ``.odt``, ``.txt`` or ``.md``) is read directly
through doc-control. The text becomes normalised text: one paragraph per line, whitespace
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
from pathlib import Path, PurePosixPath, PureWindowsPath
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
    source: dict[str, Any] = field(default_factory=dict)  # doc-control's, for .txt, .md and .odt

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


def _read_doc(path: Path, fmt: str, text_mode: str | None = None) -> Draft:
    """Every paragraph of a document as doc-control reads it, in one bulk call.

    Pages count only when the file holds Word's rendered page marks (it was laid
    out by Word); otherwise every page is 0 (unknown). For a ``.txt``, ``.md`` or
    ``.odt`` file, doc-control's ``source`` (format; for text, encoding and reading
    mode) is kept, and becomes the notes;
    ``text_mode`` (``lines``, ``blocks``; doc-control's ``auto`` when None) is how a
    ``.txt`` is cut into paragraphs.
    """
    try:
        with dc.open(path, text_mode=text_mode) as doc:
            rows = doc.paragraphs(normalized=True, pages=True)
            marks = 0
            if rows:
                head = doc.run("page.estimate", {"at": rows[0]["at"]})
                marks = int(head.get("rendered_marks") or 0)
            source = doc.source()  # empty for a .docx
    except dc.DocError as exc:
        raise IngestError(f"not a readable {path.suffix.lower() or 'file'}: {exc}") from exc
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
    return Draft(
        _collect(raw), fmt, pages_known=bool(marks), notes=_source_notes(source), source=source
    )


WRAP_MIN_PARAS = 50  # too few paragraphs to tell a wrapped text from short prose
WRAP_WIDTHS = (40, 110)  # line widths (characters) a hard-wrapped text is cut at
WRAP_OPEN = 0.3  # share of paragraphs ending mid-sentence that means wrapped lines
WRAP_END = ".!?…:;»”\"')]—-"


def hard_wrapped(paras: list[str]) -> int:
    """The line width (characters) when the text holds one paragraph per line of a
    hard-wrapped text, else 0.

    Real paragraphs end a sentence and vary widely in length; wrapped lines are cut
    near one width and most end mid-sentence.
    """
    if len(paras) < WRAP_MIN_PARAS:
        return 0
    lengths = sorted(len(t) for t in paras)
    width = lengths[int(0.9 * (len(lengths) - 1))]
    if not WRAP_WIDTHS[0] <= width <= WRAP_WIDTHS[1]:
        return 0
    open_ = sum(not t.rstrip().endswith(tuple(WRAP_END)) for t in paras)
    return width if open_ >= WRAP_OPEN * len(paras) else 0


def _wrap_notes(draft: Draft) -> list[str]:
    if "hard-wrapped blocks" in draft.notes:
        return []
    width = hard_wrapped([p.text for p in draft.paragraphs if not p.heading])
    if not width:
        return []
    return [f"hard-wrapped: one paragraph per line of about {width} characters"]


def _source_notes(source: dict[str, Any]) -> list[str]:
    notes = ["hard-wrapped blocks"] if source.get("mode") == "blocks" else []
    encoding = str(source.get("encoding") or "")
    if encoding and encoding not in ("utf-8", "utf-8-sig"):
        notes.append(f"encoding: {encoding}")
    return notes


def converted_text(meta: dict[str, Any]) -> bool:
    """A ``.txt``, ``.md`` or ``.odt`` draft whose addresses point into the ``.docx``
    copy an older release converted it to (its meta has no ``source``): doc-control
    now reads the file itself, and its addresses may differ (``lc upgrade`` reads it
    again)."""
    return meta.get("format") in ("txt", "md", "odt") and not meta.get("source")


def text_mode(ws_root: Path) -> str | None:
    """How the work's kind has doc-control cut a ``.txt`` into paragraphs (its
    ``TEXT_MODE``, e.g. ``lines`` for verse); None leaves doc-control's ``auto``."""
    from litcritic import kinds

    mode = getattr(kinds.of_work(ws_root), "TEXT_MODE", None)
    return str(mode) if mode else None


@contextlib.contextmanager
def readable(path: Path, data: bytes | None = None) -> Iterator[Path]:
    """The file doc-control reads for the manuscript at ``path`` (or ``data``).

    doc-control reads every supported format itself: the file is used as it is (a
    temporary copy when ``data`` differs from it).
    """
    suffix = path.suffix.lower()
    if suffix not in FORMATS:
        raise IngestError(f"unsupported format {suffix!r} (use {', '.join(FORMATS)})")
    if data is None or (path.is_file() and path.read_bytes() == data):
        yield path
        return
    name = f"{path.stem or 'draft'}{suffix}"
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / name
        copy.write_bytes(data)
        yield copy


def read(path: Path, data: bytes | None = None, *, text_mode: str | None = None) -> Draft:
    """The manuscript at ``path`` (or ``data``, its bytes) as doc-control reads it.

    A ``.txt`` is cut into paragraphs by ``text_mode`` (doc-control's ``auto`` when
    None).
    """
    with readable(path, data) as doc:
        return _read_doc(doc, path.suffix.lower()[1:], text_mode)


# --- documents read -----------------------------------------------------------
#
# Which documents the tool has read, and their bytes then: `lc docx` writes only
# to a document the tool has read (doc-control refuses one changed since), and
# defaults to the one read last.


def _read_state(ws_root: Path) -> Path:
    return ws_root / "state" / "documents.json"


def stored_path(ws_root: Path, doc: Path) -> str:
    """How the workspace records ``doc``: relative to the novel's folder (the
    workspace's parent) when it lies inside it, so the workspace still works when that
    folder is reached by another path (Cowork's sandbox, the writer's computer, a later
    conversation); absolute otherwise."""
    doc = doc.resolve()
    try:
        return doc.relative_to(ws_root.resolve().parent).as_posix()
    except ValueError:
        return str(doc)


def recorded_path(ws_root: Path, stored: str) -> Path:
    """The document a workspace recorded as ``stored``. An absolute path that is gone
    (recorded where the novel's folder had another path) is found again under the
    novel's folder by its longest tail that exists there."""
    base = ws_root.resolve().parent
    path = Path(stored)
    # recorded on another system: a sandbox's /tmp/... is not absolute to Windows
    other = next(
        (p for p in (PurePosixPath(stored), PureWindowsPath(stored)) if p.is_absolute()), None
    )
    if other is None:
        return (base / path).resolve()
    if path.is_absolute() and path.exists():
        return path.resolve()
    parts = other.parts[1:]
    for i in range(len(parts)):
        candidate = base.joinpath(*parts[i:])
        if candidate.is_file():
            return candidate.resolve()
    return path


def _load_reads(ws_root: Path) -> dict[str, dict[str, Any]]:
    """The documents read, keyed by their absolute path here."""
    f = _read_state(ws_root)
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    reads: dict[str, dict[str, Any]] = {}
    for key, row in data.items():
        if not isinstance(row, dict):
            continue
        path = str(recorded_path(ws_root, key))
        if int(reads.get(path, {}).get("seq", 0)) <= int(row.get("seq", 0)):
            reads[path] = {**row, "path": path}
    return reads


def record_read(ws_root: Path, doc: Path, data: bytes | None = None) -> str:
    """Remember the document as the tool last saw it; returns its hash."""
    data = doc.read_bytes() if data is None else data
    digest = hashlib.sha256(data).hexdigest()
    state = _load_reads(ws_root)
    seq = max((int(r.get("seq", 0)) for r in state.values()), default=0) + 1
    state[str(doc.resolve())] = {
        "path": str(doc.resolve()),
        "sha256": digest,
        "seq": seq,  # read order (read_at has one-second resolution)
        "read_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    f = _read_state(ws_root)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    stored = {
        stored_path(ws_root, Path(k)): {**r, "path": stored_path(ws_root, Path(k))}
        for k, r in state.items()
    }
    tmp.write_text(json.dumps(stored, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
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
    notes: tuple[str, ...] = ()


def _versions(ws_root: Path) -> list[Path]:
    found = [p for p in (ws_root / "manuscript").glob("v*.*") if re.fullmatch(r"v\d{3,}", p.stem)]
    return sorted(found, key=lambda p: int(p.stem[1:]))


def ingest(path: Path, ws_root: Path) -> Result:
    """Snapshot ``path`` into the workspace and write ``text/vNNN.txt`` + meta."""
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    existing = _versions(ws_root)
    mode = text_mode(ws_root)
    draft = read(path, data, text_mode=mode)
    if not draft.paragraphs:
        raise IngestError("no text found")
    if mode != "lines":  # verse is one line per paragraph by design
        draft.notes = [*draft.notes, *_wrap_notes(draft)]
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
            return Result(version, True, len(draft.paragraphs), text, tuple(draft.notes))
        # A previous run stopped after the snapshot: finish writing text and meta.
    (ws_root / "manuscript").mkdir(parents=True, exist_ok=True)
    (ws_root / "manuscript" / f"{version}{path.suffix.lower()}").write_bytes(data)
    return _write_text(ws_root, version, path.name, digest, draft)


def reingest(ws_root: Path, version: str, source_name: str = "") -> Result:
    """Read ``manuscript/<version>.*`` again and rewrite its text and meta.

    For a workspace made by an older release (``lc upgrade``): the snapshot is only
    read, and the writer's own file is not looked at.
    """
    found = [p for p in _versions(ws_root) if p.stem == version and p.suffix in FORMATS]
    if not found:
        raise IngestError(f"no manuscript/{version}.* to read again")
    data = found[0].read_bytes()
    draft = read(found[0], data, text_mode=text_mode(ws_root))
    if not draft.paragraphs:
        raise IngestError(f"no text found in manuscript/{found[0].name}")
    digest = hashlib.sha256(data).hexdigest()
    return _write_text(ws_root, version, source_name or found[0].name, digest, draft)


def _write_text(ws_root: Path, version: str, source_name: str, digest: str, draft: Draft) -> Result:
    (ws_root / "text").mkdir(parents=True, exist_ok=True)
    text_path = ws_root / "text" / f"{version}.txt"
    text_path.write_text(draft.text, encoding="utf-8")
    meta = {
        "schema_version": META_SCHEMA,
        "version": version,
        "source_name": source_name,
        "source_sha256": digest,
        "format": draft.format,
        "ingested_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pages_known": draft.pages_known,
        "words": len(draft.text.split()),
        "notes": draft.notes,
        **({"source": draft.source} if draft.source else {}),
        "paragraphs": [p.meta() for p in draft.paragraphs],
    }
    (ws_root / "text" / f"{version}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=0) + "\n", encoding="utf-8"
    )
    return Result(version, False, len(draft.paragraphs), text_path, tuple(draft.notes))
