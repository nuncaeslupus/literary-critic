"""The first overview, kept in the workspace so a later chat picks it up instead of re-reading.

The LLM writes the overview (what works, the biggest problems) for the writer; ``save``
stores it in ``<ws>/analysis/overview.json`` with the draft it was based on, which parts
of the novel were read for it, whether it is partial, and the Codex ``issue`` items that
record its problems. ``load`` returns it with ``stale`` set when a newer draft exists, so
the next chat knows to refresh it rather than repeat it.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from litcritic import structure, workspace
from litcritic.codex import Codex, CodexError

FILE = Path("analysis") / "overview.json"
SCHEMA_VERSION = 1
TEXT_CAP = 6000  # characters of overview text returned with the state


class OverviewError(Exception):
    """The overview cannot be saved or read."""


def path(root: Path) -> Path:
    return root / FILE


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _split(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for v in values or []:
        out += [s.strip() for s in v.split(",") if s.strip()]
    return out


def save(
    root: Path,
    text: str,
    read: list[str] | None = None,
    partial: bool = False,
    issues: list[str] | None = None,
    draft: str | None = None,
) -> dict[str, Any]:
    """Store the overview for ``draft`` (default: the latest); replaces any earlier one."""
    text = text.strip()
    if not text:
        raise OverviewError("the overview text is empty")
    latest = structure.latest_version(root)
    draft = draft or latest
    if not (root / "text" / f"{draft}.txt").is_file():
        raise OverviewError(f"no draft {draft!r} in this work")
    ids = _split(issues)
    if ids:
        try:
            codex = Codex(root)
        except CodexError as exc:
            raise OverviewError(str(exc)) from None
        missing = []
        for i in ids:
            try:
                codex.get(i)
            except CodexError:
                missing.append(i)
        if missing:
            raise OverviewError(f"no Codex item {', '.join(missing)}: record the issues first")
    doc = {
        "schema_version": SCHEMA_VERSION,
        "draft": draft,
        "saved": _now(),
        "read": _split(read),
        "partial": bool(partial),
        "issues": ids,
        "text": text,
    }
    f = path(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, f)
    return {**doc, "stale": draft != latest}


def load(root: Path, cap: int | None = None) -> dict[str, Any] | None:
    """The saved overview, with ``stale`` when a newer draft exists; None when there is none."""
    try:
        doc = json.loads(path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or not str(doc.get("text") or "").strip():
        return None
    try:
        latest = structure.latest_version(root)
    except FileNotFoundError:
        latest = None
    out = {k: doc.get(k) for k in ("draft", "saved", "read", "partial", "issues", "text")}
    out["stale"] = latest is not None and doc.get("draft") != latest
    text = str(out["text"])
    if cap is not None and len(text) > cap:
        out["text"] = text[:cap].rstrip() + " …"
        out["truncated"] = True
    return out


def _out(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def _cmd(args: Any) -> int:
    try:
        root = workspace.resolve(args.workspace, args.home).root
        if args.action == "show":
            shown = load(root)
            _out({"status": "ok", "overview": shown} if shown else {"status": "none"})
            return 0
        if args.text_file:
            text = Path(args.text_file).read_text(encoding="utf-8")
        else:
            text = args.text or ""
        _out({"status": "ok", "overview": save(root, text, args.read, args.partial, args.issues)})
        return 0
    except (OverviewError, FileNotFoundError) as exc:
        _out({"status": "refused", "message": str(exc)})
        return 1
    except (workspace.WorkspaceError, OSError, ValueError) as exc:
        _out({"status": "error", "message": str(exc)})
        return 2


def register(sub: Any) -> None:
    p = sub.add_parser("overview", help="the first overview, kept for the next chat")
    p.add_argument("action", choices=["save", "show"])
    p.add_argument("--workspace", required=True, help="workspace folder or slug")
    p.add_argument("--text", default=None, help="save: the overview as told to the writer")
    p.add_argument("--text-file", default=None, help="save: read the overview from this file")
    p.add_argument(
        "--read",
        action="append",
        default=None,
        help="save: what was read for it, e.g. c01,c23 or all (repeatable)",
    )
    p.add_argument("--partial", action="store_true", help="save: not the whole novel was read")
    p.add_argument(
        "--issues", action="append", default=None, help="save: Codex issue ids it rests on"
    )
    p.add_argument("--home", type=Path, default=None, help="where to look for works")
    p.set_defaults(func=_cmd)
