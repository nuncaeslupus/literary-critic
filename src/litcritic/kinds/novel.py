"""Novels and short stories: parts, chapters, scenes, paragraphs."""

from __future__ import annotations

from pathlib import Path

from litcritic.structure import detect
from litcritic.workspace import repo_root

NAME = "novel"
TYPES_DIR: Path | None = None
CHECKLIST = repo_root() / "checklist"

__all__ = ["CHECKLIST", "NAME", "TYPES_DIR", "detect"]
