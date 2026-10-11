"""Align two drafts paragraph by paragraph.

Every old paragraph gets a status — unchanged, moved, modified, split, merged
or deleted — and the new paragraphs it became; every new paragraph gets the
mirror status or ``inserted``. Matching runs in passes, each on what is left:

1. identical text (fingerprint), longest increasing run kept in place, the rest
   ``moved``;
2. one old paragraph equal to two or three consecutive new ones (``split``) and
   the reverse (``merged``) — before fuzzy matching, which would otherwise pair
   the old paragraph with its longest piece;
3. inside each gap between kept pairs, similar paragraphs (``modified``);
4. similar paragraphs anywhere (``modified`` far from home, i.e. moved+edited).

Stale scenes are the new scenes holding any paragraph that is not unchanged or
moved; their scene cards need re-reading.
"""

from __future__ import annotations

import bisect
import json
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from itertools import pairwise
from pathlib import Path
from typing import Any

from litcritic.structure import fingerprint

SIMILAR = 0.6  # word-level similarity for "the same paragraph, edited"
MAX_PAIRS = 250_000  # cap for the global (pass 4) comparison


@dataclass
class Alignment:
    old: list[dict[str, Any]]  # per old paragraph: {"status", "new": [j...], "ratio"?}
    new: list[dict[str, Any]]  # per new paragraph: {"status", "old": [i...]}
    counts: dict[str, int] = field(default_factory=dict)

    def mapping(self) -> dict[int, int]:
        """Old index -> new index for paragraphs that kept their text."""
        return {
            i: e["new"][0] for i, e in enumerate(self.old) if e["status"] in ("unchanged", "moved")
        }


def _norm(text: str) -> list[str]:
    return text.casefold().split()


def _ratio(a: str, b: str) -> float:
    wa, wb = _norm(a), _norm(b)
    if not wa or not wb:
        return 0.0
    sm = SequenceMatcher(None, wa, wb, autojunk=False)
    if sm.real_quick_ratio() < SIMILAR or sm.quick_ratio() < SIMILAR:
        return 0.0
    return sm.ratio()


def _lis(pairs: list[tuple[int, int]]) -> set[tuple[int, int]]:
    """Longest chain of pairs increasing in both indices (pairs sorted by old index)."""
    tails: list[int] = []
    tails_idx: list[int] = []
    prev = [-1] * len(pairs)
    for k, (_, j) in enumerate(pairs):
        pos = bisect.bisect_left(tails, j)
        if pos == len(tails):
            tails.append(j)
            tails_idx.append(k)
        else:
            tails[pos] = j
            tails_idx[pos] = k
        prev[k] = tails_idx[pos - 1] if pos else -1
    out: set[tuple[int, int]] = set()
    k = tails_idx[-1] if tails_idx else -1
    while k >= 0:
        out.add(pairs[k])
        k = prev[k]
    return out


def align(old: list[str], new: list[str]) -> Alignment:
    o: list[dict[str, Any]] = [{"status": "deleted", "new": []} for _ in old]
    n: list[dict[str, Any]] = [{"status": "inserted", "old": []} for _ in new]

    def link(i: int, j: int, status: str, ratio: float | None = None) -> None:
        o[i] = {"status": status, "new": [j]}
        n[j] = {"status": status, "old": [i]}
        if ratio is not None:
            o[i]["ratio"] = round(ratio, 3)

    # Pass 1: identical text. Duplicates pair up in order of appearance.
    by_fp: dict[str, list[int]] = defaultdict(list)
    for j, t in enumerate(new):
        by_fp[fingerprint(t)].append(j)
    used: dict[str, int] = defaultdict(int)
    pairs: list[tuple[int, int]] = []
    for i, t in enumerate(old):
        fp = fingerprint(t)
        k = used[fp]
        if k < len(by_fp.get(fp, [])):
            pairs.append((i, by_fp[fp][k]))
            used[fp] += 1
    keep = _lis(pairs)
    for i, j in pairs:
        link(i, j, "unchanged" if (i, j) in keep else "moved")

    # Pass 2: splits and merges among what is still unmatched.
    _splits_and_merges(old, new, o, n)

    # Pass 3: similar paragraphs inside the gaps between kept pairs.
    anchors = sorted(keep)
    bounds = [(-1, -1), *anchors, (len(old), len(new))]
    for (i0, j0), (i1, j1) in pairwise(bounds):
        olds = [i for i in range(i0 + 1, i1) if o[i]["status"] == "deleted"]
        news = [j for j in range(j0 + 1, j1) if n[j]["status"] == "inserted"]
        _match_similar(olds, news, old, new, o, n, link, ordered=True)

    # Pass 4: similar paragraphs anywhere (moved and edited).
    olds = [i for i, e in enumerate(o) if e["status"] == "deleted"]
    news = [j for j, e in enumerate(n) if e["status"] == "inserted"]
    if olds and news and len(olds) * len(news) <= MAX_PAIRS:
        _match_similar(olds, news, old, new, o, n, link, ordered=False)

    counts: dict[str, int] = defaultdict(int)
    for e in o:
        counts[e["status"]] += 1
    counts["inserted"] = sum(1 for e in n if e["status"] == "inserted")
    return Alignment(o, n, dict(sorted(counts.items())))


