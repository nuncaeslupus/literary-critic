"""Kinds of text: each plugs its structure detection, item types and checklist.

A kind is a module here exposing ``NAME``, ``detect(paragraphs, meta)``,
``TYPES_DIR`` (extra Codex item types, or None) and ``CHECKLIST`` (catalogue
folder). The core asks the registry for a work's kind and never imports a
kind by name.
"""

from __future__ import annotations

import importlib
import pkgutil
import tomllib
from pathlib import Path
from types import ModuleType

DEFAULT = "novel"


class KindError(Exception):
    """No such kind of text."""


def available() -> list[str]:
    return sorted(m.name for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_"))


def get(name: str) -> ModuleType:
    if name not in available():
        raise KindError(f"unknown kind {name!r}; known: {', '.join(available())}")
    return importlib.import_module(f"{__name__}.{name}")


def of_work(work_root: Path) -> ModuleType:
    """The kind named in the work's ``work.toml`` (novel when missing)."""
    f = work_root / "work.toml"
    kind = DEFAULT
    if f.is_file():
        try:
            kind = str(tomllib.loads(f.read_text(encoding="utf-8")).get("kind") or DEFAULT)
        except (OSError, ValueError):
            kind = DEFAULT
    return get(kind if kind in available() else DEFAULT)


def type_dirs(work_root: Path) -> list[Path]:
    d = getattr(of_work(work_root), "TYPES_DIR", None)
    return [d] if d else []
