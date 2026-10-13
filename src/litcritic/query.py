"""Bounded views of an indexed draft for the LLM: show, find, context.

Every command takes a token budget and never prints more than that (estimated
as characters / 3.5, a conservative figure for Spanish and English). When text
is cut, the last line says what was left out and how to continue.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from litcritic import structure
from litcritic.textstats import strip_accents

DEFAULT_BUDGET = 2000
FOOTER_RESERVE = 40
MIN_BUDGET = 100


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 3.5)


@dataclass
class Out:
    budget: int
    lines: list[str] = field(default_factory=list)
    used: int = 0
    cut: bool = False

    def __post_init__(self) -> None:
        if self.budget < MIN_BUDGET:
            raise ValueError(f"--budget must be at least {MIN_BUDGET} tokens")

    def add_cut(self, line: str) -> None:
        """Add as much of ``line`` as fits (for a paragraph longer than the budget)."""
        room = int((self.budget - FOOTER_RESERVE - self.used - 2) * 3.5)
        self.lines.append(line[: max(room, 0)].rstrip() + " […]")
        self.used = self.budget - FOOTER_RESERVE
        self.cut = True

    def add(self, line: str) -> bool:
        cost = estimate_tokens(line) + 1
        if self.used + cost > self.budget - FOOTER_RESERVE:
            self.cut = True
            return False
        self.lines.append(line)
        self.used += cost
        return True

    def finish(self, footer: str = "") -> str:
        if footer:
            footer = footer[: int((FOOTER_RESERVE - 2) * 3.5)]
            self.lines.append(footer)
        return "\n".join(self.lines) + "\n"


@dataclass
class Index:
    paragraphs: list[str]
    anchors: list[str]
    fps: list[str]
    chapters: list[dict[str, Any]]
    scenes: dict[str, str] = field(default_factory=dict)  # scene anchor -> Codex scene line
    override_fps: list[str] = field(default_factory=list)  # doc-control's, for overrides

    def scene_of(self, i: int) -> str:
        return self.anchors[i].rsplit(".p", 1)[0]


def load(ws_root: Path, version: str | None = None, codex: bool = True) -> Index:
    version = version or structure.latest_version(ws_root)
    text = (ws_root / "text" / f"{version}.txt").read_text(encoding="utf-8")
    paras = text.split("\n")[:-1] if text.endswith("\n") else text.split("\n")
    struct_file = ws_root / "index" / version / "structure.json"
    if not struct_file.is_file():
        raise FileNotFoundError(f"no structure for {version}; run `lc anchor` first")
    data = json.loads(struct_file.read_text(encoding="utf-8"))
    fps = [f for _, f in data["paragraphs"]]
    if len(fps) != len(paras) or any(
        structure.fingerprint(t) != f for t, f in zip(paras, fps, strict=True)
    ):
        raise ValueError(f"structure for {version} is out of date; run `lc anchor`")
    anchors = [a for a, _ in data["paragraphs"]]
    scenes = _codex_scenes(ws_root, version, anchors) if codex else {}
    return Index(paras, anchors, fps, data["chapters"], scenes, _override_fps(ws_root, version))


def _override_fps(ws_root: Path, version: str) -> list[str]:
    """doc-control's fingerprint of each paragraph (its address after ``#``), or []."""
    meta_file = ws_root / "text" / f"{version}.meta.json"
    if not meta_file.is_file():
        return []
    rows = json.loads(meta_file.read_text(encoding="utf-8")).get("paragraphs") or []
    return [str(r.get("at", "")).partition("#")[2] for r in rows]


def _codex_scenes(ws_root: Path, version: str, anchors: list[str]) -> dict[str, str]:
    """One line per scene that a Codex ``scene`` item spans."""
    from litcritic import codex  # codex -> spans -> query

    cx = codex.synced(ws_root, version)
    if cx is None:
        return {}
    out = {}
    for unit, item in cx.scenes_by_unit(anchors).items():
        f = item.fields
        line = f"{f.get('summary', item.text)} | POV {f.get('pov', '?')}"
        out[_bare(unit)] = line + "".join(f" | {f[k]}" for k in ("location", "time") if f.get(k))
    return out


def chapter_key(anchor: str) -> str:
    """'p1.c03.s2.p4' -> 'c03' (chapter ids carry no part prefix in lookups)."""
    m = re.search(r"c\d+", anchor)
    return m.group() if m else anchor


def _bare(anchor: str) -> str:
    return re.sub(r"^p\d+\.", "", anchor.strip())


def paragraph_range(ix: Index, unit: str) -> range:
    """Paragraph indices of a chapter ('c03'), scene ('c03.s2') or paragraph anchor."""
    u = _bare(unit)
    hits = [i for i, a in enumerate(ix.anchors) if _bare(a) == u or _bare(a).startswith(u + ".")]
    if not hits:
        raise KeyError(f"no paragraphs at {unit!r}; try `lc show` for the table of contents")
    return range(hits[0], hits[-1] + 1)


