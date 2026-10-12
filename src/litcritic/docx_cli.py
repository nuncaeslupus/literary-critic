"""`lc docx …` commands: edit the writer's Word file in place, safely.

Every command prints one JSON object. Exit codes: 0 done, 1 refused (a safety
check failed and nothing was written), 2 usage or input error.

The document is the one named on the command line or in the request
(relative paths are taken from the novel's folder, the workspace's parent);
otherwise the ``.docx`` the tool read most recently (``lc ingest`` records it).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from litcritic import docx_edit, ingest, locate, query, safe_edit, structure, workspace

FIND_LIMIT = 255  # Word's Find box takes at most 255 characters
HITS_SHOWN = 20
ANCHOR = re.compile(r"(p\d+\.)?(c\d+|front)(\.\w+)*")


class CliError(Exception):
    """A usage or input error (exit 2)."""


def _out(payload: dict[str, Any], code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return code


def _document(ws_root: Path, name: str | None) -> Path:
    if name:
        path = Path(name).expanduser()
        if path.is_absolute():
            return path
        # As `lc docx` prints it (from the novel's folder) or as `lc setup` does
        # (from the folder above, starting with the novel folder's name).
        here, above = ws_root.parent / path, ws_root.parent.parent / path
        return above if not here.exists() and above.exists() else here
    docs = safe_edit.known_documents(ws_root, ".docx")
    if not docs:
        raise CliError("no document known yet: pass --document or run `lc ingest` on the .docx")
    return docs[-1]


def _shown(ws_root: Path, doc: Path) -> str:
    """Paths in output are relative to the novel's folder when they can be."""
    try:
        return str(doc.resolve().relative_to(ws_root.parent.resolve()))
    except ValueError:
        return str(doc)


# -- the Find string ----------------------------------------------------------


SPECIAL = {"^": "^^", "\n": "^p", "\t": "^t", "\x0b": "^l", "\x1e": "^~", "\u00a0": "^s"}


def _escape(text: str) -> str:
    return "".join(SPECIAL.get(c, c) for c in text)


def _fold(text: str) -> str:
    """Lower case, one character for one (Word's Find ignores case by default)."""
    return "".join(c if len(c.lower()) != 1 else c.lower() for c in text)


class Finder:
    """Word Find strings for one document (``docx_edit.find_texts``)."""

    def __init__(self, paras: list[str]) -> None:
        self.offsets = []
        total = 0
        for p in paras:
            self.offsets.append(total)
            total += len(p) + 1
        self.whole = "\n".join(paras)
        self.folded = _fold(self.whole)

    def _once(self, a: int, b: int) -> bool:
        needle = self.folded[a:b]
        i = self.folded.find(needle)
        return i >= 0 and self.folded.find(needle, i + 1) < 0

    def _fits(self, a: int, b: int) -> bool:
        return len(_escape(self.whole[a:b])) <= FIND_LIMIT

    def find(self, k: int, start: int = 0, min_end: int = 0) -> tuple[str, bool]:
        """Shortest Find string that occurs once in the document (any case) and
        starts at character ``start`` of paragraph ``k``, reaching at least ``min_end``.

        It grows word by word, into the next paragraphs (``^p``) when needed, and
        then backwards from the previous paragraph's end. Returns the escaped
        string and whether it is unique within Word's 255 characters.
        """
        whole, span = self.whole, 4 * FIND_LIMIT
        at = self.offsets[k] + start
        floor = self.offsets[k] + max(min_end, start + 1)
        ends = [at + m.end() for m in re.finditer(r"\S+", whole[at : at + span])]
        ends = [e for e in ends if e >= floor] or [min(floor, len(whole))]
        for e in ends:
            if not self._fits(at, e):
                break
            if self._once(at, e):
                return _escape(whole[at:e]), True
        first = ends[0]
        base = max(0, at - span)
        for m in reversed(list(re.finditer(r"\S+", whole[base:at]))):
            if not self._fits(base + m.start(), first):
                break
            if self._once(base + m.start(), first):
                return _escape(whole[base + m.start() : first]), True
        end = first
        while end > at + 1 and not self._fits(at, end):
            end -= 1
        return _escape(whole[at:end]), False


def find_string(paras: list[str], k: int, start: int = 0, min_end: int = 0) -> tuple[str, bool]:
    return Finder(paras).find(k, start, min_end)


# -- writer locators ------------------------------------------------------------


