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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

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
    """Word's owner file (``~$`` plus the name, or the name with its first two letters
    replaced) and LibreOffice's ``.~lock.<name>#``, when present."""
    found: list[Path] = []
    if not doc.parent.is_dir():
        return found
    for f in doc.parent.iterdir():
        name = f.name
        if name.startswith("~$"):
            rest = name[2:]
            if rest == doc.name or (len(rest) >= len(doc.name) - 2 and doc.name.endswith(rest)):
                found.append(f)
        elif name == f".~lock.{doc.name}#":
            found.append(f)
    return sorted(found)


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
    state[_key(doc)] = {
        "path": str(doc),
        "sha256": digest,
        "mtime": doc.stat().st_mtime if doc.exists() else 0,
        "read_at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _save_state(ws_root, state)
    return digest


def backups(ws_root: Path, doc: Path) -> list[Path]:
    d = ws_root / "backups"
    return sorted(d.glob(f"{doc.stem}-*{doc.suffix}")) if d.is_dir() else []


def status(ws_root: Path, doc: Path) -> Status:
    if not doc.is_file():
        raise SafeEditError("missing", f"{doc} does not exist")
    known = _load_state(ws_root).get(_key(doc), {})
    last = str(known.get("sha256", ""))
    changed = bool(last) and last != sha256(doc.read_bytes())
    return Status(str(doc), bool(lock_files(doc)), changed, last, len(backups(ws_root, doc)))


def check_package(data: bytes) -> None:
    """A readable zip whose XML parts all parse."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        for name in zf.namelist():
            if name.endswith((".xml", ".rels")):
                ET.fromstring(zf.read(name))
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        raise SafeEditError("verify", f"the new document would not open: {exc}") from exc


def _backup(ws_root: Path, doc: Path, data: bytes) -> Path:
    d = ws_root / "backups"
    d.mkdir(parents=True, exist_ok=True)
    stamp = _now().strftime("%Y%m%dT%H%M%S%fZ")
    path = d / f"{doc.stem}-{stamp}{doc.suffix}"
    path.write_bytes(data)
    for old in backups(ws_root, doc)[:-KEEP_BACKUPS]:
        old.unlink()
    return path


def _log(ws_root: Path, entry: dict[str, Any]) -> None:
    f = ws_root / "log" / "edits.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write(
    ws_root: Path,
    doc: Path,
    transform: Callable[[bytes], tuple[bytes, Any]],
    expect: Callable[[bytes, bytes], None] | None = None,
    log: dict[str, Any] | None = None,
    _fail_at: str = "",
) -> tuple[Path, Any]:
    """Apply ``transform`` to the document safely; returns (backup path, transform's info).

    ``expect(old, new)`` raises when the new bytes are not exactly the intended
    change. ``_fail_at`` injects a failure at one of :data:`STEPS` (tests only).
    """
    if not doc.is_file():
        raise SafeEditError("missing", f"{doc} does not exist")
    if lock_files(doc):
        raise SafeEditError("locked", f"{doc.name} is open in Word; save it and close it first")
    data = doc.read_bytes()
    last = str(_load_state(ws_root).get(_key(doc), {}).get("sha256", ""))
    if last and last != sha256(data):
        raise SafeEditError(
            "changed", f"{doc.name} changed since it was last read; read it again before editing"
        )
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
        check_package(tmp.read_bytes())
        if expect is not None:
            expect(data, new)
        fail("verify")
        os.replace(tmp, doc)
        fail("after_replace")
        if doc.read_bytes() != new:
            raise SafeEditError("verify", "the document on disk is not what was written")
    except Exception as exc:
        if not doc.exists() or doc.read_bytes() != data:
            doc.write_bytes(data)
        if tmp.exists():
            tmp.unlink()
        if isinstance(exc, SafeEditError):
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
