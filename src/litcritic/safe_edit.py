"""Write the writer's document safely: never lose work, never half-write.

Every write goes through :func:`write`:

1. refuse while the document is open in Word or LibreOffice (their lock
   file sits next to it), or when it changed on disk since the tool last
   read it (the writer saved something we have not seen);
2. back it up into the workspace's ``backups/`` (the last 20 per document);
3. build the new bytes, write them to a temporary file beside the document,
   check that it is a readable package whose XML parts all parse and that it
   holds exactly the intended changes;
4. replace the document atomically, read it back, and record its hash and a
   log line.

Any failure after the backup puts the original bytes back and raises
:class:`SafeEditError`; the document is never left half-written.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from litcritic import docx_edit

KEEP_BACKUPS = 20
STEPS = ("after_backup", "after_temp", "verify", "after_replace")


class SafeEditError(Exception):
    """The document was not changed (or was restored). ``reason`` is a stable code."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass
class Status:
    document: str
    locked: bool
    changed_on_disk: bool
    last_read_sha256: str
    backups: int

    def as_json(self) -> dict[str, Any]:
        return self.__dict__.copy()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lock_files(doc: Path) -> list[Path]:
    """Lock files of an open document: Word's owner file (``~$`` before the name, or
    replacing its first one or two letters, as Word does for longer names) and
    LibreOffice's ``.~lock.<name>#``. Word's short form can be shared by two names
    that differ only in their first letters; both then count as open."""
    names = {f"~${doc.name}", f"~${doc.name[1:]}", f"~${doc.name[2:]}", f".~lock.{doc.name}#"}
    return sorted(doc.parent / n for n in names if (doc.parent / n).is_file())


def _state_file(ws_root: Path) -> Path:
    return ws_root / "state" / "documents.json"


def _key(doc: Path) -> str:
    return str(doc.resolve())


def _load_state(ws_root: Path) -> dict[str, dict[str, Any]]:
    f = _state_file(ws_root)
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(ws_root: Path, state: dict[str, dict[str, Any]]) -> None:
    f = _state_file(ws_root)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, f)


def _now() -> datetime:
    return datetime.now(UTC)


