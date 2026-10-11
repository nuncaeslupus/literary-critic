"""Novels and short stories: parts, chapters, scenes, paragraphs."""

from __future__ import annotations

from pathlib import Path

from litcritic.structure import detect

NAME = "novel"
TYPES_DIR: Path | None = None
CHECKLIST = Path(__file__).resolve().parents[3] / "checklist"

__all__ = ["CHECKLIST", "NAME", "TYPES_DIR", "detect"]
