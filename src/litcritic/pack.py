"""Carry a workspace between sessions as a zip with a checksummed manifest.

Every pack bumps a generation number kept in ``.pack-state.json`` inside the
workspace (and therefore inside the zip). Unpacking refuses to overwrite newer
or diverged work:

- the zip is older than the workspace (lower generation);
- same generation but different content (two sessions worked from one zip);
- the zip is newer but the workspace changed since it was last packed or
  unpacked, so those changes would be lost.

``force=True`` overrides the refusal; checksum and path safety checks always run.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from litcritic import __version__
from litcritic.workspace import MANIFEST as WORKSPACE_MANIFEST
from litcritic.workspace import SUBDIRS, check_location

ZIP_MANIFEST = "PACK-MANIFEST.json"
STATE = ".pack-state.json"
SKIP = {".DS_Store", "Thumbs.db", "desktop.ini"}


class PackError(Exception):
    """The zip cannot be unpacked safely."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _files(root: Path) -> dict[str, str]:
    """relative posix path -> sha256, excluding the pack state and junk files."""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name not in SKIP and p.name != STATE and not p.name.startswith("~$"):
            out[p.relative_to(root).as_posix()] = _sha(p.read_bytes())
    return out


def _state(root: Path) -> dict[str, Any]:
    f = root / STATE
    return (
        json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {"generation": 0, "files": {}}
    )


def _write_state(root: Path, generation: int, files: dict[str, str]) -> None:
    (root / STATE).write_text(
        json.dumps({"generation": generation, "files": files}, indent=1) + "\n", encoding="utf-8"
    )


def pack(root: Path, out: Path | None = None) -> tuple[Path, dict[str, Any]]:
    """Zip the workspace at ``root``; returns the zip path and its manifest."""
    if not (root / WORKSPACE_MANIFEST).is_file():
        raise PackError(f"not a workspace: {root}")
    files = _files(root)
    generation = int(_state(root).get("generation", 0)) + 1
    _write_state(root, generation, files)
    manifest = {
        "schema_version": 1,
        "slug": root.name,
        "generation": generation,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool_version": __version__,
        "files": files,
    }
    out = out or root.parent / f"{root.name}-g{generation:03d}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(ZIP_MANIFEST, json.dumps(manifest, indent=1) + "\n")
        zf.write(root / STATE, STATE)
        for rel in files:
            zf.write(root / rel, rel)
    return out, manifest


@dataclass
class UnpackResult:
    action: str  # "created" | "updated" | "unchanged"
    generation: int
    written: int
    removed: int


def _safe(name: str) -> bool:
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts and not name.startswith(("/", "\\"))


def read_zip(zip_path: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Manifest and verified file contents; raises PackError on any inconsistency."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise PackError(f"not a readable zip: {exc}") from exc
    with zf:
        names = zf.namelist()
        if ZIP_MANIFEST not in names:
            raise PackError("zip has no manifest; it was not made by `lc pack`")
        manifest = json.loads(zf.read(ZIP_MANIFEST))
        files: dict[str, bytes] = {}
        for rel, digest in manifest.get("files", {}).items():
            if not _safe(rel):
                raise PackError(f"unsafe path in zip: {rel}")
            if rel not in names:
                raise PackError(f"missing from zip: {rel}")
            data = zf.read(rel)
            if _sha(data) != digest:
                raise PackError(f"checksum mismatch: {rel}")
            files[rel] = data
        extra = set(names) - set(files) - {ZIP_MANIFEST, STATE}
        if extra:
            raise PackError(f"files not in the manifest: {sorted(extra)[:5]}")
    return manifest, files


def unpack(zip_path: Path, root: Path, force: bool = False) -> UnpackResult:
    """Extract into ``root`` (created if missing) unless that would lose newer work."""
    check_location(root.resolve())
    manifest, files = read_zip(zip_path)
    zgen = int(manifest.get("generation", 0))
    if root.exists() and any(root.iterdir()):
        local = _state(root)
        lgen = int(local.get("generation", 0))
        current = _files(root)
        changed = current != local.get("files", {})
        if current == manifest["files"]:
            _write_state(root, max(zgen, lgen), current)
            return UnpackResult("unchanged", max(zgen, lgen), 0, 0)
        if not force:
            if zgen < lgen:
                raise PackError(
                    f"zip is older than this workspace (generation {zgen} < {lgen}); "
                    "use the newest zip, or --force to overwrite"
                )
            if zgen == lgen:
                raise PackError(
                    f"zip and workspace both continue generation {zgen} with different "
                    "content; keep one of them, or --force to take the zip"
                )
            if changed:
                raise PackError(
                    "this workspace changed since it was last packed or unpacked; "
                    "pack it first, or --force to discard those changes"
                )
        stale = set(local.get("files", {})) - set(files)
        removed = 0
        for rel in stale:
            target = root / rel
            if target.is_file():
                target.unlink()
                removed += 1
        action = "updated"
    else:
        removed = 0
        action = "created"
    for sub in SUBDIRS:  # zips carry files only; recreate the empty standard folders
        (root / sub).mkdir(parents=True, exist_ok=True)
    for rel, data in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    _write_state(root, zgen, dict(manifest["files"]))
    return UnpackResult(action, zgen, len(files), removed)