def record_read(ws_root: Path, doc: Path, data: bytes | None = None) -> str:
    """Remember the document as the tool last saw it; returns its hash."""
    data = doc.read_bytes() if data is None else data
    digest = sha256(data)
    state = _load_state(ws_root)
    top = max((int(r.get("seq", 0)) for r in state.values()), default=0)
    known = state.get(_key(doc), {})
    if known.get("sha256") == digest and int(known.get("seq", 0)) == top:
        return digest  # already the last thing read: nothing to record
    seq = top + 1
    state[_key(doc)] = {
        "path": str(doc),
        "sha256": digest,
        "seq": seq,  # read order (read_at has one-second resolution)
        "read_at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _save_state(ws_root, state)
    return digest


def known_documents(ws_root: Path, suffix: str = "") -> list[Path]:
    """Documents the tool has read, oldest read first."""
    rows = sorted(_load_state(ws_root).values(), key=lambda r: int(r.get("seq", 0)))
    paths = [Path(str(r.get("path", ""))) for r in rows]
    return [d for d in paths if not suffix or d.suffix.lower() == suffix.lower()]


def _backup_prefix(doc: Path) -> str:
    """Backups of two documents never mix: the name plus a short hash of its full path."""
    return f"{doc.stem}.{hashlib.sha256(_key(doc).encode()).hexdigest()[:8]}."


def backups(ws_root: Path, doc: Path) -> list[Path]:
    d = ws_root / "backups"
    if not d.is_dir():
        return []
    prefix = _backup_prefix(doc)
    return sorted(f for f in d.iterdir() if f.name.startswith(prefix) and f.suffix == doc.suffix)


def status(ws_root: Path, doc: Path) -> Status:
    if not doc.is_file():
        raise SafeEditError("missing", f"{doc} does not exist")
    known = _load_state(ws_root).get(_key(doc), {})
    last = str(known.get("sha256", ""))
    changed = bool(last) and last != sha256(doc.read_bytes())
    return Status(str(doc), bool(lock_files(doc)), changed, last, len(backups(ws_root, doc)))


REQUIRED_PARTS = {".docx": ("[Content_Types].xml", "word/document.xml")}


def check_package(data: bytes, suffix: str = ".docx") -> None:
    """A readable package with its required parts, whose XML parts all parse."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            missing = [n for n in REQUIRED_PARTS.get(suffix, ()) if n not in names]
            if missing:
                raise SafeEditError("verify", f"the new document lacks {', '.join(missing)}")
            for name in names:
                if name.endswith((".xml", ".rels")):
                    ET.fromstring(zf.read(name))
    except SafeEditError:
        raise
    except (
        zipfile.BadZipFile,
        ET.ParseError,
        KeyError,
        zlib.error,
        NotImplementedError,
        RuntimeError,
        EOFError,
        ValueError,
    ) as exc:
        raise SafeEditError("verify", f"the new document would not open: {exc}") from exc


def only_paragraphs_changed(paragraphs: set[int]) -> Callable[[bytes, bytes], None]:
    """An ``expect`` check: the visible text differs only in these paragraphs."""

    def expect(old: bytes, new: bytes) -> None:
        a, b = docx_edit.texts(old), docx_edit.texts(new)
        if len(a) != len(b):
            raise SafeEditError("verify", "the number of paragraphs changed")
        stray = [
            k for k, (x, y) in enumerate(zip(a, b, strict=True)) if x != y and k not in paragraphs
        ]
        if stray:
            raise SafeEditError("verify", f"unexpected change in paragraph(s) {stray[:5]}")

    return expect


def _backup(ws_root: Path, doc: Path, data: bytes) -> Path:
    d = ws_root / "backups"
    d.mkdir(parents=True, exist_ok=True)
    stamp = _now().strftime("%Y%m%dT%H%M%S%fZ")
    path = d / f"{_backup_prefix(doc)}{stamp}{doc.suffix}"
    path.write_bytes(data)
    for old in backups(ws_root, doc)[:-KEEP_BACKUPS]:
        old.unlink()
    return path


def _log(ws_root: Path, entry: dict[str, Any]) -> None:
    f = ws_root / "log" / "edits.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _put(path: Path, data: bytes) -> None:
    """Write bytes atomically (temp file beside it, then replace)."""
    tmp = path.with_name(f".~lc-restore-{path.name}")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def write(
    ws_root: Path,
    doc: Path,
    transform: Callable[[bytes], tuple[bytes, Any]],
    expect: Callable[[bytes, bytes], None],
    log: dict[str, Any] | None = None,
    _fail_at: str = "",
) -> tuple[Path, Any]:
    """Apply ``transform`` to the document safely; returns (backup path, transform's info).

    ``expect(old, new)`` raises when the new bytes are not exactly the intended
    change (see :func:`only_paragraphs_changed`). ``_fail_at`` injects a failure
    at one of :data:`STEPS` (tests only).
    """
    if not doc.is_file():
        raise SafeEditError("missing", f"{doc} does not exist")

    def guard(data: bytes | None = None) -> bytes:
        locks = lock_files(doc)
        if locks:
            raise SafeEditError(
                "locked",
                f"Word has {locks[0].name} open (this document, or one with a very similar "
                "name); save it and close it first",
            )
        current = doc.read_bytes()
        if not last:
            raise SafeEditError("unread", f"{doc.name} has not been read by the tool yet")
        if sha256(current) != last or (data is not None and current != data):
            raise SafeEditError(
                "changed", f"{doc.name} changed since it was last read; read it again first"
            )
        return current

    last = str(_load_state(ws_root).get(_key(doc), {}).get("sha256", ""))
    data = guard()
    new, info = transform(data)  # raises before anything is written when an edit is unsafe
    backup = _backup(ws_root, doc, data)
    tmp = doc.with_name(f".~lc-{doc.name}")

    def fail(step: str) -> None:
        if _fail_at == step:
            raise RuntimeError(f"injected failure at {step}")

    try:
        fail("after_backup")
        with tmp.open("wb") as fh:
            fh.write(new)
            fh.flush()
            os.fsync(fh.fileno())
        fail("after_temp")
        check_package(tmp.read_bytes(), doc.suffix)
        expect(data, new)
        fail("verify")
        guard(data)  # the writer may have saved meanwhile: never overwrite that
        os.replace(tmp, doc)
        fail("after_replace")
        if doc.read_bytes() != new:
            raise SafeEditError("verify", "the document on disk is not what was written")
    except Exception as exc:
        if tmp.exists():
            tmp.unlink()
        on_disk = doc.read_bytes() if doc.exists() else None
        if on_disk is None or (on_disk == new and new != data):
            try:
                _put(doc, data)  # only our own write is undone, never the writer's save
            except OSError as io_exc:
                raise SafeEditError(
                    "restore_failed",
                    f"{exc}; putting the original back also failed ({io_exc}): "
                    f"copy {backup} over {doc}",
                ) from exc
        if isinstance(exc, SafeEditError):
            if exc.reason in ("changed", "locked"):
                raise
            exc.args = (f"{exc}; the original was put back",)
            raise
        raise SafeEditError("restored", f"{exc}; the original was put back") from exc
    record_read(ws_root, doc, new)
    _log(
        ws_root,
        {
            "at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "document": str(doc),
            "backup": str(backup),
            "before_sha256": sha256(data),
            "after_sha256": sha256(new),
            **(log or {}),
        },
    )
    return backup, info
