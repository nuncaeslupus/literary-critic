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

__all__ = ["CHECKLIST", "NAME", "PROFILE", "TYPES_DIR"]
