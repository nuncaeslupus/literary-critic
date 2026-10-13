"""Structure from doc-control's ``segment``, and paragraph anchors.

doc-control finds the parts, chapters and scenes of the file a draft was
ingested from (``.docx``, ``.txt`` or ``.md``; a converted copy for ``.odt``), with a
stable id and the signals behind each one. This module lays literary-critic's
labels over them: chapter ``cNN`` (``c00`` is front matter), scene ``sN`` (``s0``
holds heading lines) and paragraph ``pN``, so every paragraph of ``text/vNNN.txt``
gets a readable anchor ``[pN.]cNN.sN.pN`` and a content fingerprint.

The kind of text decides the detection settings (its ``PROFILE``, passed to
``segment`` as ``profile``) and may propose chapter starts doc-control does not
look for (``chapter_starts``), passed as forced overrides. The writer's
corrections in ``analysis/structure-overrides.json`` are doc-control's override
shape, passed through unchanged after the kind's (a later override wins)::

    {"schema_version": 2, "overrides": [{"fp": "7d3684d2", "kind": "chapter",
                                          "action": "force", "nth": 1}]}

The first shape (``chapter_starts``/``not_chapter``/``scene_starts``/``not_scene``
lists of 12-hex fingerprints) is still read and translated.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import re
import tempfile
import tomllib
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from litcritic import dc, kinds

OVERRIDES_SCHEMA = 2
LEGACY_KEYS = {
    "chapter_starts": ("chapter", "force"),
    "not_chapter": ("chapter", "deny"),
    "scene_starts": ("scene", "force"),
    "not_scene": ("scene", "deny"),
}
OPENING = ("chapter_start", "part_start", "document_start")  # a scene that opens its unit
LANGUAGES = ("es", "en")  # doc-control's sentence and numeral rules; others are "generic"


def fingerprint(text: str) -> str:
    """12-hex SHA-1 of case-folded, accent-stripped, whitespace-collapsed text."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return hashlib.sha1(" ".join(folded.split()).encode()).hexdigest()[:12]


@dataclass
class Unit:
    """A part or chapter: where it starts and which lines are its heading."""

    start: int
    heading: list[int] = field(default_factory=list)
    title: str = ""
    reason: str = ""  # the first signal doc-control gave ("front" for front matter)
    uid: str = ""  # doc-control's stable id (pt-…, ch-…)
    signals: list[str] = field(default_factory=list)


@dataclass
class Scene:
    """A doc-control scene: the paragraph it opens at, its stable id and signals."""

    start: int
    uid: str
    signals: list[str]


@dataclass
class Structure:
    paragraphs: list[str]
    parts: list[Unit]
    chapters: list[Unit]  # chapters[0] may be front matter (start 0, reason "front")
    scene_starts: set[int]
    breaks: set[int]  # scene-break paragraphs (the last paragraph of the scene they close)
    notes: list[str] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)  # doc-control's, in order

    def anchors(self) -> list[str]:
        return _anchor_list(self)


# --- segment -------------------------------------------------------------------


def _number(at: str) -> int:
    m = re.match(r"p(\d+)#", at)
    if not m:
        raise ValueError(f"not a doc-control paragraph address: {at!r}")
    return int(m.group(1))


def _language(language: str) -> str:
    return language if language in LANGUAGES else "generic"


def _forced(ats: list[str], starts: list[int]) -> list[dict[str, Any]]:
    """Forced chapter overrides for paragraph indexes ``starts``."""
    fps = [at.split("#", 1)[1] for at in ats]
    out: list[dict[str, Any]] = []
    for i in starts:
        o: dict[str, Any] = {"fp": fps[i], "kind": "chapter", "action": "force"}
        if fps.count(fps[i]) > 1:
            o["nth"] = fps[:i].count(fps[i]) + 1
        out.append(o)
    return out


