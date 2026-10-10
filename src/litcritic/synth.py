"""Seeded synthetic drafts: paragraph edits with an exact old<->new truth map.

Used to measure draft alignment (T6) without real revisions. Each edit touches
only paragraphs no earlier edit touched, so the truth stays unambiguous.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

KINDS = ("modify", "insert", "delete", "move", "split", "merge")
SENTENCE_END = re.compile(r"(?<=[.!?…»])\s+(?=[«\"¿¡A-ZÁÉÍÓÚÑ-])")
MIN_WORDS = 8


@dataclass
class _Item:
    text: str
    origins: list[int]
    kind: str = "unchanged"


@dataclass
class Draft:
    paragraphs: list[str]
    old: list[dict[str, object]]
    new: list[dict[str, object]]
    ops: list[dict[str, object]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs) + "\n"

    def truth(self) -> dict[str, object]:
        return {
            "old_count": len(self.old),
            "new_count": len(self.new),
            "ops": self.ops,
            "old": self.old,
            "new": self.new,
        }


def paragraphs(text: str) -> list[str]:
    """Blank-line separated blocks, stripped, empty ones dropped."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def generate(text: str, seed: int, rate: float = 0.05) -> Draft:
    """Edit about ``rate`` of the paragraphs, cycling through every edit kind."""
    rng = random.Random(seed)
    source = paragraphs(text)
    items = [_Item(p, [i]) for i, p in enumerate(source)]
    vocab = sorted({w for p in source for w in p.split()})
    budget = max(len(KINDS), round(len(source) * rate))
    ops: list[dict[str, object]] = []
    for n in range(budget):
        kind = KINDS[n % len(KINDS)]
        op = _apply(kind, items, rng, vocab)
        if op:
            ops.append(op)
    return _finish(items, len(source), ops)


def _free(items: list[_Item], words: int = 0) -> list[int]:
    return [
        i for i, it in enumerate(items) if it.kind == "unchanged" and len(it.text.split()) >= words
    ]


def _apply(
    kind: str, items: list[_Item], rng: random.Random, vocab: list[str]
) -> dict[str, object] | None:
    if kind == "insert":
        at = rng.randrange(len(items) + 1)
        words = rng.choices(vocab, k=rng.randint(MIN_WORDS, 3 * MIN_WORDS))
        items.insert(at, _Item(" ".join(words).capitalize() + ".", [], "inserted"))
        return {"kind": kind, "at": at}
    if kind == "merge":
        pairs = [i for i in _free(items) if i + 1 < len(items) and items[i + 1].kind == "unchanged"]
        if not pairs:
            return None
        i = rng.choice(pairs)
        a, b = items[i], items.pop(i + 1)
        items[i] = _Item(f"{a.text} {b.text}", a.origins + b.origins, "merged")
        return {"kind": kind, "old": items[i].origins}
    if kind == "split":
        cands = [i for i in _free(items, MIN_WORDS) if SENTENCE_END.search(items[i].text)]
        if not cands:
            return None
        i = rng.choice(cands)
        cuts = [m.start() for m in SENTENCE_END.finditer(items[i].text)]
        cut = rng.choice(cuts)
        text, origin = items[i].text, items[i].origins
        items[i : i + 1] = [
            _Item(text[:cut].strip(), origin, "split"),
            _Item(text[cut:].strip(), origin, "split"),
        ]
        return {"kind": kind, "old": origin}
    cands = _free(items, MIN_WORDS if kind == "modify" else 0)
    if not cands:
        return None
    i = rng.choice(cands)
    if kind == "delete":
        it = items.pop(i)
        return {"kind": kind, "old": it.origins}
    if kind == "modify":
        items[i] = _Item(_mutate(items[i].text, rng, vocab), items[i].origins, "modified")
        return {"kind": kind, "old": items[i].origins}
    # move: take one paragraph and drop it at least two positions away
    it = items.pop(i)
    targets = [j for j in range(len(items) + 1) if abs(j - i) >= 2]
    if not targets:
        items.insert(i, it)
        return None
    items.insert(rng.choice(targets), _Item(it.text, it.origins, "moved"))
    return {"kind": kind, "old": it.origins}


def _mutate(text: str, rng: random.Random, vocab: list[str]) -> str:
    """Replace, drop or add about 10% of the words (at least one)."""
    words = text.split()
    for _ in range(max(1, len(words) // 10)):
        pos = rng.randrange(len(words))
        action = rng.choice(("replace", "drop", "add"))
        if action == "replace":
            words[pos] = rng.choice(vocab)
        elif action == "drop" and len(words) > MIN_WORDS:
            del words[pos]
        else:
            words.insert(pos, rng.choice(vocab))
    out = " ".join(words)
    return out if out != " ".join(text.split()) else out + " " + rng.choice(vocab)


def _finish(items: list[_Item], old_count: int, ops: list[dict[str, object]]) -> Draft:
    old: list[dict[str, object]] = [{"kind": "deleted", "new": []} for _ in range(old_count)]
    new: list[dict[str, object]] = []
    for j, it in enumerate(items):
        new.append({"kind": it.kind, "old": list(it.origins)})
        for i in it.origins:
            entry = old[i]
            entry["kind"] = it.kind
            targets = entry["new"]
            assert isinstance(targets, list)
            targets.append(j)
    return Draft([it.text for it in items], old, new, ops)
