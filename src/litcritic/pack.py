"""Carry a workspace between sessions as a zip with a checksummed manifest.

Every pack gets an id (a hash of its file list and its parent's id) and records
its lineage — the ids of the packs it descends from. The workspace keeps the
lineage of its last pack or unpack in ``.pack-state.json``. Unpacking is a
fast-forward only:

- the zip is one of the workspace's ancestors → refused as older;
- the workspace's last pack is not among the zip's ancestors → refused as
  diverged (two sessions worked from one zip);
- the zip is newer but the workspace changed since its last pack or unpack →
  refused, those changes would be lost.

``force=True`` overrides those refusals and makes the workspace an exact copy
of the zip. Checksums, manifest shape and path safety are always enforced, and
files are staged before anything in the workspace is touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from litcritic import __version__, workspace
from litcritic.workspace import MANIFEST as WORKSPACE_MANIFEST

ZIP_MANIFEST = "PACK-MANIFEST.json"
STATE = ".pack-state.json"
SKIP = {".DS_Store", "Thumbs.db", "desktop.ini"}
# Folders that stay on this machine: never packed, never replaced by an unpack
# (``lc upgrade``'s backups: a pack is what the writer shares).
LOCAL_ONLY = ("upgrade-backup",)
MAX_LINEAGE = 200
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
EMPTY_STATE: dict[str, Any] = {"generation": 0, "lineage": [], "files": {}}


class PackError(Exception):
    """The zip cannot be unpacked safely."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _files(root: Path) -> dict[str, str]:
    """relative posix path -> sha256, excluding the pack state, junk files and the
    local-only folders."""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.relative_to(root).parts[0] in LOCAL_ONLY:
            continue
        if p.is_file() and p.name not in SKIP and p.name != STATE and not p.name.startswith("~$"):
            out[p.relative_to(root).as_posix()] = _sha(p.read_bytes())
    return out


def _state(root: Path) -> dict[str, Any]:
    f = root / STATE
    if not f.is_file():
        return dict(EMPTY_STATE)
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise PackError(f"damaged {STATE} in the workspace: {exc}") from exc
    return data if isinstance(data, dict) else dict(EMPTY_STATE)


def _state_text(generation: int, lineage: list[str], files: dict[str, str]) -> str:
    payload = {"generation": generation, "lineage": lineage[-MAX_LINEAGE:], "files": files}
    return json.dumps(payload, indent=1) + "\n"


def pack(root: Path, out: Path | None = None) -> tuple[Path, dict[str, Any]]:
    """Zip the workspace at ``root``; returns the zip path and its manifest."""
    if not (root / WORKSPACE_MANIFEST).is_file():
        raise PackError(f"not a workspace: {root}")
    files = _files(root)
    state = _state(root)
    parent_lineage = [str(x) for x in state.get("lineage", [])]
    generation = int(state.get("generation", 0)) + 1
    pack_id = _sha(json.dumps([parent_lineage[-1:], files], sort_keys=True).encode())[:16]
    lineage = [*parent_lineage, pack_id][-MAX_LINEAGE:]
    manifest = {
        "schema_version": 1,
        "slug": root.name,
        "generation": generation,
        "id": pack_id,
        "lineage": lineage,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool_version": __version__,
        "files": files,
    }
    out = out or root.parent / f"{root.name}-g{generation:03d}.zip"
    partial = out.with_name(out.name + ".partial")
    state_text = _state_text(generation, lineage, files)
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(ZIP_MANIFEST, json.dumps(manifest, indent=1) + "\n")
            zf.writestr(STATE, state_text)
            for rel in files:
                zf.write(root / rel, rel)
        os.replace(partial, out)
    except OSError:
        partial.unlink(missing_ok=True)
        raise
    # Only a zip that exists on disk advances the workspace's state.
    (root / STATE).write_text(state_text, encoding="utf-8")
    return out, manifest


@dataclass
class UnpackResult:
    action: str  # "created" | "updated" | "unchanged"
    generation: int
    written: int
    removed: int