class _Places:
    """Maps a document paragraph to the latest ingested draft, for writer locators.

    Locators are only given while the document still matches the draft text
    (otherwise the chapter and page could be wrong): `lc ingest` it again.
    """

    def __init__(self, ws_root: Path, doc: Path, data: bytes, lang: str = "en") -> None:
        self.ix: query.Index | None = None
        self.by_ordinal: dict[int, int] = {}
        try:
            version = structure.latest_version(ws_root)
            ix = query.load(ws_root, version, codex=False)
            draft = ingest.read(doc, data)
        except (OSError, ValueError, KeyError, ingest.IngestError, FileNotFoundError):
            return
        if not ix.anchors or [p.text for p in draft.paragraphs] != ix.paragraphs:
            return
        self.ix = ix
        self.by_ordinal = {p.src: i for i, p in enumerate(draft.paragraphs)}
        self.builder = locate.LocatorBuilder(ix, locate.load_meta(ws_root, version), lang)
        self.ordinal_of = {i: p.src for i, p in enumerate(draft.paragraphs)}

    def locator(self, ordinal: int) -> dict[str, Any] | None:
        i = self.by_ordinal.get(ordinal)
        if self.ix is None or i is None:
            return None
        return self.builder.locate(self.ix.anchors[i]).as_where()


# -- commands -------------------------------------------------------------------


