"""A reviewer's notes on the novel: the comments and tracked changes of a Word file.

An editor or a reader returns a copy of the manuscript with comments and tracked
changes. ``lc notes`` reads all of them in one pass (doc-control's ``comment.list`` and
``revision.list``), saves them under ``notes/`` in the workspace and prints them a page
at a time, each placed at the paragraph of the current draft it belongs to. The saved
copy is reused while the file is unchanged, so a conversation that drops halfway picks
up at the next page without reading the document again.
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
FORMAT = 1  # bump when the saved shape changes, so old copies are read again
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


def _changes(revs: list[dict[str, Any]]) -> list[str]:
    """A paragraph's tracked changes as the writer reads them: a deletion followed by an
    insertion is one replacement, ``old → new``."""
    out: list[str] = []
    i = 0
    while i < len(revs):
        kind, text = revs[i].get("type"), str(revs[i].get("text") or "")
        nxt = revs[i + 1] if i + 1 < len(revs) else None
        if nxt and {kind, nxt.get("type")} == {"delete", "insert"}:
            old, new = (text, nxt.get("text")) if kind == "delete" else (nxt.get("text"), text)
            out.append(f"{str(old).strip()} → {str(new or '').strip()}")
            i += 2
            continue
        sign = {"delete": "deleted: ", "insert": "added: "}.get(str(kind), f"{kind}: ")
        out.append(f"{sign}{text.strip()}")
        i += 1
    return out


def extract(path: Path, draft: _Draft | None) -> dict[str, Any]:
    """Every comment and tracked change of ``path``, in document order."""
    try:
        with dc.open(path) as doc:
            paras = {int(p["number"]): str(p.get("text") or "") for p in doc.paragraphs()}
            comments = doc.run("comment.list").get("comments") or []
            revisions = doc.run("revision.list").get("revisions") or []
    except dc.DocError as exc:
        raise NotesError(str(exc)) from exc
    edits: dict[tuple[int | None, str], list[dict[str, Any]]] = defaultdict(list)
    for r in revisions:
        if r.get("type") in ("insert", "delete"):  # formatting and moves are not wording
            edits[(_number(r.get("at")), str(r.get("author") or ""))].append(r)
    rows: list[tuple[int, int, dict[str, Any]]] = []
    for c in comments:
        note = {"kind": "comment", "author": c.get("author") or "", "text": c.get("text") or ""}
        if c.get("resolved"):
            note["resolved"] = True
        rows.append((_number(c.get("at")) or 0, 0, {"p": _number(c.get("at")), **note}))
    for (num, author), revs in edits.items():
        edit = {"p": num, "kind": "edit", "author": author, "changes": _changes(revs)}
        rows.append((num or 0, 1, edit))
    rows.sort(key=lambda r: (r[0], r[1]))
    placed: dict[int, str | None] = {}
    last: str | None = None
    notes: list[dict[str, Any]] = []
    for _, _, note in rows:
        num = note.pop("p")
        text = paras.get(num, "") if num else ""
        if num and draft and num not in placed:
            placed[num] = draft.place(text)
        anchor = placed.get(num) if num else None
        where: dict[str, Any] = {"at": anchor} if anchor else {"near": last} if last else {}
        last = anchor or last
        words = text.split()
        if words:
            where["starts"] = " ".join(words[:ENDS])
            if len(words) > ENDS:
                where["ends"] = " ".join(words[-ENDS:])
        notes.append({"n": len(notes) + 1, **note, **where})
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