def toc(ix: Index, budget: int = DEFAULT_BUDGET) -> str:
    out = Out(budget)
    out.add("chapter | words | scenes | title")
    shown = 0
    for c in ix.chapters:
        line = f"{c['id']} | {c['words']} | {len(c['scenes'])} | {c['title']}"
        if not out.add(line):
            break
        shown += 1
    rest = len(ix.chapters) - shown
    return out.finish(f"… {rest} more chapters; raise --budget or show one chapter" if rest else "")


def show(ix: Index, unit: str, budget: int = DEFAULT_BUDGET, fingerprints: bool = False) -> str:
    r = paragraph_range(ix, unit)
    out = Out(budget)
    last = r.start - 1
    for i in r:
        fp = ix.override_fps[i] if len(ix.override_fps) == len(ix.paragraphs) else ix.fps[i]
        tag = f"{ix.anchors[i]} {fp}" if fingerprints else ix.anchors[i]
        line = f"[{tag}] {ix.paragraphs[i]}"
        if not out.add(line):
            if i == r.start:  # longer than the whole budget: show its start, move on
                out.add_cut(line)
                last = i
            break
        last = i
    if last < r.stop - 1:
        nxt = ix.anchors[last + 1]
        return out.finish(f"… {r.stop - 1 - last} more paragraphs; continue: lc show {nxt}-")
    return out.finish()


def show_from(ix: Index, anchor: str, budget: int = DEFAULT_BUDGET) -> str:
    """Continue reading from ``anchor`` to the end of its chapter."""
    start = paragraph_range(ix, anchor.rstrip("-")).start
    chapter = paragraph_range(ix, chapter_key(ix.anchors[start]))
    out = Out(budget)
    last = start - 1
    for i in range(start, chapter.stop):
        line = f"[{ix.anchors[i]}] {ix.paragraphs[i]}"
        if not out.add(line):
            if i == start:
                out.add_cut(line)
                last = i
            break
        last = i
    if last < chapter.stop - 1:
        return out.finish(f"… continue: lc show {ix.anchors[last + 1]}-")
    return out.finish()


def _fold(text: str) -> str:
    return strip_accents(text).casefold()


def find(ix: Index, query: str, budget: int = DEFAULT_BUDGET, within: str = "") -> str:
    """Paragraphs containing every word of ``query`` (or the quoted phrase), accent-blind."""
    q = query.strip()
    if not q.strip('"').strip():
        raise ValueError("empty search; give one or more words")
    phrase = q.startswith('"') and q.endswith('"') and len(q) > 1
    terms = [_fold(q.strip('"'))] if phrase else [_fold(t) for t in q.split()]
    scope = paragraph_range(ix, within) if within else range(len(ix.paragraphs))
    hits = [i for i in scope if all(t in _fold(ix.paragraphs[i]) for t in terms)]
    out = Out(budget)
    out.add(f"{len(hits)} paragraphs match {query!r}")
    shown = 0
    for i in hits:
        if not out.add(f"[{ix.anchors[i]}] {_snippet(ix.paragraphs[i], terms[0])}"):
            break
        shown += 1
    rest = len(hits) - shown
    return out.finish(f"… {rest} more; narrow with --in <chapter> or more words" if rest else "")


def _snippet(text: str, term: str, width: int = 30) -> str:
    words = text.split()
    folded = [_fold(w) for w in words]
    pos = next((k for k, w in enumerate(folded) if term.split()[0] in w), 0) if term else 0
    lo, hi = max(0, pos - width // 2), min(len(words), pos + width // 2)
    return ("… " if lo else "") + " ".join(words[lo:hi]) + (" …" if hi < len(words) else "")


def context(ix: Index, anchor: str, budget: int = DEFAULT_BUDGET) -> str:
    """Where a paragraph sits: chapter, Codex scene, then the text around it."""
    r = paragraph_range(ix, anchor)
    centre = r.start
    out = Out(budget)
    ckey = chapter_key(ix.anchors[centre])
    chapter = next((c for c in ix.chapters if chapter_key(c["id"]) == ckey), None)
    if chapter:
        title = chapter["title"] or "(untitled)"
        out.add(f"chapter {chapter['id']}: {title} — {chapter['words']} words")
    scene = _bare(ix.scene_of(centre))
    if scene in ix.scenes:
        out.add(f"scene {scene}: {ix.scenes[scene]}")
    if not out.add(f">>> [{ix.anchors[centre]}] {ix.paragraphs[centre]}"):
        return out.finish("… paragraph longer than the budget; use lc show")
    header, target = out.lines[:-1], out.lines[-1]
    before: list[str] = []
    after: list[str] = []
    lo, hi = centre - 1, centre + 1
    open_lo, open_hi = lo >= 0, hi < len(ix.paragraphs)
    while open_lo or open_hi:
        for side in ("hi", "lo"):
            if side == "hi" and open_hi:
                line = f"[{ix.anchors[hi]}] {ix.paragraphs[hi]}"
                if out.add(line):
                    after.append(line)
                    hi += 1
                    open_hi = hi < len(ix.paragraphs)
                else:
                    open_hi = False
            elif side == "lo" and open_lo:
                line = f"[{ix.anchors[lo]}] {ix.paragraphs[lo]}"
                if out.add(line):
                    before.append(line)
                    lo -= 1
                    open_lo = lo >= 0
                else:
                    open_lo = False
    out.lines = [*header, *reversed(before), target, *after]
    return out.finish()