def segment(
    doc: dc.Document,
    paragraphs: list[str],
    ats: list[str],
    profile: dict[str, Any],
    overrides: list[dict[str, Any]],
    language: str = "es",
) -> tuple[Structure, list[str]]:
    """Parts, chapters and scenes of ``doc``, labelled over its text paragraphs.

    ``ats`` are the doc-control addresses of ``paragraphs`` (empty paragraphs are
    not text). Returns the structure and the overrides doc-control could not match.
    """
    numbers = [_number(at) for at in ats]

    def index(number: int) -> int:
        """The text paragraph at doc-control paragraph ``number``, or the next one."""
        return min(bisect.bisect_left(numbers, number), len(numbers) - 1)

    request: dict[str, Any] = {"profile": profile, "language": _language(language)}
    if overrides:
        request["overrides"] = overrides
    found = doc.run("segment", {**request, "unit": "chapters"})
    parts_found = doc.run("segment", {**request, "unit": "parts"})["parts"]
    scene_reply = doc.run("segment", {**request, "unit": "scenes"})
    scenes_found = scene_reply["scenes"]
    errors = [
        f"{o['kind']} {o['action']} {o['fp']}"
        + (f" (nth {o['nth']})" if "nth" in o else "")
        + ": no paragraph has this fingerprint"
        for o in found.get("unmatched_overrides", [])
    ]
    if not paragraphs:
        return Structure([], [], [], set(), set(), ["0 parts, 0 chapters, 0 scenes"]), errors

    def heading(unit: dict[str, Any]) -> list[int]:
        """The heading lines doc-control reports (title and subtitle); [] for none."""
        last = unit.get("heading_last")
        return [] if last is None else list(range(index(unit["first"]), index(last) + 1))

    def title(lines: list[int]) -> str:
        return " ".join(paragraphs[i] for i in lines)

    parts: list[Unit] = []
    for p in parts_found:
        lines = heading(p) or [index(p["first"])]
        parts.append(Unit(lines[0], lines, title(lines), "part", p["id"], list(p["signals"])))
    chapters: list[Unit] = []
    for c in found["chapters"]:
        lines = heading(c)
        signals = list(c["signals"])
        chapters.append(Unit(index(c["first"]), lines, title(lines), signals[0], c["id"], signals))
    first = min([c.start for c in chapters] + [p.start for p in parts] + [len(paragraphs)])
    if found.get("front") is not None or not chapters or first > 0:
        chapters.insert(0, Unit(0, [], "", "front"))

    scene_starts: set[int] = set()
    breaks: set[int] = set()
    scenes: list[Scene] = []
    for sc in scenes_found:
        i = index(sc["first"])
        signals = list(sc["signals"])
        scenes.append(Scene(i, sc["id"], signals))
        if signals and signals[0] in OPENING:
            continue
        if "scene_marker" in signals:
            breaks.add(i)
            if i + 1 < len(paragraphs):
                scene_starts.add(i + 1)
        else:
            scene_starts.add(i)
    # A scene break doc-control did not open a scene at (an ornament under a title, or
    # next to another break) is still a break: it stays in the heading block or closes
    # the scene before it. The in-process list of suppressed starts is whole.
    for row in scene_reply.get("suppressed", []):
        if row["kind"] == "scene" and row["reason"] == "no_text_between":
            breaks.add(index(_number(str(row["at"]))))
    for c in chapters:  # each chapter's first scene opens after its heading
        body = c.heading[-1] + 1 if c.heading else c.start
        while body in breaks or body in {p.start for p in parts}:
            body += 1
        scene_starts.add(body)
    counts = Counter(c.reason for c in chapters if c.reason != "front")
    signal_note = ", ".join(f"{k} {v}" for k, v in counts.most_common()) or "none"
    notes = [
        f"{len(parts)} parts, {len(chapters)} chapters, {len(scenes)} scenes",
        f"chapter signals: {signal_note}",
    ]
    if overrides:
        notes.append(f"overrides applied: {len(overrides) - len(errors)}")
    s = Structure(paragraphs, parts, chapters, scene_starts, breaks, notes, scenes)
    return s, errors


def _settings(
    kind: Any, paragraphs: list[str], meta: list[dict[str, Any]], fmt: str
) -> tuple[dict[str, Any], list[int]]:
    """The kind's ``segment`` profile for a draft in format ``fmt``, and the chapter
    starts the kind proposes."""
    profile = dict(getattr(kind, "PROFILE", {}))
    profile.update(getattr(kind, "FORMAT_PROFILE", {}).get(fmt, {}))
    propose = getattr(kind, "chapter_starts", None)
    return profile, (propose(paragraphs, meta) if propose else [])


