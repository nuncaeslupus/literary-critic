"""`lc remove`: delete the tool's work on a novel, so the writer can start over.

Only the work folder goes (analysis, rounds, notes, the tool's copies of the
drafts) and its line in the registry; the writer's own files are never touched.
Without ``--confirm`` it only says what would go: the writer confirms twice
(``prompts/05-setup.md``), then the work's id is passed as ``--confirm``. A zip
of the folder (``lc pack``, restored with ``lc unpack``) is written next to it
first, and nothing is deleted if that fails.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any

from litcritic import pack, workspace


class RemoveError(Exception):
    """The folder is not one this tool may delete."""


def _check(root: Path) -> None:
    unsafe = {Path.home().resolve(), workspace.home().expanduser().resolve()}
    if root in unsafe or root == Path(root.anchor) or not (root / workspace.MANIFEST).is_file():
        raise RemoveError(f"{root} is not a work folder this tool can delete")


def _unregister(root: Path) -> None:
    reg = workspace.registry_file()
    if not reg.is_file():
        return
    lines = reg.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if line.strip() and Path(line.strip()) != root]
    if kept != lines:
        reg.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")


def _writable(files: list[Path]) -> None:
    for f in files:
        os.chmod(f, stat.S_IWRITE | stat.S_IREAD)  # Windows will not delete a read-only file


def remove(ref: str, confirm: str = "", base: Path | None = None) -> dict[str, Any]:
    """What removing work ``ref`` deletes; deletes it only when ``confirm`` is its id."""
    ws = workspace.resolve(ref, base)
    root = ws.root.resolve()
    _check(root)
    meta = ws.manifest
    work_id = str(meta.get("id", ""))
    files = [f for f in root.rglob("*") if f.is_file()]
    out: dict[str, Any] = {
        "workspace_path": str(root),
        "title": str(meta.get("title", "")),
        "files": len(files),
        "bytes": sum(f.stat().st_size for f in files),
    }
    if not work_id or confirm != work_id:
        return {"status": "dry_run", **out, "confirm": work_id}
    backup, _ = pack.pack(root)
    _writable(files)
    shutil.rmtree(root)
    _unregister(root)
    return {"status": "removed", **out, "backup": str(backup)}


def _cmd(args: Any) -> int:
    try:
        out = remove(args.workspace, args.confirm or "", args.home)
    except (RemoveError, workspace.WorkspaceError, pack.PackError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("remove", help="delete the tool's work on a novel (never the novel)")
    p.add_argument("--workspace", required=True, help="the work's folder, id or slug")
    p.add_argument("--confirm", default=None, help="the work's id, after the writer confirmed")
    p.add_argument("--home", type=Path, default=None, help="where to look for works")
    p.set_defaults(func=_cmd)