def _safe(name: str) -> bool:
    if not name or "\\" in name or ":" in name or "\x00" in name:
        return False
    p, w = PurePosixPath(name), PureWindowsPath(name)
    return not (p.is_absolute() or w.is_absolute() or w.drive or ".." in p.parts)


def read_manifest(zip_path: Path) -> dict[str, Any]:
    """The manifest alone, checked for shape (cheap: no file is hashed)."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            raw = zf.read(ZIP_MANIFEST)
    except KeyError as exc:
        raise PackError("zip has no manifest; it was not made by `lc pack`") from exc
    except (zipfile.BadZipFile, OSError) as exc:
        raise PackError(f"not a readable zip: {exc}") from exc
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise PackError(f"damaged manifest: {exc}") from exc
    ok = (
        isinstance(manifest, dict)
        and isinstance(manifest.get("files"), dict)
        and isinstance(manifest.get("slug"), str)
        and isinstance(manifest.get("generation"), int)
        and isinstance(manifest.get("lineage", []), list)
    )
    if not ok:
        raise PackError("damaged manifest: missing or malformed fields")
    if not SLUG.match(manifest["slug"]):
        raise PackError(f"unsafe workspace name in zip: {manifest['slug']!r}")
    return dict(manifest)


def read_zip(zip_path: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Manifest and verified file contents; raises PackError on any inconsistency."""
    manifest = read_manifest(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        files: dict[str, bytes] = {}
        for rel, digest in manifest["files"].items():
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


def _check_fast_forward(root: Path, manifest: dict[str, Any], current: dict[str, str]) -> None:
    local = _state(root)
    local_lineage = [str(x) for x in local.get("lineage", [])]
    zip_lineage = [str(x) for x in manifest.get("lineage", [])]
    zid = str(manifest.get("id", ""))
    if zid and zid in local_lineage:
        raise PackError(
            f"zip is older than this workspace (generation {manifest['generation']} < "
            f"{local.get('generation', 0)}); use the newest zip, or --force to overwrite"
        )
    if not local_lineage or local_lineage[-1] not in zip_lineage:
        raise PackError(
            "zip and workspace went separate ways (each has work the other lacks); "
            "keep one of them, or --force to take the zip"
        )
    if current != local.get("files", {}):
        raise PackError(
            "this workspace changed since it was last packed or unpacked; "
            "pack it first, or --force to discard those changes"
        )


def unpack(
    zip_path: Path,
    root: Path,
    force: bool = False,
    loaded: tuple[dict[str, Any], dict[str, bytes]] | None = None,
) -> UnpackResult:
    """Extract into ``root`` (created if missing) unless that would lose newer work."""
    root = root.expanduser().resolve()
    workspace.check_location(root)
    manifest, files = loaded or read_zip(zip_path)
    zgen = int(manifest["generation"])
    lineage = [str(x) for x in manifest.get("lineage", [])]
    exists = root.exists() and any(root.iterdir())
    current = _files(root) if exists else {}
    if exists and current == manifest["files"]:
        (root / STATE).write_text(_state_text(zgen, lineage, current), encoding="utf-8")
        return UnpackResult("unchanged", zgen, 0, 0)
    if exists and not force:
        _check_fast_forward(root, manifest, current)
    # Stage every file next to the workspace first; nothing there changes if this fails.
    stage = root.parent / f".{root.name}.unpack-tmp"
    shutil.rmtree(stage, ignore_errors=True)
    removed = 0
    try:
        for rel, data in files.items():
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        root.mkdir(parents=True, exist_ok=True)
        for sub in workspace.SUBDIRS:  # zips carry files only; recreate empty folders
            (root / sub).mkdir(parents=True, exist_ok=True)
        for rel in set(current) - set(files):  # files the zip does not have
            (root / rel).unlink(missing_ok=True)
            removed += 1
        for rel in files:
            dest = root / rel
            if dest.parent.is_file():
                dest.parent.unlink()
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage / rel, dest)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    (root / STATE).write_text(_state_text(zgen, lineage, dict(manifest["files"])), encoding="utf-8")
    workspace.register(root)
    return UnpackResult("updated" if exists else "created", zgen, len(files), removed)
