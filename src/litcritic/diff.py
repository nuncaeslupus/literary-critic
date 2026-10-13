"""Align two drafts paragraph by paragraph, through doc-control's ``diff``.

doc-control aligns the two documents (the manuscript snapshots, or the ``.docx``
copies converted from ``.txt``, ``.md`` and ``.odt``) and returns change records
and an address map (old address -> new address, or none for a paragraph that is
gone). This module only translates that into the workspace's paragraphs, which
hold each doc-control address in ``text/vNNN.meta.json``: every old paragraph
gets a status — unchanged, moved, modified, split, merged or deleted — and the
new paragraphs it became; every new paragraph gets the mirror status or
``inserted``. ``unchanged`` means in order (its number may have shifted);
``moved`` is the same text out of order; ``modified`` is edited text, in place or
not (doc-control's ``moved`` flag is kept).

Stale scenes are the new scenes holding any paragraph that is not unchanged, or
where an old paragraph left; their Codex items need re-reading.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from litcritic import dc

KEPT = ("unchanged", "moved")  # statuses whose paragraph kept its text


@dataclass
class Alignment:
    old: list[dict[str, Any]]  # per old paragraph: {"status", "new": [j...], "ratio"?, "moved"?}
    new: list[dict[str, Any]]  # per new paragraph: {"status", "old": [i...]}
    counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    old_at: list[str] = field(default_factory=list)  # doc-control address of each old paragraph
    new_at: list[str] = field(default_factory=list)
    address_map: dict[str, str | None] = field(default_factory=dict)  # old at -> new at | None

    def mapping(self) -> dict[int, int]:
        """Old index -> new index for paragraphs that kept their text (from the address map)."""
        where = {a: j for j, a in enumerate(self.new_at)}
        out: dict[int, int] = {}
        for i, e in enumerate(self.old):
            target = self.address_map.get(self.old_at[i])
            if e["status"] in KEPT and target in where:
                out[i] = where[target]
        return out


def _number(at: str) -> int:
    m = re.match(r"p(\d+)#", at)
    if not m:
        raise ValueError(f"not a doc-control paragraph address: {at!r}")
    return int(m.group(1))


def from_diff(result: dict[str, Any], old_at: list[str], new_at: list[str]) -> Alignment:
    """The workspace alignment from a whole doc-control ``diff`` result.

    ``old_at`` / ``new_at`` are the addresses of the workspace's paragraphs (blank
    paragraphs of the documents have none and are left out of every record).
    """
    oi = {_number(a): i for i, a in enumerate(old_at)}
    nj = {_number(a): j for j, a in enumerate(new_at)}
    o: list[dict[str, Any]] = [{"status": "unchanged", "new": []} for _ in old_at]
    n: list[dict[str, Any]] = [{"status": "unchanged", "old": []} for _ in new_at]
    listed_old: set[int] = set()
    listed_new: set[int] = set()
    amap: dict[str, str | None] = {}
    for rec in result.get("changes", []):
        if "count" in rec:
            raise ValueError("collapsed diff records are not supported; ask without collapse_runs")
        olds = [oi[k] for k in map(_number, rec["old"]) if k in oi]
        news = [nj[k] for k in map(_number, rec["new"]) if k in nj]
        listed_old.update(olds)
        listed_new.update(news)
        kind = str(rec["kind"])
        for i in olds:
            if kind == "inserted" or not news:
                o[i] = {"status": "deleted", "new": []}
                continue
            o[i] = {"status": kind, "new": news}
            if "similarity" in rec and kind == "modified":
                o[i]["ratio"] = round(float(rec["similarity"]), 3)
            if rec.get("moved"):
                o[i]["moved"] = True
        for j in news:
            n[j] = {"status": kind if olds else "inserted", "old": olds}
    amap.update(result.get("address_map", {}))
    # Unlisted paragraphs kept their address: unchanged, same number on both sides.
    for i, a in enumerate(old_at):
        if i in listed_old:
            continue
        same = nj.get(_number(a))
        if same is None or same in listed_new:
            o[i] = {"status": "deleted", "new": []}
            amap.setdefault(a, None)
            continue
        o[i] = {"status": "unchanged", "new": [same]}
        n[same] = {"status": "unchanged", "old": [i]}
        listed_new.add(same)
        amap.setdefault(a, new_at[same])
    for j in range(len(new_at)):
        if j not in listed_new:
            n[j] = {"status": "inserted", "old": []}
    counts: dict[str, int] = defaultdict(int)
    for e in o:
        counts[e["status"]] += 1
    counts["inserted"] = sum(1 for e in n if e["status"] == "inserted")
    return Alignment(o, n, dict(sorted(counts.items())), [], list(old_at), list(new_at), amap)


def align_documents(
    old_docx: Path, new_docx: Path, old_at: list[str], new_at: list[str]
) -> Alignment:
    """doc-control's ``diff`` of two ``.docx`` files, onto the paragraphs at those addresses."""
    with dc.open(old_docx) as doc:
        result = doc.run("diff", {"old": str(old_docx), "new": str(new_docx)})
    if result.get("next"):
        raise ValueError("doc-control returned a partial diff")
    return from_diff(result, old_at, new_at)


