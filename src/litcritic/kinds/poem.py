"""Poetry collections: each poem is a chapter, its stanzas are paragraphs.

A poem starts at a title line: short, no closing punctuation, and alone in its
block (a blank line before and after it). Each line of verse is a paragraph, so
a stanza's first or last line never qualifies. One-line stanzas that look like
titles are the known ambiguity; correct them with structure overrides.
Everything before the first title is front matter.

doc-control's own chapter and scene detection is switched off (``PROFILE``); the
titles found here reach ``segment`` as forced chapter starts.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

NAME = "poem"
TYPES_DIR: Path | None = Path(__file__).parent / "poem_data" / "types"
CHECKLIST = Path(__file__).parent / "poem_data" / "checklist"
PROFILE: dict[str, Any] = {
    "heading_styles": False,
    "chapter_patterns": False,
    "chapter_styles": False,
    "scene_markers": False,
    "scene_styles": False,
    "heading_subtitles": False,
}
# doc-control cuts a .txt one paragraph per line (verse), whatever empty lines it holds.
TEXT_MODE = "lines"
TITLE_MAX_WORDS = 8
CLOSING = re.compile(r"[.,;:!?…»”\"')\]-]$")


def _is_title(text: str) -> bool:
    t = text.strip()
    return bool(t) and len(t.split()) <= TITLE_MAX_WORDS and not CLOSING.search(t)


def chapter_starts(paragraphs: list[str], meta: list[dict[str, Any]]) -> list[int]:
    """Paragraphs that are poem titles (none without blank-line facts)."""
    n = len(paragraphs)
    if len(meta) != n:
        return []

    def blank_before(i: int) -> bool:
        return i == 0 or int(meta[i].get("blank_before", 0)) >= 1

    return [
        i
        for i in range(n - 1)
        if _is_title(paragraphs[i]) and blank_before(i) and blank_before(i + 1)
    ]