def detect(
    paragraphs: list[str],
    meta: list[dict[str, Any]] | None = None,
    kind: str = kinds.DEFAULT,
    overrides: list[dict[str, Any]] | None = None,
    language: str = "es",
    fmt: str = "docx",
) -> Structure:
    """The structure of paragraphs held in memory (tests, examples).

    The paragraphs and their layout facts (``meta`` rows as ingest writes them)
    are written to a minimal ``.docx`` and segmented like an ingested draft of
    format ``fmt`` (``txt``, ``md``, ``odt`` or ``docx``).
    """
    from litcritic import convert
    from litcritic.ingest import Draft, Para, clean

    if meta is None or len(meta) != len(paragraphs):
        meta = [{} for _ in paragraphs]
    keys = ("heading", "centered", "page", "page_break_before", "blank_before", "style")
    draft = Draft(
        [
            Para(t, **{k: m[k] for k in keys if k in m})
            for t, m in zip(paragraphs, meta, strict=True)
        ],
        "docx",
    )
    module = kinds.get(kind)
    profile, starts = _settings(module, paragraphs, meta, fmt)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "draft.docx"
        path.write_bytes(convert.draft_to_docx(draft))
        with dc.open(path) as doc:
            rows = doc.paragraphs(normalized=True)
            ats = [str(r["at"]) for r in rows if clean(str(r.get("normalized", r["text"])))]
            if len(ats) != len(paragraphs):
                raise ValueError("paragraphs changed on their way through a .docx")
            s, errors = segment(
                doc, paragraphs, ats, profile, _forced(ats, starts) + (overrides or []), language
            )
    if errors:
        raise ValueError("; ".join(errors))
    return s


# --- anchors -------------------------------------------------------------------


def chapter_starts(s: Structure) -> list[int]:
    """First paragraph of each chapter, a part heading just before it included."""
    part_heads = {p.start for p in s.parts}
    part_lines = {i for p in s.parts for i in p.heading} | part_heads
    starts = [c.start for c in s.chapters]
    for ps in sorted(part_heads):
        for k, st in enumerate(starts):
            between = range(ps + 1, st)
            if st > ps and all(i in s.breaks or i in part_lines for i in between):
                starts[k] = min(st, ps)
                break
    return starts


def _anchor_list(s: Structure) -> list[str]:
    """``[pN.]cNN.sN.pN``: chapter 00 is front matter, scene 0 holds heading lines.

    A part heading belongs to scene 0 of the chapter that follows it; a scene
    break line is the last paragraph of the scene it closes.
    """
    n = len(s.paragraphs)
    part_heads = {p.start for p in s.parts}
    starts = chapter_starts(s)
    heads = {i for u in [*s.chapters, *s.parts] for i in u.heading} | part_heads
    has_front = bool(s.chapters) and s.chapters[0].reason == "front"
    out: list[str] = []
    ci, scene, counts = -1, 0, {0: 0}
    for i in range(n):
        while ci + 1 < len(starts) and i >= starts[ci + 1]:
            ci, scene, counts = ci + 1, 0, {0: 0}
        num = max(ci, 0) if has_front else ci + 1
        part = sum(1 for ps in part_heads if ps <= i)
        prefix = f"p{part}." if s.parts else ""
        if i in heads or (i in s.breaks and scene == 0):  # ornament under a title
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