def _edits(args: argparse.Namespace, root: Path) -> int:
    try:
        req = json.loads(Path(args.edits).read_text(encoding="utf-8"))
        items = req["edits"]
        edits = [
            docx_edit.Edit(
                str(e["id"]),
                str(e["quote"]),
                str(e["replace"]),
                str(e.get("prefix", "")),
                str(e.get("suffix", "")),
            )
            for e in items
        ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CliError(f"cannot read the edits file: {exc}") from exc
    if not edits or len({e.id for e in edits}) != len(edits):
        raise CliError("the edits file needs at least one edit, each with its own id")
    doc = _document(root, args.document or req.get("document"))
    base = {"document": _shown(root, doc), "author": docx_edit.AUTHOR}
    try:
        data = doc.read_bytes()
        _, matches = docx_edit.apply(data, edits)
        if args.dry_run:
            st = safe_edit.status(root, doc)
            return _out(
                {
                    "status": "dry_run",
                    "applied": [e.id for e in edits],
                    "skipped": [],
                    "revisions": len(edits),
                    "locked": st.locked,
                    "changed_on_disk": st.changed_on_disk,
                    **base,
                }
            )
        expect = safe_edit.only_paragraphs_changed({m.para for m in matches})
        log: dict[str, Any] = {"command": "edits", "edit_ids": [e.id for e in edits]}
        log["reasons"] = {str(e["id"]): e.get("reason", "") for e in items}
        backup, _ = safe_edit.write(root, doc, lambda d: docx_edit.apply(d, edits), expect, log)
    except docx_edit.EditError as exc:
        reasons = exc.problems or {"document": str(exc)}
        return _out(_refused(base, "edit", str(exc), reasons, edits), 1)
    except safe_edit.SafeEditError as exc:
        return _out(_refused(base, exc.reason, str(exc), {}, edits), 1)
    return _out(
        {
            "status": "applied",
            "applied": [e.id for e in edits],
            "skipped": [],
            "backup": _shown(root, backup),
            "revisions": len(edits),
            **base,
        }
    )


def _refused(
    base: dict[str, Any],
    reason: str,
    message: str,
    problems: dict[str, str],
    edits: list[docx_edit.Edit],
) -> dict[str, Any]:
    return {
        "status": "refused",
        "reason": reason,
        "message": message,
        "applied": [],
        "skipped": [{"id": e.id, "reason": problems.get(e.id, "not applied")} for e in edits],
        "backup": None,
        "revisions": 0,
        **base,
    }


def _rename(args: argparse.Namespace, root: Path) -> int:
    if not args.new.strip():
        raise CliError("the new name is empty")
    doc = _document(root, args.document)
    sensitive = not args.ignore_case
    base: dict[str, Any] = {"document": _shown(root, doc), "old": args.old, "new": args.new}
    try:
        data = doc.read_bytes()
        _, applied, skipped = docx_edit.rename(data, args.old, args.new, sensitive)
        places = _Places(root, doc, data, args.lang)
        finder = Finder(docx_edit.find_texts(data))

        def hit(m: docx_edit.Match, why: str = "") -> dict[str, Any]:
            find, unique = finder.find(m.para, m.start, m.end)
            out: dict[str, Any] = {"text": m.text, "find": find, "unique": unique}
            out["locator"] = places.locator(m.para)
            if why:
                out["reason"] = why
            return out

        left = [hit(m, why) for m, why in skipped[:HITS_SHOWN]]
        if args.dry_run:
            return _out(
                {
                    "status": "dry_run",
                    "count": len(applied),
                    "hits": [hit(m) for m in applied[:HITS_SHOWN]],
                    "skipped": left,
                    "backup": None,
                    **base,
                }
            )
        paras = {m.para for m in applied}
        log = {"command": "rename", "old": args.old, "new": args.new, "count": len(applied)}

        def transform(d: bytes) -> tuple[bytes, Any]:
            out, *info = docx_edit.rename(d, args.old, args.new, sensitive)
            return out, info

        expect = safe_edit.only_paragraphs_changed(paras)
        backup, _ = safe_edit.write(root, doc, transform, expect, log)
    except docx_edit.EditError as exc:
        return _out({"status": "refused", "reason": "edit", "message": str(exc), **base}, 1)
    except safe_edit.SafeEditError as exc:
        return _out({"status": "refused", "reason": exc.reason, "message": str(exc), **base}, 1)
    return _out(
        {
            "status": "applied",
            "count": len(applied),
            "skipped": left,
            "backup": _shown(root, backup),
            **base,
        }
    )


def _locate(args: argparse.Namespace, root: Path) -> int:
    doc = _document(root, args.document)
    if not doc.is_file():
        return _out({"status": "refused", "reason": "missing", "message": f"{doc} not found"}, 1)
    data = doc.read_bytes()
    places = _Places(root, doc, data, args.lang)
    target = args.target.strip()
    i = None
    if not args.quote and ANCHOR.fullmatch(target) and places.ix is not None:
        try:
            i = query.paragraph_range(places.ix, target).start
        except KeyError:
            i = None
    if i is not None:
        ordinal, start, end = places.ordinal_of[i], 0, 0
    else:
        found = docx_edit.find(data, args.target)
        if len(found) != 1:
            if not found and not args.quote and ANCHOR.fullmatch(target) and places.ix is None:
                why = (
                    "the document no longer matches the last ingested draft; "
                    "run `lc ingest` and `lc anchor` on it first"
                )
                return _out({"status": "refused", "reason": "changed", "message": why}, 1)
            why = "not found" if not found else f"found {len(found)} times; quote more words"
            return _out({"status": "refused", "reason": "quote", "message": why}, 1)
        ordinal, start, end = found[0].para, found[0].start, found[0].end
    find, unique = Finder(docx_edit.find_texts(data)).find(ordinal, start, end)
    return _out(
        {
            "status": "ok",
            "document": _shown(root, doc),
            "find": find,
            "unique": unique,
            "locator": places.locator(ordinal),
        }
    )


def _status(args: argparse.Namespace, root: Path) -> int:
    doc = _document(root, args.document)
    try:
        st = safe_edit.status(root, doc)
    except safe_edit.SafeEditError as exc:
        return _out({"status": "refused", "reason": exc.reason, "message": str(exc)}, 1)
    return _out({"status": "ok", **st.as_json(), "document": _shown(root, doc)})


COMMANDS = {"edits": _edits, "rename": _rename, "locate": _locate, "status": _status}


def _run(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        args.lang = str(ws.manifest.get("language", "en"))
        return COMMANDS[args.docx_cmd](args, ws.root)
    except docx_edit.EditError as exc:  # not a readable Word document
        return _out({"status": "refused", "reason": "unreadable", "message": str(exc)}, 1)
    except (CliError, workspace.WorkspaceError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        print(f"error: {exc}", file=sys.stderr)
        return 2


def register(sub: Any) -> None:
    p = sub.add_parser("docx", help="edit the writer's Word file in place (tracked changes)")
    dsub = p.add_subparsers(dest="docx_cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--workspace", required=True, help="workspace folder or slug")
        sp.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
        sp.add_argument("--document", default=None, help="the .docx (default: last one read)")
        sp.set_defaults(func=_run)

    p_ed = dsub.add_parser("edits", help="apply approved edits as tracked changes")
    p_ed.add_argument("--edits", required=True, help="edits.json (see docs)")
    p_ed.add_argument("--dry-run", action="store_true", help="check only, write nothing")
    common(p_ed)
    p_rn = dsub.add_parser("rename", help="rename a whole word everywhere, as tracked changes")
    p_rn.add_argument("old")
    p_rn.add_argument("new")
    case = p_rn.add_mutually_exclusive_group()
    case.add_argument("--case-sensitive", action="store_true", help="the default")
    case.add_argument("--ignore-case", action="store_true", help="also other capitalisations")
    p_rn.add_argument("--dry-run", action="store_true", help="list the hits, write nothing")
    common(p_rn)
    p_lo = dsub.add_parser("locate", help="the Word Find string and writer locator of a passage")
    p_lo.add_argument("target", help="a paragraph anchor (c03.s1.p4) or a quote from the text")
    p_lo.add_argument("--quote", action="store_true", help="search the target as text only")
    common(p_lo)
    p_st = dsub.add_parser("status", help="is the document open, changed, backed up")
    common(p_st)
