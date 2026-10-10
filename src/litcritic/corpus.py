"""Public-domain corpus: source notes and their validation.

Each ``corpus/<slug>/`` holds ``text.txt`` and ``source.toml``. A text counts as
documented when its note has every required field and its checksum matches.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from litcritic.workspace import repo_root

REQUIRED_FIELDS = (
    "title",
    "author",
    "year",
    "language",
    "origin",
    "origin_url",
    "retrieved",
    "licence",
    "processing",
    "sha256",
)


@dataclass
class Text:
    slug: str
    path: Path
    meta: dict[str, object]
    errors: list[str] = field(default_factory=list)

    @property
    def documented(self) -> bool:
        return not self.errors

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")


def default_root() -> Path:
    return repo_root() / "corpus"


def load(root: Path | None = None) -> list[Text]:
    """Every corpus text under ``root``, with its documentation errors."""
    root = root or default_root()
    texts = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        texts.append(_load_one(d))
    return texts


def get(slug: str, root: Path | None = None) -> Text:
    d = (root or default_root()) / slug
    if not d.is_dir():
        raise FileNotFoundError(f"no corpus text named {slug!r}")
    return _load_one(d)


def _load_one(d: Path) -> Text:
    text = Text(d.name, d / "text.txt", {})
    note = d / "source.toml"
    if not text.path.is_file():
        text.errors.append("missing text.txt")
    if not note.is_file():
        text.errors.append("missing source.toml")
        return text
    try:
        text.meta = tomllib.loads(note.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        text.errors.append(f"source.toml: {exc}")
        return text
    for key in REQUIRED_FIELDS:
        value = text.meta.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            text.errors.append(f"source.toml: missing {key}")
    if text.path.is_file() and "sha256" in text.meta:
        digest = hashlib.sha256(text.path.read_bytes()).hexdigest()
        if digest != text.meta["sha256"]:
            text.errors.append("text.txt does not match source.toml sha256")
    return text


def documented_ratio(texts: list[Text]) -> float:
    """Gate metric ``corpus_sources_documented``; 0.0 for an empty corpus."""
    return sum(t.documented for t in texts) / len(texts) if texts else 0.0