def load_overrides(
    ws_root: Path, paragraphs: list[str], ats: list[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """The writer's overrides in doc-control's shape, and any that cannot be read.

    The first shape (12-hex fingerprint lists) is translated by paragraph text;
    when any of its entries is wrong, none is used.
    """
    f = ws_root / "analysis" / "structure-overrides.json"
    if not f.is_file():
        return [], []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [], [f"not valid JSON: {exc}"]
    if not isinstance(data, dict):
        return [], ["overrides must be a JSON object"]
    if "overrides" in data:
        items = data["overrides"]
        if not isinstance(items, list) or not all(isinstance(o, dict) for o in items):
            return [], ["overrides: expected a list of objects"]
        return items, []
    errors = [f"unknown key {k!r}" for k in data if k not in LEGACY_KEYS]
    where: dict[str, list[int]] = {}
    for i, t in enumerate(paragraphs):
        where.setdefault(fingerprint(t), []).append(i)
    out: list[dict[str, Any]] = []
    for key, (kind, action) in LEGACY_KEYS.items():
        items = data.get(key, [])
        if not isinstance(items, list):
            errors.append(f"{key}: expected a list of fingerprints")
            continue
        for fp in items:
            hits = where.get(str(fp), [])
            if len(hits) != 1:
                problem = "not found" if not hits else f"matches {len(hits)} paragraphs"
                errors.append(f"{key}: {fp} {problem}")
                continue
            o = _forced(ats, hits)[0]
            o.update(kind=kind, action=action)
            out.append(o)
    return ([], errors) if errors else (out, [])


# --- workspace I/O ----------------------------------------------------------------


def to_json(s: Structure, version: str) -> dict[str, Any]:
    anchors = s.anchors()
    words = [len(t.split()) for t in s.paragraphs]
    bounds = [*chapter_starts(s), len(s.paragraphs)]
    opened = [sc.start for sc in s.scenes]

    def dc_scene(i: int) -> Scene | None:
        k = bisect.bisect_right(opened, i) - 1
        return s.scenes[k] if k >= 0 else None

    chapters = []
    for k, c in enumerate(s.chapters):
        lo, hi = bounds[k], bounds[k + 1]
        cid = anchors[next((i for i in range(lo, hi) if i not in c.heading), lo)].split(".s")[0]
        scenes: dict[str, dict[str, Any]] = {}
        for i in range(lo, hi):
            sid = anchors[i].rsplit(".p", 1)[0]
            if sid.endswith(".s0"):
                continue
            if sid not in scenes:
                ds = dc_scene(i)
                scenes[sid] = {
                    "id": sid,
                    "start": i,
                    "end": i,
                    "words": 0,
                    "stable_id": ds.uid if ds else "",
                    "signals": ds.signals if ds else [],
                }
            sc = scenes[sid]
            sc["end"] = i
            sc["words"] += words[i]
        chapters.append(
            {
                "id": cid,
                "title": c.title or (s.paragraphs[c.heading[0]] if c.heading else ""),
                "reason": c.reason,
                "stable_id": c.uid,
                "signals": c.signals,
                "start": lo,
                "end": hi - 1,
                "words": sum(words[lo:hi]),
                "scenes": list(scenes.values()),
            }
        )
    return {
        "schema_version": 2,
        "version": version,
        "notes": s.notes,
        "parts": [
            {"n": n + 1, "title": p.title, "start": p.start, "stable_id": p.uid}
            for n, p in enumerate(s.parts)
        ],
        "chapters": chapters,
        "paragraphs": [[a, fingerprint(t)] for a, t in zip(anchors, s.paragraphs, strict=True)],
    }


def latest_version(ws_root: Path) -> str:
    texts = sorted((ws_root / "text").glob("v[0-9][0-9][0-9].txt"))
    if not texts:
        raise FileNotFoundError("no ingested draft; run `lc ingest` first")
    return texts[-1].stem


def _work_language(ws_root: Path) -> str:
    f = ws_root / "work.toml"
    try:
        return str(tomllib.loads(f.read_text(encoding="utf-8")).get("language") or "es")
    except (OSError, ValueError):
        return "es"


def build(ws_root: Path, version: str | None = None) -> tuple[Path, Structure, list[str]]:
    """Segment the draft with the kind's settings and the writer's overrides; write
    ``index/vNNN/structure.json``. Returns its path, the structure and override errors."""
    from litcritic import ingest

    version = version or latest_version(ws_root)
    text = (ws_root / "text" / f"{version}.txt").read_text(encoding="utf-8")
    paragraphs = text.split("\n")[:-1] if text.endswith("\n") else text.split("\n")
    meta_file = ws_root / "text" / f"{version}.meta.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.is_file() else {}
    rows = meta.get("paragraphs") or []
    ats = [str(r.get("at", "")) for r in rows]
    if len(rows) != len(paragraphs) or not all(ats) or ingest.converted_text(meta):
        raise ValueError(f"{version} was ingested by an older release; run `lc upgrade`")
    source = next(
        (p for p in (ws_root / "manuscript").glob(f"{version}.*") if p.suffix in ingest.FORMATS),
        None,
    )
    if source is None:
        raise FileNotFoundError(f"no manuscript/{version}.* to read the structure from")
    fmt = str(meta.get("format") or source.suffix[1:])
    profile, starts = _settings(kinds.of_work(ws_root), paragraphs, rows, fmt)
    overrides, errors = load_overrides(ws_root, paragraphs, ats)
    language = _work_language(ws_root)
    mode = ingest.text_mode(ws_root)
    with ingest.readable(source) as file, dc.open(file, text_mode=mode) as doc:
        try:
            s, unmatched = segment(
                doc, paragraphs, ats, profile, _forced(ats, starts) + overrides, language
            )
        except dc.DocError as exc:  # an override doc-control refuses: segment without them
            errors.append(f"{exc.code}: {exc}")
            s, unmatched = segment(doc, paragraphs, ats, profile, _forced(ats, starts), language)
    errors += unmatched
    out = ws_root / "index" / version / "structure.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(to_json(s, version), ensure_ascii=False) + "\n", encoding="utf-8")
    return out, s, errors
