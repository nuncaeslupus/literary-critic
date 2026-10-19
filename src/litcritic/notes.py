"""A reviewer's notes on the novel: the comments and tracked changes of a Word file.

An editor or a reader returns a copy of the manuscript with comments and tracked
changes. ``lc notes`` reads all of them in one pass (doc-control's ``review.list``),
saves them under ``notes/`` in the workspace and prints them a page at a time, each
placed at the paragraph of the current draft it belongs to. The saved copy is reused
while the file is unchanged, so a conversation that drops halfway picks up at the next
page without reading the document again.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from litcritic import dc, ingest, query, structure
from litcritic.textstats import strip_accents

PAGE = 30  # notes per page: enough to work through, small enough for a chat turn
FORMAT = 2  # bump when the saved shape changes, so old copies are read again
SHINGLE = 4  # words per shingle when matching a paragraph to the current draft
MATCH_SHARE = 0.3  # share of a paragraph's shingles the draft paragraph must share
ENDS = 6  # words quoted at each end of a paragraph
KINDS = ("comment", "edit")

_PARA = re.compile(r"p(\d+)")
_WORD = re.compile(r"\w+")


class NotesError(Exception):
    """The notes cannot be read."""


def folder(ws_root: Path) -> Path:
    """Where the novel's documents are: the latest draft's folder, else the novel's."""
    docs = ingest.known_documents(ws_root)
    return docs[-1].parent if docs else ws_root.resolve().parent


def candidates(ws_root: Path) -> list[str]:
    """Word files beside the manuscript that are not a draft the tool has read."""
    known = {d.resolve() for d in ingest.known_documents(ws_root)}
    base = folder(ws_root)
    try:
        files = sorted(base.glob("*.docx"))
    except OSError:
        return []
    return [f.name for f in files if f.resolve() not in known and not f.name.startswith("~$")]


def resolve(ws_root: Path, name: str) -> Path:
    path = Path(name).expanduser()
    if not path.is_absolute():
        path = folder(ws_root) / path
    if not path.is_file():
        raise NotesError(f"no file {name!r} in {folder(ws_root)}")
    if path.suffix.lower() != ".docx":
        raise NotesError("only a Word file (.docx) carries comments and tracked changes")
    return path.resolve()


def _fold(text: str) -> list[str]:
    return _WORD.findall(strip_accents(text).casefold())


