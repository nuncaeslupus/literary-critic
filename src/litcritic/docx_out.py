"""A copy of the writer's .docx with each action as an anchored comment.

The original file is never modified: the copy is written next to the round's
actions. Paragraphs are named by their doc-control address (``at``), read at
ingest time; doc-control writes all the comments as one ``batch`` of
``comment.add``, so no Word XML is handled here.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from litcritic import dc, ingest, query, rounds
from litcritic.codex import Codex

AUTHOR = "literary-critic"


class DocxError(Exception):
    """The comments copy cannot be made."""


def add_comments(path: Path, targets: dict[str, list[str]]) -> int:
    """Add comments, in place, to the paragraphs at the given doc-control addresses.

    ``targets`` maps a paragraph address (``p142#a7b2a7b2``, as read at ingest) to
    the comment's lines. All comments are written as one all-or-nothing batch;
    doc-control refuses an address whose paragraph changed. Returns how many
    comments were added.
    """
    ops = [
        {"op": "comment.add", "at": at, "text": "\n".join(lines)}
        for at, lines in sorted(targets.items(), key=lambda t: _number(t[0]))
    ]
    try:
        if ops:
            dc.run("batch", {"doc": str(path), "ops": ops, "author": AUTHOR})
    except dc.DocError as exc:
        raise DocxError(str(exc)) from exc
    return len(ops)


def _number(at: str) -> int:
    """The paragraph number of an address, so comments go in document order."""
    m = re.match(r"p(\d+)#", at)
    return int(m.group(1)) if m else 0


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
        draft = ingest.read(snapshot, data)
        ix = query.load(ws_root, version)
    except ingest.IngestError as exc:
        raise DocxError(str(exc)) from exc
    if [p.text for p in draft.paragraphs] != ix.paragraphs:
        raise DocxError(f"{snapshot.name} no longer matches text/{version}.txt; re-ingest it")
    lang = rounds.language(ws_root)
    index_of = {a: i for i, a in enumerate(ix.anchors)}
    targets: dict[str, list[str]] = {}
    for action in rounds.round_actions(ws_root, round_dir, cx):
        if action["status"] not in ("pending", "accepted") or not action["where"]:
            continue
        anchor = action["where"]["anchor"]
        if anchor not in index_of:
            raise DocxError(f"{action['id']}: {anchor} is not in {version}")
        at = draft.paragraphs[index_of[anchor]].at
        targets[at] = [*targets.get(at, []), *comment_lines(action, lang)]
    out = round_dir / f"{version}-comments.docx"
    with tempfile.TemporaryDirectory() as tmp:  # doc-control keeps backups beside the file
        work = Path(tmp) / out.name
        work.write_bytes(data)
        add_comments(work, targets)
        shutil.copyfile(work, out)
    return out, len(targets)
