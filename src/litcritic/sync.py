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
from litcritic.codex import Codex, CodexError, Item, _check_draft, _write_atomic
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
    notes: list[str] = field(default_factory=list)

    @property
    def flagged(self) -> list[str]:
        return sorted({*self.changed, *self.lost, *self.dependents})

    def lines(self) -> list[str]:
        out = [f"synced {self.old} -> {self.new}: {self.moved} spans moved"]
        out += [f"renamed {e}: {a} -> {b}" for e, a, b in self.renamed]
        out += self.notes
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
    if not names:
        return {}
    subs: Counter[tuple[str, str]] = Counter()
    for i, entry in enumerate(al.old):
        if entry["status"] not in ("modified", "split", "merged"):
            continue
        a = WORD.findall(old.paragraphs[i])
        if names.isdisjoint(a):
            continue
        b = [w for j in entry["new"] for w in WORD.findall(new.paragraphs[j])]
        for tag, i0, i1, j0, j1 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
            if tag == "replace" and i1 - i0 == j1 - j0:
                subs.update(
                    (x, y) for x, y in zip(a[i0:i1], b[j0:j1], strict=True) if x in names and x != y
                )
    if not subs:
        return {}
    still = set(WORD.findall(new.joined))
    best: dict[str, tuple[str, int]] = {}
    for (x, y), n in subs.items():
        if n >= RENAME_MIN and x not in still and n > best.get(x, ("", 0))[1]:
            best[x] = (y, n)
    return {x: y for x, (y, _) in best.items()}


def _rename_entities(
    cx: Codex, renames: dict[str, str], updates: dict[str, Item], report: Report
) -> None:
    """Apply renames to active entities, keeping old names as aliases; skip clashes."""
    if not renames:
        return

    def swap(text: str) -> str:
        return WORD.sub(lambda m: renames.get(m.group(), m.group()), text)

    active = [e for e in cx.of_type("entity") if e.status != "retired"]
    for e in active:
        base = updates.get(e.id) or Item.from_json(e.as_json())
        name = base.fields.get("name", "")
        aliases = list(base.fields.get("aliases", []))
        new_name = swap(name)
        new_aliases = [swap(a) for a in aliases]
        if new_name == name and new_aliases == aliases:
            continue
        taken = {
            n.casefold()
            for o in active
            if o.id != e.id
            for n in [o.fields.get("name", ""), *o.fields.get("aliases", [])]
        }
        if {new_name.casefold(), *(a.casefold() for a in new_aliases)} & taken:
            report.notes.append(
                f"{e.id}: {name} -> {new_name} not applied (name of another entity)"
            )
            continue
        keep = [a for a in dict.fromkeys([name, *aliases, *new_aliases]) if a != new_name]
        base.fields = {**base.fields, "name": new_name, "aliases": keep}
        updates[e.id] = base
        report.renamed.append((e.id, name, new_name))


def sync(work_root: Path, to: str | None = None, cx: Codex | None = None) -> Report:
    cx = cx or Codex(work_root)
    new_draft = to or structure.latest_version(work_root)
    _check_draft(work_root, new_draft)
    report = Report(cx.draft, new_draft)
    if new_draft == cx.draft:
        return report
    if int(new_draft[1:]) < int(cx.draft[1:]):
        raise CodexError(f"the Codex is at {cx.draft}; it does not go back to {new_draft}")
    if cx.damaged:
        raise CodexError(f"fix the unreadable rows first (lc codex check): {sorted(cx.damaged)}")
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
    dependents: set[str] = set()
    for target in sorted(hit):
        for src, rel in cx.linked_to(target):
            if rel in HOP and src.status != "retired" and src.id not in hit:
                base = updates.get(src.id) or Item.from_json(src.as_json())
                base.status = "needs_reread"
                updates[src.id] = base
                dependents.add(src.id)
    report.dependents = sorted(dependents)
    _rename_entities(cx, _renames(cx, old, new, al), updates, report)
    # Items first, the synced draft last: a crash in between leaves spans that a
    # re-run relocates again (their draft no longer matches), never a false "synced".
    cx.replace_all(list(updates.values()), op="sync", by="script", updated=new_draft)
    reasons = {i: "changed" for i in report.changed}
    reasons.update({i: "lost" for i in report.lost})
    reasons.update({i: "depends" for i in report.dependents})
    queue = [
        {"item": it.id, "reason": reasons.get(it.id, "earlier")}
        for it in sorted(cx.items.values(), key=lambda x: x.id)
        if it.status == "needs_reread"
    ]
    _write_atomic(
        cx.root / "reread.jsonl",
        "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in queue),
    )
    cx.set_meta(synced_draft=new_draft, last_sync=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    report.changed.sort()
    report.lost.sort()
    report.dependents.sort()
    return report
