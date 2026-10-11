"""Poetry collections: each poem is a chapter, its stanzas are paragraphs.

A poem starts at a title line: short, no closing punctuation, alone in its
block (a blank line after it, when the file records blank lines) and followed by
text. Each line of verse is a paragraph. Everything before the first title is
front matter.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from litcritic.structure import Structure, Unit

NAME = "poem"
TYPES_DIR: Path | None = Path(__file__).parent / "poem_data" / "types"
CHECKLIST = Path(__file__).parent / "poem_data" / "checklist"
TITLE_MAX_WORDS = 8
CLOSING = re.compile(r"[.,;:!?…»”\"')\]-]$")


def _is_title(text: str) -> bool:
    t = text.strip()
    return bool(t) and len(t.split()) <= TITLE_MAX_WORDS and not CLOSING.search(t)


def detect(paragraphs: list[str], meta: list[dict[str, Any]] | None = None) -> Structure:
    n = len(paragraphs)
    known = meta if meta and len(meta) == n else None

    def alone(i: int) -> bool:
        return known is None or int(known[i + 1].get("blank_before", 0)) >= 1

    titles = [
        i
        for i in range(n - 1)
        if _is_title(paragraphs[i]) and alone(i) and not _is_title(paragraphs[i + 1])
    ]
    chapters = [
        Unit(start=i, heading=[i], title=paragraphs[i].strip(), reason="title") for i in titles
    ]
    if not chapters or chapters[0].start > 0:
        chapters.insert(0, Unit(start=0, reason="front"))
    scene_starts = {c.heading[-1] + 1 for c in chapters if c.heading and c.heading[-1] + 1 < n}
    notes = [f"{len(titles)} poems (kind: poem)"]
    return Structure(list(paragraphs), [], chapters, scene_starts, set(), notes)
