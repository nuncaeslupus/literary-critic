"""Novels and short stories: parts, chapters, scenes, paragraphs.

doc-control's chapter and scene detection does the work; ``PROFILE`` holds the
settings a novel needs (passed to ``segment`` as ``profile``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from litcritic.workspace import repo_root

NAME = "novel"
TYPES_DIR: Path | None = None
CHECKLIST = repo_root() / "checklist"
PROFILE: dict[str, Any] = {}
# Per manuscript format: plain text marks a heading with a wider gap above a short
# line; Markdown novels may use any heading level for chapters.
FORMAT_PROFILE: dict[str, dict[str, Any]] = {
    "txt": {"chapter_blank_lines": 2},
    "md": {"chapter_level": "auto"},
}

__all__ = ["CHECKLIST", "FORMAT_PROFILE", "NAME", "PROFILE", "TYPES_DIR"]
