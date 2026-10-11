"""Structure detection and paragraph anchors.

Turns an ingested draft (``text/vNNN.txt`` + ``vNNN.meta.json``) into parts,
chapters and scenes, and gives every paragraph a readable anchor
(``[pN.]cNN.sN.pN``) and a content fingerprint. Detection is heuristic and
deterministic; an LLM (or the writer) may propose corrections in an overrides
file keyed by fingerprints, which are validated before they are applied.

Signals, strongest first:

- explicit chapter/part words or numbers ("Capítulo 3", "PART TWO", "-IV-", "12.");
- outline levels from heading styles (only the top levels; deeper headings are
  usually notes or subtitles);
- paragraph style names that say what they are ("Chapter start", "Parte",
  "Separador", "after break");
- explicit page breaks before a short line, centred short lines, and short
  upper-case lines followed by body text;
- symbol-only lines ("*", "* * *", "#") and runs of blank lines as scene breaks.

A candidate chapter with too little text before the next one is not a chapter:
at the start it is front matter (chapter 0), elsewhere it stays inside the
previous chapter (signatures, "THE END" lines).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROMAN = r"[IVXLCDM]+"
NUMBER_WORDS = (
    "uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|"
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    "primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|quint[oa]|first|second|third|fourth|fifth"
)
NUM = rf"(?:\d+|{ROMAN}|{NUMBER_WORDS})"
CHAPTER_WORD = re.compile(
    rf"^(?:cap[ií]tulo|cap\.|chapter|ch\.)\s*{NUM}?\b|^(?:pr[oó]logo|prologue|ep[ií]logo|epilogue"
    r"|interludio|interlude|introducci[oó]n|introduction|coda)\b",
    re.I,
)
PART_WORD = re.compile(rf"^(?:parte|part|libro|book|volumen|volume)\s+{NUM}\b", re.I)
BARE_NUMBER = re.compile(rf"^[-\u2013\u2014.\s]*(?:\d{{1,3}}|{ROMAN})[-\u2013\u2014.\s]*$")
SYMBOLS = re.compile(r"^[\s*#~•·⁂§◆◇○●=+_\u2014\u2013-]{1,15}$")
STYLE_CHAPTER = re.compile(r"cap[ií]tulo|chapter|chap\b", re.I)
STYLE_PART = re.compile(r"\b(?:parte|part|libro|book)\b", re.I)
STYLE_BREAK = re.compile(r"separ|break|ornament|pausa|asterism", re.I)
STYLE_AFTER_BREAK = re.compile(r"tras|after|despu[eé]s", re.I)
MIN_CHAPTER_WORDS = 150
MIN_SIGNAL_COUNT = 3
SIGNAL_ORDER = ("chapter-word", "number", "chapter-style", "heading-style", "page-break", "caps")
MAX_HEADING_WORDS = 12


def fingerprint(text: str) -> str:
    """12-hex SHA-1 of case-folded, accent-stripped, whitespace-collapsed text."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return hashlib.sha1(" ".join(folded.split()).encode()).hexdigest()[:12]


@dataclass
class Unit:
    """A chapter (or part) as detected: where it starts and which lines are its heading."""

    start: int
    heading: list[int] = field(default_factory=list)
    title: str = ""
    reason: str = ""


@dataclass
class Structure:
    paragraphs: list[str]
    parts: list[Unit]
    chapters: list[Unit]  # chapters[0] may be front matter (start 0, reason "front")
    scene_starts: set[int]
    breaks: set[int]  # separator paragraphs (belong to no scene text)
    notes: list[str] = field(default_factory=list)

    def anchors(self) -> list[str]:
        return _anchor_list(self)


# --- detection ---------------------------------------------------------------


def _words(text: str) -> int:
    return len(text.split())


def _is_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def _heading_like(text: str) -> bool:
    return _words(text) <= MAX_HEADING_WORDS and not re.search(r"[.,;:]\s*$|[\"»”]$", text)


def _is_title_line(text: str, meta: dict[str, Any]) -> bool:
    """A short line right after a chapter number that names the chapter."""
    if not _heading_like(text) or _words(text) > 8 or re.match(r"^[-\u2013\u2014«\"“'¿¡]", text):
        return False
    return bool(meta.get("centered") or meta.get("heading") or _is_caps(text) or _words(text) <= 4)


