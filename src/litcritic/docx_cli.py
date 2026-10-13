"""`lc docx …` commands: edit the writer's Word file in place, safely.

Every command prints one JSON object. Exit codes: 0 done, 1 refused (a safety
check failed and nothing was written), 2 usage or input error.

The edits themselves are doc-control's (through ``litcritic.dc``): quotes are
resolved to addresses verbatim (``anchor.resolve`` in exact mode) and applied
as one tracked ``batch`` or ``term.rename``. doc-control refuses a document open
in Word or changed since the tool last read it, backs it up, verifies the
result and keeps the history ``lc docx undo`` takes back.

The document is the one named on the command line or in the request
(relative paths are taken from the novel's folder, the workspace's parent);
otherwise the ``.docx`` the tool read most recently (``lc ingest`` records it).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from litcritic import dc, ingest, locate, query, structure, workspace

FIND_LIMIT = 255  # Word's Find box takes at most 255 characters
HITS_SHOWN = 20
ANCHOR = re.compile(r"(p\d+\.)?(c\d+|front)(\.\w+)*")
AUTHOR = "literary-critic"
ADDRESS = re.compile(r"p(\d+)#(\w+):(\d+)-(\d+)")  # a doc-control range
REASONS = {  # doc-control error code -> the stable reason `lc docx` reports
    "DOC_LOCKED": "locked",
    "DOC_CHANGED_ON_DISK": "changed",
    "STALE_ADDRESS": "changed",
    "DOC_NOT_FOUND": "missing",
    "NOT_A_DOCX": "unreadable",
    "VERIFY_FAILED_RESTORED": "restored",
    "UNSUPPORTED_CONTENT": "edit",
    "BATCH_CONFLICT": "edit",
    "HISTORY_NOT_FOUND": "nothing",
}
BY_HAND = "inside a field, link or note mark; change it by hand"


class CliError(Exception):
    """A usage or input error (exit 2)."""


def _out(payload: dict[str, Any], code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return code


def _document(ws_root: Path, name: str | None) -> Path:
    if name:
        path = Path(name).expanduser()
        return path if path.is_absolute() else ws_root.parent / path
    docs = ingest.known_documents(ws_root, ".docx")
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
    """Word Find strings for one document (its paragraphs' text, by position)."""

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
    """Find strings and writer locators for spots in the document.

    Locators are only given while the document still matches the latest ingested
    draft (otherwise the chapter and page could be wrong): `lc ingest` it again.
    """

    def __init__(self, ws_root: Path, doc: Path, data: bytes, lang: str = "en") -> None:
        self.ix: query.Index | None = None
        self.by_ordinal: dict[int, int] = {}
        self.texts: list[str] = []  # paragraph text by doc-control number - 1
        try:
            draft = ingest.read(doc, data)
        except (OSError, ValueError, KeyError, ingest.IngestError):
            return
        for p in draft.paragraphs:
            if p.ordinal >= 0:
                self.texts += [""] * (p.ordinal + 1 - len(self.texts))
                self.texts[p.ordinal] = p.text
        self.finder = Finder(self.texts)
        try:
            version = structure.latest_version(ws_root)
            ix = query.load(ws_root, version, codex=False)
        except (OSError, ValueError, KeyError, FileNotFoundError):
            return
        if not ix.anchors or [p.text for p in draft.paragraphs] != ix.paragraphs:
            return
        self.ix = ix
        self.by_ordinal = {p.ordinal: i for i, p in enumerate(draft.paragraphs)}
        self.builder = locate.LocatorBuilder(ix, locate.load_meta(ws_root, version), lang)
        self.ordinal_of = {i: p.ordinal for i, p in enumerate(draft.paragraphs)}

    def locator(self, ordinal: int) -> dict[str, Any] | None:
        i = self.by_ordinal.get(ordinal)
        if self.ix is None or i is None:
            return None
        return self.builder.locate(self.ix.anchors[i]).as_where()

    def spot(self, at: str, text: str) -> tuple[int, int, int]:
        """(paragraph position, start, end) in this text of a doc-control range.

        doc-control numbers paragraphs from 1 and counts the original characters;
        the text here is normalised (whitespace collapsed, soft hyphens dropped), so
        the passage sits at or before the range's offset: the nearest one is taken.
        """
        m = ADDRESS.fullmatch(at)
        if m is None:
            return -1, 0, 0
        k, a = int(m.group(1)) - 1, int(m.group(3))
        para = self.texts[k] if 0 <= k < len(self.texts) else ""
        needle = ingest.clean(text)
        found = [i.start() for i in re.finditer(re.escape(needle), para)] if needle else []
        start = max((i for i in found if i <= a), default=found[0] if found else 0)
        return k, start, start + len(needle)

    def find(self, k: int, start: int = 0, end: int = 0) -> tuple[str, bool]:
        if not 0 <= k < len(self.texts):
            return "", False
        return self.finder.find(k, start, end)

    def hit(self, at: str, text: str, why: str = "") -> dict[str, Any]:
        k, start, end = self.spot(at, text)
        find, unique = self.find(k, start, end)
        out: dict[str, Any] = {"text": text, "find": find, "unique": unique}
        out["locator"] = self.locator(k)
        if why:
            out["reason"] = why
        return out


# -- doc-control ------------------------------------------------------------------


class NotOnce(Exception):
    """A quote that is not in the document exactly once."""

    def __init__(self, count: int) -> None:
        super().__init__("not found" if not count else f"found {count} times")
        self.count = count


def _resolve(doc: Path, quote: str, prefix: str = "", suffix: str = "") -> str:
    """The doc-control range of the one place holding ``quote`` verbatim."""
    anchor = {"exact": quote}
    if prefix.strip():
        anchor["prefix"] = prefix
    if suffix.strip():
        anchor["suffix"] = suffix
    req = {"doc": str(doc), "anchor": anchor, "mode": "exact"}
    try:
        return str(dc.run("anchor.resolve", req)["at"])
    except dc.DocError as exc:
        if exc.code == "ANCHOR_NOT_FOUND":
            raise NotOnce(0) from exc
        if exc.code == "ANCHOR_AMBIGUOUS":
            raise NotOnce(max(len(exc.details.get("candidates", [])), 2)) from exc
        raise


def _sha256(doc: Path) -> str:
    return hashlib.sha256(doc.read_bytes()).hexdigest()


def _why(exc: dc.DocError, doc: Path) -> tuple[str, str]:
    """(reason, message for the writer) of a doc-control refusal."""
    reason = REASONS.get(exc.code, exc.code.lower())
    if reason == "locked":
        lock = Path(str(exc.details.get("lock_file", "~$" + doc.name))).name
        return reason, (
            f"Word has {lock} open (this document, or one with a very similar name); "
            "save it and close it first"
        )
    if reason == "changed":
        return reason, f"{doc.name} changed since it was last read; read it again first"
    if reason == "edit":
        return reason, f"{exc.message}; edit it by hand"
    return reason, str(exc)


def _unread(doc: Path) -> tuple[str, str]:
    return "unread", f"{doc.name} has not been read by the tool yet"


def _written(
    ws_root: Path, doc: Path, before: str, result: dict[str, Any], log: dict[str, Any]
) -> Path:
    """Record what doc-control wrote: the new bytes as read, and a log line."""
    after = ingest.record_read(ws_root, doc)
    backup = Path(str(result.get("backup", "")))
    entry = {
        "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "document": str(doc),
        "backup": str(backup),
        "before_sha256": before,
        "after_sha256": after,
        "op_id": result.get("op_id", ""),
        **log,
    }
    f = ws_root / "log" / "edits.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return backup


def _state(ws_root: Path, doc: Path) -> dict[str, Any]:
    last = ingest.last_read(ws_root, doc)
    info = dc.run("info", {"doc": str(doc)})
    history = dc.run("history.list", {"doc": str(doc), "limit": 200}).get("entries", [])
    return {
        "document": str(doc),
        "locked": bool(info.get("word_lock")),
        "changed_on_disk": bool(last) and last != _sha256(doc),
        "last_read_sha256": last,
        "backups": len({e["backup"] for e in history if e.get("backup")}),
    }


# -- commands -------------------------------------------------------------------


def _edits(args: argparse.Namespace, root: Path) -> int:
    try:
        req = json.loads(Path(args.edits).read_text(encoding="utf-8"))
        items = req["edits"]
        edits = [
            (
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
    ids = [e[0] for e in edits]
    if not edits or len(set(ids)) != len(edits):
        raise CliError("the edits file needs at least one edit, each with its own id")
    doc = _document(root, args.document or req.get("document"))
    base = {"document": _shown(root, doc), "author": AUTHOR}

    def refused(reason: str, message: str, problems: dict[str, str] | None = None) -> int:
        return _out(_refused(base, reason, message, problems or {}, ids), 1)

    if not doc.is_file():
        return refused("missing", f"{doc} does not exist")
    problems: dict[str, str] = {}
    spots: list[tuple[str, str, str]] = []  # (range, id, replacement)
    for eid, quote, replace, prefix, suffix in edits:
        if not quote.strip():
            problems[eid] = "empty quote"
            continue
        try:
            spots.append((_resolve(doc, quote, prefix, suffix), eid, replace))
        except NotOnce as exc:
            problems[eid] = str(exc) + ("; add context" if exc.count else "")
    places = sorted(
        (int(m.group(1)), int(m.group(3)), int(m.group(4)), eid)
        for at, eid, _ in spots
        if (m := ADDRESS.fullmatch(at))
    )
    for (p1, _, e1, a), (p2, s2, _, b) in pairwise(places):
        if p1 == p2 and s2 < e1:
            problems[b] = f"overlaps {a}"
    if problems:
        return refused("edit", "; ".join(f"{k}: {v}" for k, v in problems.items()), problems)
    ops = [{"op": "text.replace", "at": at, "text": replace} for at, _, replace in spots]
    batch: dict[str, Any] = {"doc": str(doc), "ops": ops, "author": AUTHOR, "tracked": True}
    last = ingest.last_read(root, doc)
    if not args.dry_run and not last:
        return refused(*_unread(doc))
    try:
        if args.dry_run:
            dc.run("batch", {**batch, "dry_run": True})
            st = _state(root, doc)
            return _out(
                {
                    "status": "dry_run",
                    "applied": ids,
                    "skipped": [],
                    "revisions": len(ids),
                    "locked": st["locked"],
                    "changed_on_disk": st["changed_on_disk"],
                    **base,
                }
            )
        result = dc.run("batch", {**batch, "expect": {"sha256": last}})
    except dc.DocError as exc:
        reason, message = _why(exc, doc)
        para = str(exc.details.get("paragraph", ""))
        named = {eid: message for at, eid, _ in spots if para and at.startswith(para + ":")}
        return refused(reason, message, named)
    log: dict[str, Any] = {"command": "edits", "edit_ids": ids}
    log["reasons"] = {str(e["id"]): e.get("reason", "") for e in items}
    backup = _written(root, doc, last, result, log)
    return _out(
        {
            "status": "applied",
            "applied": ids,
            "skipped": [],
            "backup": _shown(root, backup),
            "revisions": len(ids),
            **base,
        }
    )


def _refused(
    base: dict[str, Any],
    reason: str,
    message: str,
    problems: dict[str, str],
    ids: list[str],
) -> dict[str, Any]:
    return {
        "status": "refused",
        "reason": reason,
        "message": message,
        "applied": [],
        "skipped": [{"id": i, "reason": problems.get(i, "not applied")} for i in ids],
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

    def refused(reason: str, message: str) -> int:
        return _out({"status": "refused", "reason": reason, "message": message, **base}, 1)

    if not args.old.strip():
        return refused("edit", "nothing to rename: the old name is empty")
    if not doc.is_file():
        return refused("missing", f"{doc} does not exist")
    req: dict[str, Any] = {
        "doc": str(doc),
        "from": args.old,
        "to": args.new,
        "whole_word": True,
        "case_sensitive": sensitive,
        "preserve_case": True,  # with --ignore-case, each occurrence keeps its case
        "author": AUTHOR,
    }
    plan = dc.run("term.rename", {**req, "dry_run": True, "preview_limit": 200})
    counts = plan.get("counts", {})
    if not counts.get("matches"):
        return refused("edit", f"{args.old!r} does not appear in the document")
    hits = plan.get("preview", [])
    left: list[dict[str, Any]] = []
    places = _Places(root, doc, doc.read_bytes(), args.lang)
    if counts.get("skipped_unsupported") or counts.get("skipped_boundary"):
        # doc-control counts the occurrences it leaves alone; find says where they are.
        found = dc.run(
            "find",
            {
                "doc": str(doc),
                "query": args.old,
                "whole_word": True,
                "ignore_case": not sensitive,
                "limit": 200,
                "context": 0,
            },
        ).get("matches", [])
        done = {h["at"] for h in hits}
        left = [m for m in found if m["at"] not in done][:HITS_SHOWN]
    skipped = [places.hit(m["at"], m["text"], BY_HAND) for m in left]
    if args.dry_run:
        return _out(
            {
                "status": "dry_run",
                "count": counts.get("replaced", 0),
                "hits": [places.hit(h["at"], h["before"]) for h in hits[:HITS_SHOWN]],
                "skipped": skipped,
                "backup": None,
                **base,
            }
        )
    last = ingest.last_read(root, doc)
    if not last:
        return refused(*_unread(doc))
    try:
        result = dc.run("term.rename", {**req, "expect": {"sha256": last}})
    except dc.DocError as exc:
        return refused(*_why(exc, doc))
    count = result.get("counts", {}).get("replaced", 0)
    log = {"command": "rename", "old": args.old, "new": args.new, "count": count}
    backup = _written(root, doc, last, result, log)
    return _out(
        {
            "status": "applied",
            "count": count,
            "skipped": skipped,
            "backup": _shown(root, backup),
            **base,
        }
    )


def _locate(args: argparse.Namespace, root: Path) -> int:
    doc = _document(root, args.document)
    if not doc.is_file():
        return _out({"status": "refused", "reason": "missing", "message": f"{doc} not found"}, 1)
    places = _Places(root, doc, doc.read_bytes(), args.lang)
    target = args.target.strip()
    i = None
    if not args.quote and ANCHOR.fullmatch(target) and places.ix is not None:
        try:
            i = query.paragraph_range(places.ix, target).start
        except KeyError:
            i = None
    if i is not None:
        k, start, end = places.ordinal_of[i], 0, 0
    else:
        try:
            at = _resolve(doc, args.target)
        except NotOnce as exc:
            if not exc.count and not args.quote and ANCHOR.fullmatch(target) and places.ix is None:
                why = (
                    "the document no longer matches the last ingested draft; "
                    "run `lc ingest` and `lc anchor` on it first"
                )
                return _out({"status": "refused", "reason": "changed", "message": why}, 1)
            why = str(exc) + ("; quote more words" if exc.count else "")
            return _out({"status": "refused", "reason": "quote", "message": why}, 1)
        k, start, end = places.spot(at, args.target)
    find, unique = places.find(k, start, end)
    return _out(
        {
            "status": "ok",
            "document": _shown(root, doc),
            "find": find,
            "unique": unique,
            "locator": places.locator(k),
        }
    )


def _status(args: argparse.Namespace, root: Path) -> int:
    doc = _document(root, args.document)
    if not doc.is_file():
        why = f"{doc} does not exist"
        return _out({"status": "refused", "reason": "missing", "message": why}, 1)
    return _out({"status": "ok", **_state(root, doc), "document": _shown(root, doc)})


def _undo(args: argparse.Namespace, root: Path) -> int:
    doc = _document(root, args.document)
    base: dict[str, Any] = {"document": _shown(root, doc)}

    def refused(reason: str, message: str) -> int:
        return _out({"status": "refused", "reason": reason, "message": message, **base}, 1)

    if not doc.is_file():
        return refused("missing", f"{doc} does not exist")
    last = ingest.last_read(root, doc)
    if not args.dry_run and not last:
        return refused(*_unread(doc))
    req: dict[str, Any] = {"doc": str(doc)}
    if args.dry_run:
        req["dry_run"] = True
    else:
        req["expect"] = {"sha256": last}
    try:
        result = dc.run("undo", req)
    except dc.DocError as exc:
        reason, message = _why(exc, doc)
        if reason == "nothing":
            message = "there is no edit of the tool left to undo in this document"
        return refused(reason, message)
    out = {"undid": result.get("undid"), "paragraphs": result.get("paragraphs", 0)}
    if args.dry_run:
        return _out({"status": "dry_run", **out, "backup": None, **base})
    backup = _written(root, doc, last, result, {"command": "undo", "undid": out["undid"]})
    return _out({"status": "undone", **out, "backup": _shown(root, backup), **base})


COMMANDS = {
    "edits": _edits,
    "rename": _rename,
    "locate": _locate,
    "status": _status,
    "undo": _undo,
}


def _run(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        args.lang = str(ws.manifest.get("language", "en"))
        return COMMANDS[args.docx_cmd](args, ws.root)
    except dc.DocError as exc:  # not a readable Word document, or doc-control missing
        reason = REASONS.get(exc.code, exc.code.lower())
        return _out({"status": "refused", "reason": reason, "message": str(exc)}, 1)
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
    p_un = dsub.add_parser("undo", help="take back the tool's last edit or rename")
    p_un.add_argument("--dry-run", action="store_true", help="check only, write nothing")
    common(p_un)
