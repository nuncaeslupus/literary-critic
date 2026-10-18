"""`lc docx …` commands: edit the writer's Word file in place, safely.

Every command prints one JSON object. Exit codes: 0 done, 1 refused (a safety
check failed and nothing was written), 2 usage or input error.

The edits themselves are doc-control's (through ``litcritic.dc``): quotes are
resolved to addresses verbatim (``anchor.resolve`` in exact mode) and applied
as one plain ``batch`` or ``term.rename`` (``"tracked": false``: the text is changed in
place, no revision marks). doc-control refuses a document open
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
import os
import re
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from litcritic import dc, ingest, locate, query, structure, word_live, workspace

FIND_LIMIT = 255  # Word's Find box takes at most 255 characters
HITS_SHOWN = 20
ANCHOR = re.compile(r"(p\d+\.)?(c\d+|front)(\.\w+)*")
# a chapter by its heading's number; roman in capitals only ("mil" or "vi" is a quote)
NUMBER = re.compile(r"\d{1,3}|[IVXLCDM]+")
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
    "SCHEMA_INVALID": "doc_control_too_old",  # an older doc-control rejects "tracked": false
}
MARKED = "this passage still has a marked change from before; accept or reject it in Word first"
TOO_OLD = (
    "the installed doc-control is too old to write changes plainly; "
    "update it (pip install -U 'doc-control>=0.8.4,<0.9')"
)
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


# -- the Find string and writer locators -------------------------------------------


# The Find box's own options for a quote counted as Word counts it: any case, any part
# of a word (doc-control's ``query_word_options`` for that search).
WORD_DEFAULTS = {"match_case": False, "whole_words": False}
# Of the paragraphs, the share that must read as in the ingested draft for its index to
# still place them: an approved change edits one paragraph, a rename a few, and neither
# adds or removes one.
SAME_SHARE = 0.8
READ_TRIES, READ_PAUSE = 5, 0.4  # a file held for a moment (a save, a sync) is read again


def _same_paragraphs(now: list[str], ingested: list[str]) -> bool:
    """Whether the document's paragraphs are still the ingested draft's, one for one: the
    same number, and nearly all with the same text (the tool's own edits change a few)."""
    if len(now) != len(ingested):
        return False
    same = sum(a == b for a, b in zip(now, ingested, strict=True))
    return same >= SAME_SHARE * len(now)


def _read(doc: Path) -> bytes:
    """The document's bytes. Windows refuses a read for a moment while Word saves the
    file or OneDrive syncs it; try again a few times before giving up."""
    for _ in range(READ_TRIES - 1):
        try:
            return doc.read_bytes()
        except PermissionError:
            time.sleep(READ_PAUSE)
    return doc.read_bytes()


class _Places:
    """Find strings and writer locators for spots in the document, from doc-control's
    ``locate``: one call for the whole document, on the first spot asked for, or,
    with ``few`` (one spot will be asked for), a call for each spot's paragraph.

    Locators are only given while the document's paragraphs are still the latest
    ingested draft's, one for one (``_same_paragraphs``: the tool's own edits keep
    them); otherwise the chapter and page could be wrong: `lc ingest` it again.
    The document's paragraphs and addresses are the draft's when its bytes are the
    ingested ones; otherwise the document is read again and compared.
    """

    def __init__(
        self, ws_root: Path, doc: Path, data: bytes, lang: str = "en", *, few: bool = False
    ) -> None:
        self.ix: query.Index | None = None
        self.by_ordinal: dict[int, int] = {}
        self.ordinal_of: dict[int, int] = {}
        self.handle = dc.open(doc)
        self.typed: dict[str, str | None] = {}
        self.few = few
        self._rows: locate.Rows | None = None
        self._some: dict[str, dict[str, Any]] = {}
        try:
            version = structure.latest_version(ws_root)
            ix = query.load(ws_root, version, codex=False)
        except (OSError, ValueError, KeyError, FileNotFoundError):
            return
        ats = _ingested(ws_root, version, data)
        if ats is None or len(ats) != len(ix.paragraphs):
            try:
                draft = ingest.read(doc, data)
            except (OSError, ValueError, KeyError, ingest.IngestError):
                return
            if not _same_paragraphs([p.text for p in draft.paragraphs], ix.paragraphs):
                return
            ats = [p.at for p in draft.paragraphs]
        if not ix.anchors:
            return
        self.ix = ix
        ordinals = [ingest.Para("", at=at).ordinal for at in ats]
        self.by_ordinal = {k: i for i, k in enumerate(ordinals)}
        self.ordinal_of = dict(enumerate(ordinals))
        some = self._rows_of if few else None
        self.locations = locate.Locations(ix, ats, lambda: self.rows, lang, some)

    @property
    def rows(self) -> locate.Rows:
        if self._rows is None:
            self._rows = locate.read_rows(self.handle)
        return self._rows

    def _rows_of(self, ats: list[str]) -> locate.Rows:
        """The rows of these paragraphs (asked one by one with ``few``)."""
        if self._rows is not None or not self.few:
            return {at: self.rows[at] for at in ats if at in self.rows}
        missing = [at for at in ats if at not in self._some]
        if missing:
            self._some.update(locate.read_rows(self.handle, missing))
        return {at: self._some[at] for at in ats if at in self._some}

    def _row(self, at: str) -> dict[str, Any]:
        return self._rows_of([at]).get(at, {})

    def locator(self, ordinal: int) -> dict[str, Any] | None:
        i = self.by_ordinal.get(ordinal)
        if self.ix is None or i is None:
            return None
        return self.locations.locate(self.ix.anchors[i]).as_where()

    def _typed_once(self, text: str) -> str | None:
        """``text`` as typed in Word's Find box (doc-control's ``query_word``, in the
        box's ``^`` codes) when Word's Find, with its default options, meets it exactly
        once in the document; None otherwise."""
        if text not in self.typed:
            req = {"query": text, "ignore_case": True, "limit": 1, "context": 0}
            found = self.handle.run("text.find", req)
            word = found.get("query_word")
            once = int(found.get("total", 0)) == 1
            defaults = found.get("query_word_options") == WORD_DEFAULTS
            self.typed[text] = str(word) if word and once and defaults else None
        return self.typed[text]

    def find(self, at: str, text: str = "") -> dict[str, Any]:
        """What to type in Word's Find to reach ``text`` at ``at`` (a doc-control
        address or range): ``find``, and ``unique`` when Word meets it only there.

        The passage itself, as typed in the Find box, when Word meets it once;
        otherwise doc-control's Find phrase of its paragraph, in the Find box's own
        ``^`` codes (``find_phrase_word``; it may cross a paragraph mark, ``^p``).
        When there is none, the Find phrase of the nearest paragraph before it that
        has one, and ``paragraphs_after``: how far down from there it is.
        """
        typed = self._typed_once(text) if text.strip() and len(text) <= FIND_LIMIT else None
        if typed:
            return {"find": typed, "unique": True}
        row = self._row(at.split(":")[0])
        if row.get("find_phrase_word"):  # doc-control's phrase as typed in Word's Find box
            return {"find": str(row["find_phrase_word"]), "unique": True}
        context = row.get("context") or {}
        out: dict[str, Any] = {"find": str(context.get("after_word") or ""), "unique": False}
        if context:
            out["paragraphs_after"] = int(context.get("paragraphs_after", 0))
        return out

    def hit(self, at: str, text: str, why: str = "") -> dict[str, Any]:
        out: dict[str, Any] = {"text": text, **self.find(at, text)}
        m = ADDRESS.fullmatch(at)
        out["locator"] = self.locator(int(m.group(1)) - 1) if m else None
        if why:
            out["reason"] = why
        return out


def _ingested(ws_root: Path, version: str, data: bytes) -> list[str] | None:
    """The paragraph addresses of ``version`` when ``data`` is the very file it was
    ingested from (same bytes, so the same paragraphs); None otherwise."""
    try:
        meta = json.loads((ws_root / "text" / f"{version}.meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    digest = hashlib.sha256(data).hexdigest()
    if meta.get("format") != "docx" or meta.get("source_sha256") != digest:
        return None
    ats = [str(p.get("at", "")) for p in meta.get("paragraphs", [])]
    return ats if all(ats) else None


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
    req = {"doc": str(doc), "anchor": anchor, "mode": "exact", "match_level": "exact"}
    try:
        return str(dc.run("anchor.resolve", req)["at"])
    except dc.DocError as exc:
        if exc.code == "ANCHOR_NOT_FOUND":
            raise NotOnce(0) from exc
        if exc.code == "ANCHOR_AMBIGUOUS":
            raise NotOnce(max(len(exc.details.get("candidates", [])), 2)) from exc
        raise


def _live_paragraph(doc: Path, phrase: str) -> tuple[str, str]:
    """(text, address) of the one paragraph holding ``phrase`` in the document open in
    Word, found by ``live.select`` without bringing Word to the front."""
    request = {"doc": str(doc), "find_phrase": phrase, "match_level": "exact"}
    try:
        got = word_live.run("live.select", {**request, "mode": "cursor", "front": False})
    except dc.DocError as exc:
        if exc.code == "ANCHOR_NOT_FOUND":
            raise NotOnce(0) from exc
        if exc.code == "ANCHOR_AMBIGUOUS":
            raise NotOnce(2) from exc
        raise
    return str(got.get("text") or ""), str(got.get("at") or "")


def _live_spot(doc: Path, quote: str, prefix: str = "", suffix: str = "") -> tuple[str, str, int]:
    """(paragraph text, address, start of ``quote`` in it) in the document open in Word,
    which may hold edits not yet saved: the paragraph is found by the quote, or with its
    context when the quote alone is not once."""
    context = prefix + quote + suffix
    try:
        text, at = _live_paragraph(doc, quote)
    except NotOnce as exc:
        if exc.count < 2 or context == quote:
            raise
        text, at = _live_paragraph(doc, context)
    if text.count(quote) == 1:
        return text, at, text.index(quote)
    if text.count(context) == 1 and context != quote:
        return text, at, text.index(context) + len(prefix)
    raise NotOnce(text.count(quote))


def _resolve_live(doc: Path, quote: str, prefix: str = "", suffix: str = "") -> str:
    """The range of ``quote`` in the document open in Word (see ``_live_spot``)."""
    _text, at, start = _live_spot(doc, quote, prefix, suffix)
    return f"{at}:{start}-{start + len(quote)}"


PIN = 40  # characters kept on each side of a change's quote to pin its place
FIND_MAX = 250  # Word's Find takes at most 255 characters


def _place(doc: Path, quote: str, before: str, after: str, live: bool) -> tuple[str, str, int]:
    """(paragraph address, its text, start of ``quote`` in it) of the one place holding
    ``before + quote + after``, all of it: a place whose words around the quote were
    edited is not found, rather than another place holding the same quote."""
    phrase = before + quote + after
    if live:
        text, at, start = _live_spot(doc, phrase)
    else:
        at, span = _resolve(doc, phrase).rsplit(":", 1)
        text = str(dc.run("para.get", {"doc": str(doc), "at": at}).get("text") or "")
        start = int(span.split("-")[0])
    return at, text, start + len(before)


def _rewritten(spots: list[tuple[str, str, str]], texts: dict[str, str]) -> dict[str, str]:
    """Each written edit's paragraph address once the batch is in: the paragraph number
    with the fingerprint of its text as the edits leave it."""
    out: dict[str, str] = {}
    for para, text in texts.items():
        mine = sorted(
            (
                (int(m.group(3)), int(m.group(4)), eid, replace)
                for at, eid, replace in spots
                if at.rsplit(":", 1)[0] == para and (m := ADDRESS.fullmatch(at))
            ),
            reverse=True,
        )
        for start, end, _eid, replace in mine:
            text = text[:start] + replace + text[end:]
        new = f"{para.split('#')[0]}#{dc.fingerprint(text)}"
        out.update({eid: new for _s, _e, eid, _r in mine})
    return out


def _around(text: str, start: int, end: int, wide: int) -> tuple[str, str]:
    """The words of ``text`` just before ``start`` and just after ``end``: up to ``wide``
    characters each side, cut at a space and at any control character, and short enough
    for Word to find the whole phrase."""
    wide = min(wide, max(0, FIND_MAX - (end - start)) // 2)
    lo, hi = max(0, start - wide), min(len(text), end + wide)
    if lo > 0 and not text[lo - 1].isspace() and (cut := text.find(" ", lo, start)) != -1:
        lo = cut + 1
    if hi < len(text) and not text[hi].isspace() and (cut := text.rfind(" ", end, hi)) != -1:
        hi = cut
    before, after = text[lo:start], text[end:hi]
    before = re.split(r"[\x00-\x1f]", before)[-1]
    after = re.split(r"[\x00-\x1f]", after)[0]
    return before, after


def pin(doc: Path, quote: str, prefix: str = "", suffix: str = "") -> tuple[str, str]:
    """The words around the one place holding ``quote`` (found with the chat's ``prefix``
    and ``suffix``), kept with a change so that applying it checks that place is still as
    it was. Read in Word when it has the document open (edits not saved yet count), else
    in the file. Raises ``NotOnce`` when the place is not once, the words included."""
    wide = max(PIN, len(prefix), len(suffix))
    live = word_live.is_open(doc)
    if live:
        try:
            text, _at, start = _live_spot(doc, quote, prefix, suffix)
        except dc.DocError:
            live = False
    if not live:
        para, span = _resolve(doc, quote, prefix, suffix).rsplit(":", 1)
        text = str(dc.run("para.get", {"doc": str(doc), "at": para}).get("text") or "")
        start = int(span.split("-")[0])
    before, after = _around(text, start, start + len(quote), wide)
    _place(doc, quote, before, after, live)  # the pinned words are once too
    return before, after


def confirm(doc: Path, at: str, live: bool) -> bool:
    """Whether the paragraph at ``at`` reads as the address says (its number, and the
    fingerprint of its text): a write read back at the very place it went."""
    try:
        if live:
            word_live.run(
                "live.select", {"doc": str(doc), "at": at, "mode": "cursor", "front": False}
            )
        else:
            dc.run("para.get", {"doc": str(doc), "at": at, "limit": 1})
    except dc.DocError:
        return False
    return True


def _sha256(doc: Path) -> str:
    return hashlib.sha256(_read(doc)).hexdigest()


def _why(exc: dc.DocError, doc: Path) -> tuple[str, str]:
    """(reason, message for the writer) of a doc-control refusal."""
    reason = REASONS.get(exc.code, exc.code.lower())
    if exc.code == "UNSUPPORTED_CONTENT" and "unresolved tracked" in str(exc.message):
        return "marked", MARKED
    if reason == "doc_control_too_old":
        return reason, TOO_OLD
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
    info = dc.run("doc.info", {"doc": str(doc)})
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
    reasons = {str(e["id"]): str(e.get("reason", "")) for e in items}
    payload, code = apply_edits(root, doc, edits, reasons, args.dry_run)
    return _out(payload, code)


Edit = tuple[str, str, str, str, str]  # id, quote, replace, prefix, suffix


WORD_NEEDED = "Word could not open the document, so nothing was written: the writer types it"
WORD_ONLY_ENV = "LITCRITIC_WORD_ONLY"  # set by the desktop extension's server (lc mcp)


def word_only_env() -> bool:
    """Whether this process may change the manuscript only through Word."""
    return os.environ.get(WORD_ONLY_ENV) == "1"


def apply_edits(
    root: Path,
    doc: Path,
    edits: list[Edit],
    reasons: dict[str, str] | None = None,
    dry_run: bool = False,
    word_only: bool = False,
    pinned: bool = False,
) -> tuple[dict[str, Any], int]:
    """The one write path for approved edits: resolve each quote once, then one plain
    batch with backup, ``expect.sha256`` and verify-and-restore, and a line in
    ``log/edits.jsonl``. Returns the answer and its exit code (0 applied, 1 refused).
    ``word_only`` (the desktop extension) never writes the file: a closed document is
    opened in Word first, and without Word the edit is refused (``word_needed``).
    ``pinned``: each edit's prefix and suffix are the words around it that must all
    still be there (``pin``), not hints that pick among several places."""
    ids = [e[0] for e in edits]
    base = {"document": _shown(root, doc), "author": AUTHOR}

    def refused(
        reason: str, message: str, problems: dict[str, str] | None = None
    ) -> tuple[dict[str, Any], int]:
        return _refused(base, reason, message, problems or {}, ids), 1

    if not doc.is_file():
        return refused("missing", f"{doc} does not exist")
    live = not dry_run and word_live.is_open(doc)
    if (word_only or word_only_env()) and not dry_run and not live:
        live = word_live.open_if_closed(doc) and word_live.is_open(doc)
        if not live:
            return refused("word_needed", WORD_NEEDED)
    texts: dict[str, str] = {}  # pinned: each paragraph's text as found, by address

    def resolve_pinned(doc: Path, quote: str, before: str = "", after: str = "") -> str:
        at, text, start = _place(doc, quote, before, after, live)
        texts[at] = text
        return f"{at}:{start}-{start + len(quote)}"

    resolve = resolve_pinned if pinned else _resolve_live if live else _resolve
    # The file as it is now, taken before the quotes are found in it: a save in Word
    # since the tool last read it is the writer's own work, and each quote must still be
    # there once; ``expect`` then guards only against a change during this call.
    fresh = "" if live or dry_run else hashlib.sha256(_read(doc)).hexdigest()
    problems: dict[str, str] = {}
    spots: list[tuple[str, str, str]] = []  # (range, id, replacement)
    for eid, quote, replace, prefix, suffix in edits:
        if not quote.strip():
            problems[eid] = "empty quote"
            continue
        try:
            spots.append((resolve(doc, quote, prefix, suffix), eid, replace))
        except NotOnce as exc:
            problems[eid] = str(exc) + ("; add context" if exc.count else "")
        except dc.DocError as exc:
            if not live:
                raise
            return refused(*_why(exc, doc))
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
    batch: dict[str, Any] = {"doc": str(doc), "ops": ops, "author": AUTHOR, "tracked": False}
    if live:
        answer, code = _apply_live(root, doc, batch, ids, reasons, base, refused)
        if code == 0 and pinned:
            answer["places"] = _rewritten(spots, texts)
        return answer, code
    last = ingest.last_read(root, doc)
    if not dry_run and not last:
        return refused(*_unread(doc))
    try:
        if dry_run:
            dc.run("doc.batch", {**batch, "dry_run": True})
            st = _state(root, doc)
            return {
                "status": "dry_run",
                "applied": ids,
                "skipped": [],
                "revisions": len(ids),
                "locked": st["locked"],
                "changed_on_disk": st["changed_on_disk"],
                **base,
            }, 0
        result = dc.run("doc.batch", {**batch, "expect": {"sha256": fresh}})
    except dc.DocError as exc:
        reason, message = _why(exc, doc)
        para = str(exc.details.get("paragraph", ""))
        named = {eid: message for at, eid, _ in spots if para and at.startswith(para + ":")}
        return refused(reason, message, named)
    log: dict[str, Any] = {"command": "edits", "edit_ids": ids}
    log["reasons"] = {eid: (reasons or {}).get(eid, "") for eid in ids}
    backup = _written(root, doc, fresh, result, log)
    done: dict[str, Any] = {
        "status": "applied",
        "applied": ids,
        "skipped": [],
        "backup": _shown(root, backup),
        "revisions": len(ids),
        **base,
    }
    if pinned:
        done["places"] = _rewritten(spots, texts)
    return done, 0


def _apply_live(
    root: Path,
    doc: Path,
    batch: dict[str, Any],
    ids: list[str],
    reasons: dict[str, str] | None,
    base: dict[str, Any],
    refused: Callable[..., tuple[dict[str, Any], int]],
) -> tuple[dict[str, Any], int]:
    """The document is open in Word (or LibreOffice): the same plain batch goes into the
    open document. The live engine has no backup, no ``expect`` and no all-or-nothing;
    the app's own undo takes it back, and nothing is written to the file until the writer
    saves."""
    try:
        word_live.write(batch)
    except dc.DocError as exc:
        reason, message = _why(exc, doc)
        return refused(reason, message)
    entry = {
        "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "document": str(doc),
        "backup": "",
        "how": "live",
        "command": "edits",
        "edit_ids": ids,
        "reasons": {eid: (reasons or {}).get(eid, "") for eid in ids},
    }
    f = root / "log" / "edits.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {
        "status": "applied",
        "applied": ids,
        "skipped": [],
        "backup": None,
        "how": "live",
        "revisions": 0,
        **base,
    }, 0


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
        "tracked": False,
    }
    try:
        plan = dc.run("term.rename", {**req, "dry_run": True, "preview_limit": 200})
    except dc.DocError as exc:
        return refused(*_why(exc, doc))
    counts = plan.get("counts", {})
    if not counts.get("matches"):
        return refused("edit", f"{args.old!r} does not appear in the document")
    hits = plan.get("preview", [])
    left: list[dict[str, Any]] = []
    places = _Places(root, doc, _read(doc), args.lang)
    if counts.get("skipped_unsupported") or counts.get("skipped_boundary"):
        # doc-control counts the occurrences it leaves alone; find says where they are.
        found = dc.run(
            "text.find",
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


def _found(
    args: argparse.Namespace, root: Path, doc: Path, places: _Places, raw: str
) -> dict[str, Any]:
    """Where one target is (``status: ok``), or why it cannot be found (``refused``)."""

    def refused(reason: str, message: str) -> dict[str, Any]:
        return {"status": "refused", "reason": reason, "message": message}

    target = raw.strip()
    if not args.quote and NUMBER.fullmatch(target):
        if places.ix is None:
            why = "the novel has no index yet; run `lc ingest` and `lc anchor` first"
            return refused("changed", why)
        try:
            target = query.numbered_chapter(places.ix, target)
        except KeyError as exc:
            return refused("chapter", exc.args[0])
    i = None
    if not args.quote and ANCHOR.fullmatch(target) and places.ix is not None:
        try:
            i = query.paragraph_range(places.ix, target).start
        except KeyError:
            i = None
    if i is not None:
        k, at, text = places.ordinal_of[i], places.locations.ats[i], ""
    else:
        try:
            at = _resolve(doc, raw)
        except NotOnce as exc:
            if not exc.count and not args.quote and ANCHOR.fullmatch(target) and places.ix is None:
                why = (
                    "the document no longer matches the last ingested draft; "
                    "run `lc ingest` and `lc anchor` on it first"
                )
                return refused("changed", why)
            return refused("quote", str(exc) + ("; quote more words" if exc.count else ""))
        m = ADDRESS.fullmatch(at)
        k, text = (int(m.group(1)) - 1 if m else -1), raw
    return {
        "status": "ok",
        "document": _shown(root, doc),
        # for `lc word locate`: the file where lc runs, and the paragraph's address
        "path": str(doc.resolve()),
        "at": at.split(":")[0],
        **places.find(at, text),
        "locator": places.locator(k),
    }


def _locate(args: argparse.Namespace, root: Path) -> int:
    doc = _document(root, args.document)
    if not doc.is_file():
        return _out({"status": "refused", "reason": "missing", "message": f"{doc} not found"}, 1)
    places = _Places(root, doc, _read(doc), args.lang, few=True)
    found = _found(args, root, doc, places, args.target)
    if found["status"] != "ok":
        return _out(found, 1)
    if args.go:
        # one step for "take me there": `lc word locate` on this answer, in the same process
        from litcritic import word_live

        return _out(word_live.call("locate", {**found, "language": args.lang}))
    return _out(found)


def _places(args: argparse.Namespace, root: Path) -> int:
    """A list of places as doc-control's ``live_places`` call: one button each in Word."""
    from litcritic import word_live

    doc = _document(root, args.document)
    if not doc.is_file():
        return _out({"status": "refused", "reason": "missing", "message": f"{doc} not found"}, 1)
    places = _Places(root, doc, _read(doc), args.lang, few=len(args.targets) <= 3)
    shown, missing, lines = [], [], []
    for target in args.targets:
        found = _found(args, root, doc, places, target)
        if found["status"] != "ok":
            missing.append({"target": target, **{k: found[k] for k in ("reason", "message")}})
            continue
        place = word_live.place(found, args.lang)
        shown.append(place)
        lines.append(f"{len(shown)}. {place['label']}")
    if not shown:
        return _out({"status": "refused", "reason": "none", "missing": missing}, 1)
    arguments = {"doc": doc.name, "places": shown, "mode": "cursor"}
    live = {"tool": "live_places", "arguments": arguments}
    out: dict[str, Any] = {"status": "ok", "document": _shown(root, doc), "live": live}
    out["writer"] = "\n".join(lines)
    if missing:
        out["missing"] = missing
    return _out(out)


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
        result = dc.run("history.undo", req)
    except dc.DocError as exc:
        reason, message = _why(exc, doc)
        if reason == "nothing":
            message = "there is no edit of the tool left to undo in this document"
        return refused(reason, message)
    out = {"undid": result.get("undid"), "paragraphs": result.get("paragraphs", 0)}
    if args.dry_run:
        return _out({"status": "dry_run", **out, "backup": None, **base})
    backup = _written(root, doc, last, result, {"command": "undo", "undid": out["undid"]})
    answer: dict[str, Any] = {"status": "undone", **out, "backup": _shown(root, backup), **base}
    change_id = _undone_change(root, str(out["undid"] or ""))
    if change_id:
        answer["change"] = change_id
    return _out(answer)


def _undone_change(root: Path, op_id: str) -> str | None:
    """Log ``change.undone`` when the edit just taken back came from ``lc change approve``."""
    if not op_id:
        return None
    f = root / "log" / "edits.jsonl"
    if not f.is_file():
        return None
    ids: list[str] = []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("command") == "edits" and e.get("op_id") == op_id:
            ids = [str(i) for i in e.get("edit_ids", [])]
    from litcritic import change

    return change.mark_undone(root, ids, op_id)


COMMANDS = {
    "edits": _edits,
    "rename": _rename,
    "locate": _locate,
    "places": _places,
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
    p = sub.add_parser(
        "docx", help="edit the writer's Word file in place (a backup is kept; undo takes it back)"
    )
    dsub = p.add_subparsers(dest="docx_cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--workspace", required=True, help="workspace folder or slug")
        sp.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
        sp.add_argument("--document", default=None, help="the .docx (default: last one read)")
        sp.set_defaults(func=_run)

    p_ed = dsub.add_parser("edits", help="apply approved edits to the file (with a backup)")
    p_ed.add_argument("--edits", required=True, help="edits.json (see docs)")
    p_ed.add_argument("--dry-run", action="store_true", help="check only, write nothing")
    common(p_ed)
    p_rn = dsub.add_parser("rename", help="rename a whole word everywhere (with a backup)")
    p_rn.add_argument("old")
    p_rn.add_argument("new")
    case = p_rn.add_mutually_exclusive_group()
    case.add_argument("--case-sensitive", action="store_true", help="the default")
    case.add_argument("--ignore-case", action="store_true", help="also other capitalisations")
    p_rn.add_argument("--dry-run", action="store_true", help="list the hits, write nothing")
    common(p_rn)
    p_lo = dsub.add_parser("locate", help="the Word Find string and writer locator of a passage")
    p_lo.add_argument(
        "target",
        help="a paragraph anchor (c03.s1.p4), a chapter or scene (c03, c03.s1), "
        "the number in a chapter's heading (15 or XV), or a quote from the text",
    )
    p_lo.add_argument("--quote", action="store_true", help="search the target as text only")
    p_lo.add_argument(
        "--go",
        action="store_true",
        help="also take the open Word there: print what `lc word locate` would",
    )
    common(p_lo)
    p_pl = dsub.add_parser(
        "places", help="a list of places as doc-control's live_places buttons (one per place)"
    )
    p_pl.add_argument("targets", nargs="+", help="each as `lc docx locate` takes it")
    p_pl.add_argument("--quote", action="store_true", help="search every target as text only")
    common(p_pl)
    p_st = dsub.add_parser("status", help="is the document open, changed, backed up")
    common(p_st)
    p_un = dsub.add_parser("undo", help="take back the tool's last edit or rename")
    p_un.add_argument("--dry-run", action="store_true", help="check only, write nothing")
    common(p_un)
