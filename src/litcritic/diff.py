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
moved; their Codex items need re-reading.
"""

from __future__ import annotations

import bisect
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from itertools import pairwise
from pathlib import Path
from typing import Any

from litcritic.structure import fingerprint

SIMILAR = 0.6  # word-level similarity for "the same paragraph, edited"
GAP_PAIRS = 40_000  # above this, a gap is compared along a diagonal band only
BAND = 40  # half-width of that band, in paragraphs
MAX_PAIRS = 250_000  # cap for the global (pass 4) comparison


@dataclass
class Alignment:
    old: list[dict[str, Any]]  # per old paragraph: {"status", "new": [j...], "ratio"?}
    new: list[dict[str, Any]]  # per new paragraph: {"status", "old": [i...]}
    counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def mapping(self) -> dict[int, int]:
        """Old index -> new index for paragraphs that kept their text."""
        return {
            i: e["new"][0] for i, e in enumerate(self.old) if e["status"] in ("unchanged", "moved")
        }


class _Words:
    """Case-folded word lists, computed once per paragraph."""

    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.cache: dict[int, list[str]] = {}

    def __getitem__(self, i: int) -> list[str]:
        if i not in self.cache:
            self.cache[i] = self.texts[i].casefold().split()
        return self.cache[i]


def _ratio_words(wa: list[str], wb: list[str]) -> float:
    if not wa or not wb:
        return 0.0
    sm = SequenceMatcher(None, wa, wb, autojunk=False)
    if sm.real_quick_ratio() < SIMILAR or sm.quick_ratio() < SIMILAR:
        return 0.0
    return sm.ratio()


def _ratio(a: str, b: str) -> float:
    return _ratio_words(a.casefold().split(), b.casefold().split())


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


class _Aligner:
    def __init__(self, old: list[str], new: list[str]) -> None:
        self.old_t, self.new_t = old, new
        self.ow, self.nw = _Words(old), _Words(new)
        self.o: list[dict[str, Any]] = [{"status": "deleted", "new": []} for _ in old]
        self.n: list[dict[str, Any]] = [{"status": "inserted", "old": []} for _ in new]
        self.notes: list[str] = []

    def link(self, i: int, j: int, status: str, ratio: float | None = None) -> None:
        self.o[i] = {"status": status, "new": [j]}
        self.n[j] = {"status": status, "old": [i]}
        if ratio is not None:
            self.o[i]["ratio"] = round(ratio, 3)

    def free_old(self, i: int) -> bool:
        return 0 <= i < len(self.o) and self.o[i]["status"] == "deleted"

    def free_new(self, j: int) -> bool:
        return 0 <= j < len(self.n) and self.n[j]["status"] == "inserted"

    def gaps(self) -> list[tuple[list[int], list[int]]]:
        """Unmatched old/new indices between consecutive in-place matches."""
        kept = sorted((i, e["new"][0]) for i, e in enumerate(self.o) if e["status"] == "unchanged")
        out = []
        for (i0, j0), (i1, j1) in pairwise([(-1, -1), *kept, (len(self.o), len(self.n))]):
            olds = [i for i in range(i0 + 1, i1) if self.free_old(i)]
            news = [j for j in range(j0 + 1, j1) if self.free_new(j)]
            if olds and news:
                out.append((olds, news))
        return out

    def exact(self) -> None:
        """Unique identical paragraphs anchor the order; repeats are paired within gaps."""
        ofp = [fingerprint(t) for t in self.old_t]
        nfp = [fingerprint(t) for t in self.new_t]
        oc, nc = Counter(ofp), Counter(nfp)
        nidx = {fp: j for j, fp in enumerate(nfp) if nc[fp] == 1}
        pairs = [(i, nidx[fp]) for i, fp in enumerate(ofp) if oc[fp] == 1 and fp in nidx]
        keep = _lis(pairs)
        for i, j in pairs:
            self.link(i, j, "unchanged" if (i, j) in keep else "moved")
        # Repeated texts (scene breaks, short replies): in order, inside each gap.
        for olds, news in self.gaps():
            sm = SequenceMatcher(
                None, [ofp[i] for i in olds], [nfp[j] for j in news], autojunk=False
            )
            for a, b, size in sm.get_matching_blocks():
                for k in range(size):
                    self.link(olds[a + k], news[b + k], "unchanged")
        # Whatever identical text is left has moved.
        pending: dict[str, list[int]] = defaultdict(list)
        for j, fp in enumerate(nfp):
            if self.free_new(j):
                pending[fp].append(j)
        for i, fp in enumerate(ofp):
            if self.free_old(i) and pending.get(fp):
                self.link(i, pending[fp].pop(0), "moved")

    def splits_and_merges(self) -> None:
        """One paragraph equal to 2-3 consecutive ones nearby, in either direction."""
        for olds, news in self.gaps():
            free_n = set(news)
            for i in olds:
                if not self.free_old(i):
                    continue
                head = self.ow[i][:3]
                for j in news:
                    if j not in free_n or self.nw[j][:3] != head:
                        continue
                    for size in (2, 3):
                        js = list(range(j, j + size))
                        if not all(x in free_n for x in js):
                            break
                        joined = [w for x in js for w in self.nw[x]]
                        if _ratio_words(self.ow[i], joined) >= 0.9:
                            self.o[i] = {"status": "split", "new": js}
                            for x in js:
                                self.n[x] = {"status": "split", "old": [i]}
                                free_n.discard(x)
                            break
                    if not self.free_old(i):
                        break
            free_o = {i for i in olds if self.free_old(i)}
            for j in news:
                if not self.free_new(j):
                    continue
                head = self.nw[j][:3]
                for i in olds:
                    if i not in free_o or self.ow[i][:3] != head:
                        continue
                    for size in (2, 3):
                        is_ = list(range(i, i + size))
                        if not all(x in free_o for x in is_):
                            break
                        joined = [w for x in is_ for w in self.ow[x]]
                        if _ratio_words(joined, self.nw[j]) >= 0.9:
                            self.n[j] = {"status": "merged", "old": is_}
                            for x in is_:
                                self.o[x] = {"status": "merged", "new": [j]}
                                free_o.discard(x)
                            break
                    if not self.free_new(j):
                        break

    def similar(self, olds: list[int], news: list[int], ordered: bool) -> None:
        """Greedy best-first pairing by similarity; ``ordered`` keeps pairs non-crossing."""
        banded = len(olds) * len(news) > GAP_PAIRS
        cands: list[tuple[float, int, int]] = []
        for k, i in enumerate(olds):
            if banded:
                centre = k * len(news) // len(olds)
                window = news[max(0, centre - BAND) : centre + BAND + 1]
            else:
                window = news
            for j in window:
                r = _ratio_words(self.ow[i], self.nw[j])
                if r >= SIMILAR:
                    cands.append((r, i, j))
        if banded:
            self.notes.append(f"large gap ({len(olds)}x{len(news)}) compared along a band")
        cands.sort(key=lambda c: (-c[0], c[1], c[2]))
        taken_i: list[int] = []
        taken_j: list[int] = []
        for r, i, j in cands:
            if not self.free_old(i) or not self.free_new(j):
                continue
            if ordered:
                pos = bisect.bisect_left(taken_i, i)
                if (pos and taken_j[pos - 1] > j) or (pos < len(taken_j) and taken_j[pos] < j):
                    continue
                taken_i.insert(pos, i)
                taken_j.insert(pos, j)
            self.link(i, j, "modified", r)


def align(old: list[str], new: list[str]) -> Alignment:
    a = _Aligner(old, new)
    a.exact()
    a.splits_and_merges()
    for olds, news in a.gaps():
        a.similar(olds, news, ordered=True)
    olds = [i for i in range(len(old)) if a.free_old(i)]
    news = [j for j in range(len(new)) if a.free_new(j)]
    if olds and news:
        if len(olds) * len(news) <= MAX_PAIRS:
            a.similar(olds, news, ordered=False)
        else:
            a.notes.append(
                f"moved-and-edited search skipped ({len(olds)} x {len(news)} unmatched); "
                "some paragraphs may show as deleted + inserted"
            )
    counts: dict[str, int] = defaultdict(int)
    for e in a.o:
        counts[e["status"]] += 1
    counts["inserted"] = sum(1 for e in a.n if e["status"] == "inserted")
    return Alignment(a.o, a.n, dict(sorted(counts.items())), a.notes)


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
    a_old = [a for a, _ in s_old.get("paragraphs", [])]
    a_new = [a for a, _ in s_new.get("paragraphs", [])]
    for v, paras, anchors in ((va, old, a_old), (vb, new, a_new)):
        if len(paras) != len(anchors):
            raise ValueError(f"structure for {v} is out of date; run `lc anchor --version {v}`")
    al = align(old, new)
    scene_of: dict[int, str] = {}
    for ch in s_new.get("chapters", []):
        for sc in ch["scenes"]:
            for j in range(sc["start"], sc["end"] + 1):
                scene_of[j] = sc["id"]
    stale = {
        scene_of[j]
        for j, e in enumerate(al.new)
        if e["status"] not in ("unchanged",) and j in scene_of
    }
    # A scene that only lost text is stale too: find where the loss sits in the
    # new draft (after the nearest earlier paragraph that kept its place).
    last_kept = -1
    for e in al.old:
        if e["status"] == "unchanged":
            last_kept = e["new"][0]
        elif e["status"] in ("deleted", "moved", "merged", "split"):
            anchor_j = last_kept if last_kept >= 0 else 0
            if anchor_j in scene_of:
                stale.add(scene_of[anchor_j])
    touched = sorted(
        {a_old[i].rsplit(".p", 1)[0] for i, e in enumerate(al.old) if e["status"] != "unchanged"}
    )
    data = {
        "schema_version": 1,
        "from": va,
        "to": vb,
        "counts": al.counts,
        "notes": al.notes,
        "stale_scenes": sorted(stale),
        "old_scenes_touched": touched,
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