def _shingles(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


@dataclass
class _Draft:
    """The current draft's paragraphs, to place each note in it."""

    anchors: list[str]
    exact: dict[tuple[str, ...], int]
    shingles: dict[tuple[str, ...], list[int]]

    @classmethod
    def of(cls, ws_root: Path) -> _Draft | None:
        try:
            ix = query.load(ws_root, structure.latest_version(ws_root), codex=False)
        except (OSError, ValueError, KeyError):
            return None  # not indexed yet: notes carry their words only
        exact: dict[tuple[str, ...], int] = {}
        shingles: dict[tuple[str, ...], list[int]] = defaultdict(list)
        for i, text in enumerate(ix.paragraphs):
            words = _fold(text)
            exact.setdefault(tuple(words), i)
            for s in _shingles(words):
                shingles[s].append(i)
        return cls(ix.anchors, exact, shingles)

    def place(self, text: str) -> str | None:
        """The anchor of the draft paragraph that reads like ``text``, if one does."""
        words = _fold(text)
        if not words:
            return None
        if tuple(words) in self.exact:
            return self.anchors[self.exact[tuple(words)]]
        mine = _shingles(words)
        if not mine:
            return None
        votes: Counter[int] = Counter()
        for s in mine:
            votes.update(self.shingles.get(s, ()))
        if not votes:
            return None
        best, count = votes.most_common(1)[0]
        return self.anchors[best] if count >= MATCH_SHARE * len(mine) else None


def _number(at: Any) -> int | None:
    m = _PARA.match(str(at or ""))
    return int(m.group(1)) if m else None


def _change(c: dict[str, Any]) -> str:
    """A tracked change as the writer reads it: ``old → new``, or what was added or deleted."""
    if c.get("type") == "replace":
        return f"{str(c.get('old') or '').strip()} → {str(c.get('new') or '').strip()}"
    sign = {"delete": "deleted: ", "insert": "added: "}.get(str(c.get("type")), "")
    return f"{sign}{str(c.get('text') or '').strip()}"


def _comment(c: dict[str, Any]) -> dict[str, Any]:
    note: dict[str, Any] = {"kind": "comment", "author": c.get("author") or ""}
    if c.get("quote"):
        note["on"] = c["quote"]  # the words the comment is on
    note["text"] = c.get("text") or ""
    if c.get("resolved"):
        note["resolved"] = True
    replies = [f"{r.get('author') or ''}: {r.get('text') or ''}" for r in c.get("replies") or []]
    if replies:
        note["replies"] = replies
    return note


def extract(path: Path, draft: _Draft | None) -> dict[str, Any]:
    """Every comment and tracked change of ``path``, in document order (doc-control's
    ``review.list``: comments with their quotes, a deletion and its insertion as one)."""
    try:
        with dc.open(path) as doc:
            paras = {int(p["number"]): str(p.get("text") or "") for p in doc.paragraphs()}
            groups = doc.run("review.list").get("paragraphs") or []
    except dc.DocError as exc:
        raise NotesError(str(exc)) from exc
    last: str | None = None
    notes: list[dict[str, Any]] = []
    for group in groups:
        num = _number(group.get("at"))
        found = [_comment(c) for c in group.get("comments") or []]
        edits: dict[str, list[str]] = {}
        for c in group.get("changes") or []:
            edits.setdefault(str(c.get("author") or ""), []).append(_change(c))
        found += [{"kind": "edit", "author": a, "changes": ch} for a, ch in edits.items()]
        text = paras.get(num, "") if num else ""
        anchor = draft.place(text) if num and draft else None
        where: dict[str, Any] = {"at": anchor} if anchor else {"near": last} if last else {}
        last = anchor or last
        words = text.split()
        if words:
            where["starts"] = " ".join(words[:ENDS])
            if len(words) > ENDS:
                where["ends"] = " ".join(words[-ENDS:])
        notes += [{"n": len(notes) + k + 1, **note, **where} for k, note in enumerate(found)]
    return {"format": FORMAT, "notes": notes}


def _saved(ws_root: Path, path: Path) -> Path:
    return ws_root / "notes" / f"{path.stem}.json"


def load(ws_root: Path, path: Path) -> dict[str, Any]:
    """The notes of ``path``: the saved copy while the file is unchanged, else read now."""
    st = path.stat()
    stamp = {"source": path.name, "size": st.st_size, "mtime_ns": st.st_mtime_ns}
    saved = _saved(ws_root, path)
    try:
        data: dict[str, Any] = json.loads(saved.read_text(encoding="utf-8"))
        if data.get("format") == FORMAT and all(data.get(k) == v for k, v in stamp.items()):
            return data
    except (OSError, ValueError):
        pass
    data = {**stamp, **extract(path, _Draft.of(ws_root))}
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return data


def page(data: dict[str, Any], number: int = 1, kind: str = "", author: str = "") -> dict[str, Any]:
    """One page of the notes, with the totals the writer is told first."""
    notes = data["notes"]
    totals: dict[str, Counter[str]] = defaultdict(Counter)
    for n in notes:
        totals[n["author"]][n["kind"]] += 1
    picked = [
        n
        for n in notes
        if (not kind or n["kind"] == kind) and (not author or n["author"] == author)
    ]
    pages = max(1, -(-len(picked) // PAGE))
    if not 1 <= number <= pages:
        raise NotesError(f"page {number} does not exist; there are {pages}")
    out: dict[str, Any] = {
        "source": data["source"],
        "authors": {a: dict(c) for a, c in totals.items()},
        "placed": sum(1 for n in notes if "at" in n),
        "notes": len(picked),
        "page": number,
        "pages": pages,
        "items": picked[(number - 1) * PAGE : number * PAGE],
    }
    if number < pages:
        out["next"] = f"--page {number + 1}"
    return out