def _is_break(text: str, meta: dict[str, Any]) -> bool:
    return bool(SYMBOLS.match(text)) or bool(
        STYLE_BREAK.search(str(meta.get("style", ""))) and _words(text) <= 3
    )


def _chapter_signal(text: str, meta: dict[str, Any], top_levels: set[int]) -> str:
    """Why this paragraph would start a chapter ('' if it would not)."""
    style = str(meta.get("style", ""))
    if CHAPTER_WORD.match(text) and _words(text) <= MAX_HEADING_WORDS:
        return "chapter-word"
    if BARE_NUMBER.match(text):
        return "number"
    if meta.get("heading") in top_levels and _heading_like(text):
        return "heading-style"
    if STYLE_CHAPTER.search(style) and not STYLE_PART.search(style):
        return "chapter-style"
    if meta.get("page_break_before") and _heading_like(text) and _words(text) <= 8:
        return "page-break"
    if _is_caps(text) and _heading_like(text) and not SYMBOLS.match(text):
        return "caps"
    return ""


def detect(paragraphs: list[str], meta: list[dict[str, Any]] | None = None) -> Structure:
    meta = meta or [{} for _ in paragraphs]
    levels = sorted({int(m["heading"]) for m in meta if m.get("heading")})
    parts: list[Unit] = []
    part_level = 0
    # Two heading levels in use and the top one is rare → the top one marks parts.
    if len(levels) >= 2:
        top_count = sum(1 for m in meta if m.get("heading") == levels[0])
        if top_count <= max(2, len(paragraphs) // 200):
            part_level = levels[0]
    top_levels = {lv for lv in levels[:2] if lv != part_level} if levels else set()
    if part_level and len(levels) >= 3:
        top_levels = {levels[1]}

    breaks = {i for i, t in enumerate(paragraphs) if _is_break(t, meta[i])}
    for i, (text, m) in enumerate(zip(paragraphs, meta, strict=True)):
        if i in breaks:
            continue
        style = str(m.get("style", ""))
        if (
            PART_WORD.match(text)
            or (part_level and m.get("heading") == part_level)
            or (STYLE_PART.search(style) and _heading_like(text))
        ):
            parts.append(Unit(i, [i], text, "part"))
    part_starts = {p.start for p in parts}

    found: list[Unit] = []
    for i, (text, m) in enumerate(zip(paragraphs, meta, strict=True)):
        if i in breaks or i in part_starts:
            continue
        reason = _chapter_signal(text, m, top_levels)
        if reason == "chapter-style":  # the styled paragraph is body text, not a title
            found.append(Unit(i, [], "", reason))
        elif reason:
            found.append(Unit(i, [i], text, reason))
    # The most specific kind of signal the draft uses consistently wins; weaker
    # kinds are usually something else (notes to self, signs, emphasis).
    counts = {r: sum(1 for u in found if u.reason == r) for r in SIGNAL_ORDER}
    chosen = next((r for r in SIGNAL_ORDER if counts[r] >= MIN_SIGNAL_COUNT), "")
    keep = {chosen, "chapter-word"} if chosen in ("number",) else {chosen}
    if chosen == "chapter-word":
        keep.add("number")
    raw = [u for u in found if u.reason in keep or (u.reason == "chapter-word" and u.heading)]
    if chosen:
        notes_signal = f"chapter signal: {chosen} ({counts[chosen]})"
    else:
        notes_signal = "chapter signal: none"
    # A heading spans its number line plus a following short title line.
    merged: list[Unit] = []
    for u in raw:
        prev = merged[-1] if merged else None
        if (
            prev
            and prev.heading
            and u.heading
            and u.start == prev.heading[-1] + 1
            and len(prev.heading) < 3
        ):
            first = paragraphs[prev.heading[0]]
            if (
                prev.reason in ("number", "chapter-word") and _heading_like(paragraphs[u.start])
            ) or (u.reason == prev.reason == "caps" and prev.start == 0):
                prev.heading.append(u.start)
                prev.title = f"{first} {paragraphs[u.start]}".strip()
                continue
        merged.append(u)
    for u in merged:
        nxt = u.heading[-1] + 1 if u.heading else 0
        if (
            u.heading
            and u.reason in ("number", "chapter-word")
            and len(u.heading) == 1
            and nxt < len(paragraphs)
            and nxt not in breaks
            and _is_title_line(paragraphs[nxt], meta[nxt])
            and not _chapter_signal(paragraphs[nxt], meta[nxt], top_levels)
        ):
            u.heading.append(nxt)
            u.title = f"{paragraphs[u.start]} {paragraphs[nxt]}"

    chapters = _drop_thin(paragraphs, merged, part_starts)
    if not chapters or chapters[0].start > 0:
        first_start = chapters[0].start if chapters else len(paragraphs)
        has_text = any(i not in part_starts and i not in breaks for i in range(0, first_start))
        if has_text or not chapters:
            chapters.insert(0, Unit(0, [], "", "front"))
    scene_starts = _scenes(paragraphs, meta, chapters, breaks, part_starts)
    notes = [
        f"{len(parts)} parts, {len(chapters)} chapters, {len(scene_starts)} scenes",
        notes_signal,
    ]
    return Structure(paragraphs, parts, chapters, scene_starts, breaks, notes)


def _drop_thin(paragraphs: list[str], units: list[Unit], part_starts: set[int]) -> list[Unit]:
    """Keep candidates followed by enough text; thin ones at the start become front matter."""
    kept: list[Unit] = []
    bounds = [u.start for u in units] + [len(paragraphs)]
    for k, u in enumerate(units):
        end = bounds[k + 1]
        last = u.heading[-1] if u.heading else u.start - 1
        for ps in sorted(part_starts):
            if last < ps < end:
                end = ps
        body = sum(_words(paragraphs[i]) for i in range(last + 1, end))
        strong = u.reason in ("chapter-word", "number", "heading-style", "chapter-style")
        if body >= MIN_CHAPTER_WORDS or (strong and body > 0 and kept):
            kept.append(u)
    return kept


def _scenes(
    paragraphs: list[str],
    meta: list[dict[str, Any]],
    chapters: list[Unit],
    breaks: set[int],
    part_starts: set[int],
) -> set[int]:
    starts: set[int] = set()
    heads = {i for c in chapters for i in c.heading} | part_starts
    for c in chapters:
        first = (c.heading[-1] + 1) if c.heading else c.start
        while first in breaks or first in part_starts:
            first += 1
        starts.add(first)
    for i in range(1, len(paragraphs)):
        if i in breaks or i in heads:
            continue
        style = str(meta[i].get("style", ""))
        if (i - 1) in breaks or (
            (int(meta[i].get("blank_before", 0)) >= 2 or STYLE_AFTER_BREAK.search(style))
            and (i - 1) not in heads
        ):
            starts.add(i)
    return starts


# --- anchors -------------------------------------------------------------------


def _anchor_list(s: Structure) -> list[str]:
    """``[pN.]cNN.sN.pN``: chapter 00 is front matter, scene 0 holds heading lines.

    A part heading belongs to scene 0 of the chapter that follows it; a scene
    break line is the last paragraph of the scene it closes.
    """
    n = len(s.paragraphs)
    part_heads = {p.start for p in s.parts}
    starts = [c.start for c in s.chapters]
    for ps in part_heads:  # pull a part heading into the next chapter's head
        for k, st in enumerate(starts):
            between = range(ps + 1, st)
            if st > ps and all(i in s.breaks or i in part_heads for i in between):
                starts[k] = min(st, ps)
                break
    heads = {i for c in s.chapters for i in c.heading} | part_heads
    has_front = bool(s.chapters) and s.chapters[0].reason == "front"
    out: list[str] = []
    ci, scene, counts = -1, 0, {0: 0}
    for i in range(n):
        while ci + 1 < len(starts) and i >= starts[ci + 1]:
            ci, scene, counts = ci + 1, 0, {0: 0}
        num = max(ci, 0) if has_front else ci + 1
        part = sum(1 for ps in part_heads if ps <= i)
        prefix = f"p{part}." if s.parts else ""
        if i in heads:
            sc = 0
        else:
            if i in s.scene_starts or scene == 0:
                scene += 1
                counts[scene] = 0
            sc = scene
        counts[sc] = counts.get(sc, 0) + 1
        out.append(f"{prefix}c{num:02d}.s{sc}.p{counts[sc]}")
    return out


# --- overrides ------------------------------------------------------------------

OVERRIDE_KEYS = ("chapter_starts", "not_chapter", "scene_starts", "not_scene")


def apply_overrides(s: Structure, overrides: dict[str, Any]) -> list[str]:
    """Apply corrections keyed by paragraph fingerprint; return validation errors.

    Nothing is applied when any error is found, so a bad proposal never leaves a
    half-corrected structure.
    """
    fps = [fingerprint(t) for t in s.paragraphs]
    where: dict[str, list[int]] = {}
    for i, fp in enumerate(fps):
        where.setdefault(fp, []).append(i)
    errors = [f"unknown key {k!r}" for k in overrides if k not in OVERRIDE_KEYS]
    resolved: dict[str, list[int]] = {}
    for key in OVERRIDE_KEYS:
        items = overrides.get(key, [])
        if not isinstance(items, list):
            errors.append(f"{key}: expected a list of fingerprints")
            continue
        resolved[key] = []
        for fp in items:
            hits = where.get(str(fp), [])
            if len(hits) != 1:
                problem = "not found" if not hits else f"matches {len(hits)} paragraphs"
                errors.append(f"{key}: {fp} {problem}")
            else:
                resolved[key].append(hits[0])
    if errors:
        return errors
    drop = set(resolved["not_chapter"])
    s.chapters = [c for c in s.chapters if c.start not in drop or c.reason == "front"]
    known = {c.start for c in s.chapters}
    for i in resolved["chapter_starts"]:
        if i not in known:
            s.chapters.append(Unit(i, [], "", "override"))
    s.chapters.sort(key=lambda c: c.start)
    s.scene_starts |= set(resolved["scene_starts"]) | set(resolved["chapter_starts"])
    s.scene_starts -= set(resolved["not_scene"])
    s.notes.append(f"overrides applied: {sum(len(v) for v in resolved.values())}")
    return []


# --- workspace I/O ----------------------------------------------------------------


def to_json(s: Structure, version: str) -> dict[str, Any]:
    anchors = s.anchors()
    words = [_words(t) for t in s.paragraphs]
    bounds = [c.start for c in s.chapters] + [len(s.paragraphs)]
    chapters = []
    for k, c in enumerate(s.chapters):
        lo, hi = c.start, bounds[k + 1]
        cid = anchors[next((i for i in range(lo, hi) if i not in c.heading), lo)].split(".s")[0]
        scenes: dict[str, dict[str, Any]] = {}
        for i in range(lo, hi):
            sid = anchors[i].rsplit(".p", 1)[0]
            if sid.endswith(".s0"):
                continue
            sc = scenes.setdefault(sid, {"id": sid, "start": i, "end": i, "words": 0})
            sc["end"] = i
            sc["words"] += words[i]
        chapters.append(
            {
                "id": cid,
                "title": c.title or (s.paragraphs[c.heading[0]] if c.heading else ""),
                "reason": c.reason,
                "start": lo,
                "end": hi - 1,
                "words": sum(words[lo:hi]),
                "scenes": list(scenes.values()),
            }
        )
    return {
        "schema_version": 1,
        "version": version,
        "notes": s.notes,
        "parts": [{"n": n + 1, "title": p.title, "start": p.start} for n, p in enumerate(s.parts)],
        "chapters": chapters,
        "paragraphs": [[a, fingerprint(t)] for a, t in zip(anchors, s.paragraphs, strict=True)],
    }


def latest_version(ws_root: Path) -> str:
    texts = sorted((ws_root / "text").glob("v[0-9][0-9][0-9].txt"))
    if not texts:
        raise FileNotFoundError("no ingested draft; run `lc ingest` first")
    return texts[-1].stem


def build(ws_root: Path, version: str | None = None) -> tuple[Path, Structure, list[str]]:
    """Detect, apply ``analysis/structure-overrides.json`` if present, write structure.json."""
    version = version or latest_version(ws_root)
    text = (ws_root / "text" / f"{version}.txt").read_text(encoding="utf-8")
    paragraphs = text.split("\n")[:-1] if text.endswith("\n") else text.split("\n")
    meta_file = ws_root / "text" / f"{version}.meta.json"
    meta = None
    if meta_file.is_file():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))["paragraphs"]
    s = detect(paragraphs, meta)
    errors: list[str] = []
    ov = ws_root / "analysis" / "structure-overrides.json"
    if ov.is_file():
        errors = apply_overrides(s, json.loads(ov.read_text(encoding="utf-8")))
    out = ws_root / "index" / version / "structure.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(to_json(s, version), ensure_ascii=False) + "\n", encoding="utf-8")
    return out, s, errors