def _match_similar(
    olds: list[int],
    news: list[int],
    old: list[str],
    new: list[str],
    o: list[dict[str, Any]],
    n: list[dict[str, Any]],
    link: Any,
    ordered: bool,
) -> None:
    """Greedy best-first pairing by similarity; ``ordered`` keeps pairs non-crossing."""
    cands: list[tuple[float, int, int]] = []
    for i in olds:
        for j in news:
            r = _ratio(old[i], new[j])
            if r >= SIMILAR:
                cands.append((r, i, j))
    cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    taken: list[tuple[int, int]] = []
    for r, i, j in cands:
        if o[i]["status"] != "deleted" or n[j]["status"] != "inserted":
            continue
        if ordered and any((i < a) != (j < b) for a, b in taken):
            continue
        link(i, j, "modified", r)
        taken.append((i, j))


def _splits_and_merges(
    old: list[str], new: list[str], o: list[dict[str, Any]], n: list[dict[str, Any]]
) -> None:
    def free_old(i: int) -> bool:
        return 0 <= i < len(old) and o[i]["status"] == "deleted"

    def free_new(j: int) -> bool:
        return 0 <= j < len(new) and n[j]["status"] == "inserted"

    for i, text in enumerate(old):
        if not free_old(i):
            continue
        target = _norm(text)
        for j in range(len(new)):
            if not free_new(j) or target[:3] != _norm(new[j])[:3]:
                continue
            for size in (2, 3):
                js = list(range(j, j + size))
                if not all(free_new(x) for x in js):
                    break
                joined = " ".join(new[x] for x in js)
                if _ratio(text, joined) >= 0.9:
                    o[i] = {"status": "split", "new": js}
                    for x in js:
                        n[x] = {"status": "split", "old": [i]}
                    break
            if o[i]["status"] == "split":
                break
    for j, text in enumerate(new):
        if not free_new(j):
            continue
        target = _norm(text)
        for i in range(len(old)):
            if not free_old(i) or target[:3] != _norm(old[i])[:3]:
                continue
            for size in (2, 3):
                is_ = list(range(i, i + size))
                if not all(free_old(x) for x in is_):
                    break
                joined = " ".join(old[x] for x in is_)
                if _ratio(joined, text) >= 0.9:
                    n[j] = {"status": "merged", "old": is_}
                    for x in is_:
                        o[x] = {"status": "merged", "new": [j]}
                    break
            if n[j]["status"] == "merged":
                break


# --- workspace I/O -----------------------------------------------------------------


def _load(ws_root: Path, version: str) -> tuple[list[str], dict[str, Any]]:
    text = (ws_root / "text" / f"{version}.txt").read_text(encoding="utf-8")
    paras = text.split("\n")[:-1] if text.endswith("\n") else text.split("\n")
    struct_file = ws_root / "index" / version / "structure.json"
    if not struct_file.is_file():
        raise FileNotFoundError(f"no structure for {version}; run `lc anchor --version {version}`")
    return paras, json.loads(struct_file.read_text(encoding="utf-8"))


def build(ws_root: Path, va: str, vb: str) -> tuple[Path, Alignment, dict[str, Any]]:
    """Write ``index/<vb>/alignment.json`` mapping ``va`` anchors to ``vb`` anchors."""
    old, s_old = _load(ws_root, va)
    new, s_new = _load(ws_root, vb)
    al = align(old, new)
    a_old = [a for a, _ in s_old["paragraphs"]]
    a_new = [a for a, _ in s_new["paragraphs"]]
    scene_of = {}
    for ch in s_new["chapters"]:
        for sc in ch["scenes"]:
            for j in range(sc["start"], sc["end"] + 1):
                scene_of[j] = sc["id"]
    stale = sorted(
        {
            scene_of[j]
            for j, e in enumerate(al.new)
            if e["status"] not in ("unchanged", "moved") and j in scene_of
        }
    )
    removed_from = sorted(
        {
            a_old[i].rsplit(".p", 1)[0]
            for i, e in enumerate(al.old)
            if e["status"] in ("deleted", "moved", "merged", "split")
        }
    )
    data = {
        "schema_version": 1,
        "from": va,
        "to": vb,
        "counts": al.counts,
        "stale_scenes": stale,
        "old_scenes_touched": removed_from,
        "old": [
            {"a": a_old[i], "status": e["status"], "new": [a_new[j] for j in e["new"]]}
            | ({"ratio": e["ratio"]} if "ratio" in e else {})
            for i, e in enumerate(al.old)
        ],
        "inserted": [a_new[j] for j, e in enumerate(al.new) if e["status"] == "inserted"],
    }
    out = ws_root / "index" / vb / "alignment.json"
    out.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    return out, al, data
