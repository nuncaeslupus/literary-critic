"""Writer locators: how a person finds a paragraph without any tools.

For an anchor it gives the chapter (number and title) and the scene, from
literary-critic's labels, and from doc-control's ``locate`` and
``page.estimate``: an approximate page, the paragraph's first and last words
(doc-control's shortest head … tail that no other paragraph shares, shown with
at least four words a side so the writer can spot it by eye) and the phrase
Word's Find meets exactly once. A paragraph that repeats another one word for
word points to the paragraph just before it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from litcritic import dc, ingest, query

MIN_WORDS = 4  # words shown a side, at least (more never makes a unique phrase ambiguous)
MAX_WORDS = 12  # words shown a side when no phrase is unique
LABELS = {
    "es": {"front": "preliminares", "scene": "escena"},
    "en": {"front": "front matter", "scene": "scene"},
}
_WORD = re.compile(r"\S+")

Rows = dict[str, dict[str, Any]]  # doc-control address -> its locate row (plus text, page_exact)


class LocateError(ValueError):
    """The draft cannot be located (not read through doc-control, or its file is gone)."""


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
    find: str = ""  # what to type in Word's Find to land on this paragraph ("" when none)

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
        if self.find:
            out["find"] = self.find
        return out


def read_rows(doc: dc.Document) -> Rows:
    """doc-control's ``locate`` row of every paragraph, with its text and whether
    its page is Word's own (the file was laid out by Word and a mark or break
    fixes the page) rather than the word-count model's."""
    located = doc.run("locate", {})
    pages = doc.run("page.estimate", {})
    laid_out = str(located.get("basis", "model")) != "model"
    exact = {str(r["at"]): laid_out and r.get("source") != "model" for r in pages["paragraphs"]}
    text = {str(p["at"]): str(p.get("text", "")) for p in doc.paragraphs()}
    return {
        str(r["at"]): {**r, "text": text.get(str(r["at"]), ""), "page_exact": exact.get(r["at"])}
        for r in located["paragraphs"]
    }


def _ends(text: str, head: int, tail: int) -> tuple[str, str]:
    """The first ``head`` and last ``tail`` words of ``text``."""
    spans = [(m.start(), m.end()) for m in _WORD.finditer(text)]
    if not spans:
        return "", ""
    n = len(spans)
    head, tail = min(max(head, 1), n), min(max(tail, 1), n)
    first, last = text[spans[0][0] : spans[head - 1][1]], text[spans[n - tail][0] : spans[-1][1]]
    return ingest.clean(first), ingest.clean(last)  # as the writer sees them (no soft hyphens)


def _phrase(row: dict[str, Any]) -> tuple[str, str, bool]:
    """(first words, last words, unique) of a locate row."""
    if row.get("phrase") is None:
        side = MAX_WORDS if row.get("reason") == "not_unique_within_limit" else MIN_WORDS
        first, last = _ends(row["text"], side, side)
        return first, last, False
    head = max(int(row.get("head_words") or 0), MIN_WORDS)
    tail = max(int(row.get("tail_words") or 0), MIN_WORDS)
    first, last = _ends(row["text"], head, tail)
    return first, last, True


class Locations:
    """Writer locators for the paragraphs of an index.

    ``ats`` are the doc-control addresses of ``ix.paragraphs`` (same order);
    ``load`` returns doc-control's rows for the document they point into and is
    called once, on the first locator asked for.
    """

    def __init__(
        self, ix: query.Index, ats: list[str], load: Callable[[], Rows], lang: str = "en"
    ) -> None:
        self.ix = ix
        self.ats = ats
        self.lang = lang
        self._load = load
        self._rows: Rows | None = None
        self.chapter_by_key = {query.chapter_key(c["id"]): c for c in ix.chapters}

    @classmethod
    def of_workspace(
        cls, ws_root: Path, version: str, ix: query.Index, lang: str = "en"
    ) -> Locations:
        """Locators for an ingested draft, from its snapshot ``manuscript/vNNN.*``."""
        ats = [str(p.get("at", "")) for p in load_meta(ws_root, version)]
        if len(ats) != len(ix.paragraphs) or not all(ats):
            raise LocateError(f"{version} was not read through doc-control: run `lc ingest` again")
        meta_file = ws_root / "text" / f"{version}.meta.json"
        if ingest.converted_text(json.loads(meta_file.read_text(encoding="utf-8"))):
            raise LocateError(f"{version} was ingested by an older release: run `lc upgrade`")
        snapshots = [p for p in (ws_root / "manuscript").glob(f"{version}.*") if p.is_file()]
        if not snapshots:
            raise LocateError(f"the snapshot of {version} is missing from manuscript/")

        lines = ingest.txt_lines(ws_root)

        def load() -> Rows:
            with ingest.readable(snapshots[0], lines=lines) as file, dc.open(file) as doc:
                return read_rows(doc)

        return cls(ix, ats, load, lang)

    @property
    def rows(self) -> Rows:
        if self._rows is None:
            try:
                self._rows = self._load()
            except dc.DocError as exc:
                raise LocateError(f"cannot locate paragraphs: {exc}") from exc
        return self._rows

    def row(self, i: int) -> dict[str, Any] | None:
        """doc-control's locate row of paragraph ``i`` of the index."""
        return self.rows.get(self.ats[i]) if 0 <= i < len(self.ats) else None

    def locate(self, anchor: str) -> Locator:
        i = query.paragraph_range(self.ix, anchor).start
        a = self.ix.anchors[i]
        row = self.row(i)
        if row is None:
            raise KeyError(f"{a} is not in the document doc-control read")
        first, last, unique = _phrase(row)
        after = ""
        if not unique and (before := self.row(i - 1)) is not None:
            after = _phrase(before)[0]
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
        page = int(row.get("page_label") or row.get("page") or 0)
        return Locator(
            a,
            chapter_label,
            section,
            page,
            bool(row.get("page_exact")),
            first,
            last,
            unique,
            after,
            str(row.get("find_phrase") or ""),
        )


def load_meta(ws_root: Path, version: str) -> list[dict[str, Any]]:
    f = ws_root / "text" / f"{version}.meta.json"
    if not f.is_file():
        return []
    data = json.loads(f.read_text(encoding="utf-8"))
    return list(data.get("paragraphs", []))


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
        find=where.get("find", ""),
    )


def as_json(loc: Locator) -> str:
    return json.dumps(asdict(loc), ensure_ascii=False)
