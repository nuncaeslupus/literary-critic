"""Writer locators: how a person finds a paragraph without any tools.

For an anchor it gives the chapter (number and title), the scene, an
approximate page, and the paragraph's first and last words — each the shortest
run of words (at least four, at most twelve) that occurs exactly once in the
whole draft, so the writer can spot it by eye or with the editor's search box.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from litcritic import query

MIN_WORDS = 4
MAX_WORDS = 12
WORDS_PER_PAGE = 300
LABELS = {
    "es": {"front": "preliminares", "scene": "escena"},
    "en": {"front": "front matter", "scene": "scene"},
}


@dataclass
class Locator:
    anchor: str
    chapter: str
    section: str
    page: int
    page_exact: bool
    first_words: str
    last_words: str
    unique: bool
    after: str = ""  # opening words of the previous paragraph, when this one is not unique

    def as_where(self) -> dict[str, Any]:
        """The ``where`` object of an action (schema ``action``)."""
        out: dict[str, Any] = {
            "anchor": self.anchor,
            "chapter": self.chapter,
            "first_words": self.first_words,
            "last_words": self.last_words,
        }
        if self.section:
            out["section"] = self.section
        if self.page:
            out["page"] = self.page
            out["page_exact"] = self.page_exact
        if self.after:
            out["after"] = self.after
        return out


def _occurrences(haystack: str, needle: str) -> int:
    return haystack.count(needle)


def _unique_run(words: list[str], text: str, from_end: bool) -> tuple[str, bool]:
    """Shortest run of words from the start (or end) that occurs once in ``text``."""
    n = len(words)
    for k in range(min(MIN_WORDS, n), min(MAX_WORDS, n) + 1):
        run = " ".join(words[n - k :] if from_end else words[:k])
        if _occurrences(text, run) == 1:
            return run, True
    k = min(MAX_WORDS, n)
    return " ".join(words[n - k :] if from_end else words[:k]), False


class LocatorBuilder:
    def __init__(
        self, ix: query.Index, meta: list[dict[str, Any]] | None = None, lang: str = "en"
    ) -> None:
        self.ix = ix
        self.lang = lang
        self.text = "\n".join(ix.paragraphs)
        self.meta = meta if meta and len(meta) == len(ix.paragraphs) else []
        self.pages_known = any(m.get("page") for m in self.meta)
        self.words_before: list[int] = []
        total = 0
        for p in ix.paragraphs:
            self.words_before.append(total)
            total += len(p.split())
        self.chapter_by_key = {query.chapter_key(c["id"]): c for c in ix.chapters}

    def locate(self, anchor: str) -> Locator:
        i = query.paragraph_range(self.ix, anchor).start
        a = self.ix.anchors[i]
        words = self.ix.paragraphs[i].split()
        first, ok1 = _unique_run(words, self.text, from_end=False)
        last, ok2 = _unique_run(words, self.text, from_end=True)
        chapter = self.chapter_by_key.get(query.chapter_key(a), {})
        m = re.search(r"c(\d+)", a)
        number = int(m.group(1)) if m else 0
        title = str(chapter.get("title") or "")
        labels = LABELS.get(self.lang, LABELS["en"])
        chapter_label = (
            f"{number}" + (f" ({title})" if title else "") if number else labels["front"]
        )
        scene = re.search(r"\.s(\d+)", a)
        section = f"{labels['scene']} {scene.group(1)}" if scene and scene.group(1) != "0" else ""
        page = int(self.meta[i].get("page") or 0) if self.pages_known else 0
        exact = page > 0
        if not exact:
            page = self.words_before[i] // WORDS_PER_PAGE + 1
        after = ""
        if not (ok1 and ok2) and i > 0:
            after, _ = _unique_run(self.ix.paragraphs[i - 1].split(), self.text, from_end=False)
        return Locator(a, chapter_label, section, page, exact, first, last, ok1 and ok2, after)


def load_meta(ws_root: Path, version: str) -> list[dict[str, Any]]:
    f = ws_root / "text" / f"{version}.meta.json"
    if not f.is_file():
        return []
    data = json.loads(f.read_text(encoding="utf-8"))
    paragraphs = data.get("paragraphs", [])
    return paragraphs if data.get("pages_known") else []


def describe(loc: Locator, lang: str = "en") -> str:
    """One line a writer can follow."""
    approx = "" if loc.page_exact else "≈"
    if lang == "es":
        where = f"Capítulo {loc.chapter}" + (f", {loc.section}" if loc.section else "")
        line = (
            f"{where}, pág. {approx}{loc.page}: el párrafo que empieza «{loc.first_words}…» "
            f"y termina «…{loc.last_words}»"
        )
        return line + (f", justo después del que empieza «{loc.after}…»" if loc.after else "")
    where = f"Chapter {loc.chapter}" + (f", {loc.section}" if loc.section else "")
    line = (
        f"{where}, p. {approx}{loc.page}: the paragraph that starts “{loc.first_words}…” "
        f"and ends “…{loc.last_words}”"
    )
    return line + (f", right after the one that starts “{loc.after}…”" if loc.after else "")


def from_where(where: dict[str, Any]) -> Locator:
    """A locator rebuilt from an action's stored ``where`` (no draft needed)."""
    return Locator(
        anchor=where["anchor"],
        chapter=where["chapter"],
        section=where.get("section", ""),
        page=int(where.get("page", 0)),
        page_exact=bool(where.get("page_exact", False)),
        first_words=where["first_words"],
        last_words=where["last_words"],
        unique=True,
        after=where.get("after", ""),
    )


def as_json(loc: Locator) -> str:
    return json.dumps(asdict(loc), ensure_ascii=False)
