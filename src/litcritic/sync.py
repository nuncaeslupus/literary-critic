"""Bring a Codex up to a new draft, flagging exactly what the change touched.

1. Align the synced draft with the new one (``diff.align``).
2. Relocate every span (``spans.relocate``): kept text moves silently; changed
   or lost text is flagged.
3. Items with a changed or lost span become ``needs_reread``, and so does every
   item that depends on one of them (one hop over ``depends_on``, ``refers_to``
   and ``pays_off`` links pointing at it).
4. Names the draft replaced consistently (a renamed character) become the
   entity's new name, the old one kept as an alias, so the entity keeps its id.
5. ``codex/reread.jsonl`` lists what to re-read and why; ``codex.toml`` records
   the synced draft.
"""

from __future__ import annotations

import difflib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from litcritic import diff, query, structure
from litcritic import spans as spanlib
from litcritic.codex import Codex, Item, _write_atomic
from litcritic.textstats import WORD

HOP = ("depends_on", "refers_to", "pays_off")
RENAME_MIN = 2  # consistent substitutions needed before a name counts as renamed


@dataclass
class Report:
    old: str
    new: str
    moved: int = 0
    changed: list[str] = field(default_factory=list)
    lost: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str, str]] = field(default_factory=list)  # (entity, old, new)

    @property
    def flagged(self) -> list[str]:
        return sorted({*self.changed, *self.lost, *self.dependents})

    def lines(self) -> list[str]:
        out = [f"synced {self.old} -> {self.new}: {self.moved} spans moved"]
        out += [f"renamed {e}: {a} -> {b}" for e, a, b in self.renamed]
        if self.changed:
            out.append(f"text changed under {len(self.changed)} item(s): {', '.join(self.changed)}")
        if self.lost:
            out.append(f"text gone for {len(self.lost)} item(s): {', '.join(self.lost)}")
        if self.dependents:
            out.append(f"depend on those: {', '.join(self.dependents)}")
        out.append(
            f"re-read queue: {len(self.flagged)} item(s) (lc codex sql or codex/reread.jsonl)"
        )
        return out


def _text(work_root: Path, draft: str) -> spanlib.Text:
    ix = query.load(work_root, draft)
    return spanlib.Text(ix.paragraphs, ix.anchors, draft)


def _renames(cx: Codex, old: spanlib.Text, new: spanlib.Text, al: diff.Alignment) -> dict[str, str]:
    """Old name word -> new word, for entity names the new draft replaced consistently."""
    names = {
        w
        for e in cx.of_type("entity")
        if e.status != "retired"
        for n in [e.fields.get("name", ""), *e.fields.get("aliases", [])]
        for w in WORD.findall(n)
    }
    subs: Counter[tuple[str, str]] = Counter()
    for i, entry in enumerate(al.old):
        if entry["status"] not in ("modified", "split", "merged"):
            continue
        a = WORD.findall(old.paragraphs[i])
        b = [w for j in entry["new"] for w in WORD.findall(new.paragraphs[j])]
        for tag, i0, i1, j0, j1 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
            if tag == "replace" and i1 - i0 == j1 - j0:
                subs.update(
                    (x, y) for x, y in zip(a[i0:i1], b[j0:j1], strict=True) if x in names and x != y
                )
    still = set(WORD.findall(new.joined))
    best: dict[str, tuple[str, int]] = {}
    for (x, y), n in subs.items():
        if n >= RENAME_MIN and x not in still and n > best.get(x, ("", 0))[1]:
            best[x] = (y, n)
    return {x: y for x, (y, _) in best.items()}


def _rename_entities(cx: Codex, renames: dict[str, str], report: Report) -> list[Item]:
    out = []
    for e in cx.of_type("entity"):
        name = e.fields.get("name", "")
        aliases = list(e.fields.get("aliases", []))
        new_name = " ".join(renames.get(w, w) for w in name.split())
        new_aliases = [" ".join(renames.get(w, w) for w in a.split()) for a in aliases]
        if new_name == name and new_aliases == aliases:
            continue
        keep = [a for a in dict.fromkeys([name, *aliases, *new_aliases]) if a != new_name]
        fields = {**e.fields, "name": new_name, "aliases": keep}
        out.append(Item.from_json({**e.as_json(), "fields": fields}))
        report.renamed.append((e.id, name, new_name))
    return out


def sync(work_root: Path, to: str | None = None, cx: Codex | None = None) -> Report:
    cx = cx or Codex(work_root)
    new_draft = to or structure.latest_version(work_root)
    report = Report(cx.draft, new_draft)
    if new_draft == cx.draft:
        return report
    old, new = _text(work_root, cx.draft), _text(work_root, new_draft)
    al = diff.align(old.paragraphs, new.paragraphs)
    kept = al.mapping()
    updates: dict[str, Item] = {}
    for item in cx.items.values():
        if item.status == "retired" or not item.spans:
            continue
        moved = [spanlib.relocate(s, old, new, al, new_draft, kept) for s in item.spans]
        states = {s.state for s in moved}
        report.moved += sum(s.state == "moved" for s in moved)
        status = item.status
        if "lost" in states:
            report.lost.append(item.id)
            status = "needs_reread"
        elif "changed" in states:
            report.changed.append(item.id)
            status = "needs_reread"
        copy = Item.from_json({**item.as_json(), "status": status})
        copy.spans = moved
        updates[item.id] = copy
    hit = {*report.changed, *report.lost}
    for target in sorted(hit):
        for src, rel in cx.linked_to(target):
            if rel in HOP and src.status != "retired" and src.id not in hit:
                base = updates.get(src.id) or Item.from_json(src.as_json())
                base.status = "needs_reread"
                updates[src.id] = base
                if src.id not in report.dependents:
                    report.dependents.append(src.id)
    for e in _rename_entities(cx, _renames(cx, old, new, al), report):
        updates[e.id] = e
    previous = dict(cx.meta)
    cx.set_meta(synced_draft=new_draft, last_sync=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    try:
        cx.replace_all(list(updates.values()), op="sync", by="script")
    except Exception:
        cx.set_meta(**previous)
        raise
    queue = [
        {"item": i, "reason": r}
        for r, ids in (
            ("changed", report.changed),
            ("lost", report.lost),
            ("depends", report.dependents),
        )
        for i in ids
    ]
    _write_atomic(
        cx.root / "reread.jsonl",
        "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in queue),
    )
    report.changed.sort()
    report.lost.sort()
    report.dependents.sort()
    return report
