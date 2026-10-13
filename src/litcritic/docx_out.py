"""A copy of the writer's .docx with each action as an anchored comment.

The original file is never modified: the copy is written next to the round's
actions. Paragraphs are found by their position among the document's ``w:p``
elements, recorded at ingest time; doc-control numbers the same paragraphs
``p1``, ``p2``, ... and writes all the comments as one ``batch`` of
``comment.add``, so no Word XML is handled here.
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from litcritic import dc, ingest, query, rounds
from litcritic.codex import Codex

AUTHOR = "literary-critic"


class DocxError(Exception):
    """The comments copy cannot be made."""


def _addresses(path: Path) -> list[str]:
    """Doc-control's address of every paragraph of the file, in document order."""
    out: list[str] = []
    cursor: str | None = None
    while True:
        request: dict[str, Any] = {"doc": str(path), "limit": 1000}
        if cursor:
            request["cursor"] = cursor
        result = dc.run("text.normalized", request)
        for entry in result["paragraphs"]:
            if not out or out[-1] != entry["at"]:  # a long paragraph comes as several entries
                out.append(entry["at"])
        cursor = result.get("_next")
        if not cursor:
            return out


def add_comments(path: Path, targets: dict[int, list[str]]) -> int:
    """Add comments, in place, to the paragraphs at the given w:p ordinals.

    ``targets`` maps a paragraph ordinal (as counted by ingest) to the
    comment's lines. All comments are written as one all-or-nothing batch.
    Returns how many comments were added.
    """
    try:
        addresses = _addresses(path)
        ops: list[dict[str, Any]] = []
        for ordinal in sorted(targets):
            if ordinal >= len(addresses):
                raise DocxError(f"paragraph {ordinal} is not in the document")
            if not addresses[ordinal].startswith(f"p{ordinal + 1}#"):
                raise DocxError("could not map the document's paragraphs safely; no comments added")
            ops.append(
                {"op": "comment.add", "at": addresses[ordinal], "text": "\n".join(targets[ordinal])}
            )
        if ops:
            dc.run("batch", {"doc": str(path), "ops": ops, "author": AUTHOR})
    except dc.DocError as exc:
        raise DocxError(str(exc)) from exc
    return len(ops)


def comment_lines(action: dict[str, Any], lang: str) -> list[str]:
    t = rounds.TEXT.get(lang, rounds.TEXT["en"])
    return [
        f"[{action['id']}] {action['what']}",
        f"{t['why']}: {action['why']}",
        f"{t['options']}: " + " / ".join(action["options"]),
    ]


def build(ws_root: Path, version: str | None = None) -> tuple[Path, int]:
    """Write ``revisions/round-NN/<draft>-comments.docx`` for the latest round.

    Comments go on the Codex's synced draft, where the issues' spans point;
    actions whose passage is gone, or that the writer already closed, get none.
    """
    round_dir = rounds.latest_round(ws_root)
    cx = Codex(ws_root)
    if version and version != cx.draft:
        raise DocxError(f"the Codex is synced to {cx.draft}; run `lc codex sync` first")
    version = cx.draft
    snapshot = ws_root / "manuscript" / f"{version}.docx"
    if not snapshot.is_file():
        raise DocxError(f"draft {version} is not a .docx; comments need a Word file")
    data = snapshot.read_bytes()
    try:
        draft = ingest.read_docx(data)
        ix = query.load(ws_root, version)
    except (ingest.IngestError, zipfile.BadZipFile) as exc:
        raise DocxError(str(exc)) from exc
    if [p.text for p in draft.paragraphs] != ix.paragraphs:
        raise DocxError(f"{snapshot.name} no longer matches text/{version}.txt; re-ingest it")
    lang = rounds.language(ws_root)
    index_of = {a: i for i, a in enumerate(ix.anchors)}
    targets: dict[int, list[str]] = {}
    for action in rounds.round_actions(ws_root, round_dir, cx):
        if action["status"] not in ("pending", "accepted") or not action["where"]:
            continue
        anchor = action["where"]["anchor"]
        if anchor not in index_of:
            raise DocxError(f"{action['id']}: {anchor} is not in {version}")
        ordinal = draft.paragraphs[index_of[anchor]].src
        targets[ordinal] = [*targets.get(ordinal, []), *comment_lines(action, lang)]
    out = round_dir / f"{version}-comments.docx"
    with tempfile.TemporaryDirectory() as tmp:  # doc-control keeps backups beside the file
        work = Path(tmp) / out.name
        work.write_bytes(data)
        add_comments(work, targets)
        shutil.copyfile(work, out)
    return out, len(targets)