# --- paragraphs held in memory (tests, measurements) ----------------------------


@contextmanager
def _as_docx(paragraphs: list[str], folder: Path, name: str) -> Iterator[tuple[Path, list[str]]]:
    from litcritic import convert
    from litcritic.ingest import Draft, Para, clean

    path = folder / f"{name}.docx"
    path.write_bytes(convert.draft_to_docx(Draft([Para(t) for t in paragraphs], "docx")))
    with dc.open(path) as doc:
        rows = doc.paragraphs(normalized=True)
    ats = [str(r["at"]) for r in rows if clean(str(r.get("normalized", r["text"])))]
    if len(ats) != len(paragraphs):
        raise ValueError("paragraphs changed on their way through a .docx")
    yield path, ats


def align(old: list[str], new: list[str]) -> Alignment:
    """Align paragraphs held in memory, written to minimal ``.docx`` copies first."""
    with (
        tempfile.TemporaryDirectory() as tmp,
        _as_docx(old, Path(tmp), "old") as (a, a_at),
        _as_docx(new, Path(tmp), "new") as (b, b_at),
    ):
        return align_documents(a, b, a_at, b_at)


# --- workspace I/O -----------------------------------------------------------------


def _addresses(ws_root: Path, version: str, count: int) -> list[str]:
    meta_file = ws_root / "text" / f"{version}.meta.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.is_file() else {}
    ats = [str(r.get("at", "")) for r in meta.get("paragraphs") or []]
    if len(ats) != count or not all(ats):
        raise ValueError(f"{version} was ingested by an older release; run `lc ingest` again")
    return ats


def _manuscript(ws_root: Path, version: str) -> Path:
    from litcritic import ingest

    found = [p for p in (ws_root / "manuscript").glob(f"{version}.*") if p.suffix in ingest.FORMATS]
    if not found:
        raise FileNotFoundError(f"no manuscript/{version}.* to compare")
    return found[0]


def versions(ws_root: Path, va: str, vb: str) -> Alignment:
    """Align two ingested drafts of a workspace (their manuscript snapshots)."""
    from litcritic import ingest

    counts = []
    for v in (va, vb):
        text = (ws_root / "text" / f"{v}.txt").read_text(encoding="utf-8")
        counts.append(len(text.split("\n")) - (1 if text.endswith("\n") else 0))
    old_at = _addresses(ws_root, va, counts[0])
    new_at = _addresses(ws_root, vb, counts[1])
    with (
        ingest.docx_of(_manuscript(ws_root, va)) as (a, _),
        ingest.docx_of(_manuscript(ws_root, vb)) as (b, _),
    ):
        return align_documents(a, b, old_at, new_at)


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
    al = versions(ws_root, va, vb)
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
            | ({"moved": True} if e.get("moved") else {})
            for i, e in enumerate(al.old)
        ],
        "inserted": [a_new[j] for j, e in enumerate(al.new) if e["status"] == "inserted"],
    }
    out = ws_root / "index" / vb / "alignment.json"
    out.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    return out, al, data
