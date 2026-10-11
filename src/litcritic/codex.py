"""The Codex: one work's knowledge, as typed items on text spans.

Every item shares one envelope (id, type, text, spans, links, status, fields,
by, rev, created, updated); its ``fields`` follow its type, defined as data in
``codex_types/<type>.toml``. Items live in ``<work>/codex/items/<type>.jsonl``,
one per line, sorted by id; each change is appended to ``codex/changes.jsonl``.

This module is the only reader and writer of those files. Callers ask it, and
the SQL view is built from it, so the files can change without them noticing.
Nothing that can be recomputed from the text or from other items is stored.
"""

from __future__ import annotations

import json
import os
import secrets
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from litcritic import spans as spanlib
from litcritic import validate

SCHEMA_VERSION = 1
DIR = "codex"
STATUSES = ("active", "needs_reread", "retired")
BY = ("llm", "writer", "script")
TYPES_DIR = Path(__file__).parent / "codex_types"


class CodexError(Exception):
    """The Codex cannot do what was asked."""


@dataclass(frozen=True)
class ItemType:
    name: str
    prefix: str
    links: tuple[str, ...]
    columns: tuple[str, ...]
    schema: dict[str, Any]
    spans_required: bool
    standalone: bool  # may exist with no spans and no links (an entity, a thread)


def load_types(*dirs: Path) -> dict[str, ItemType]:
    """Item types from ``codex_types/`` plus any extra folders (a kind's types)."""
    out: dict[str, ItemType] = {}
    for d in (TYPES_DIR, *dirs):
        for f in sorted(d.glob("*.toml")):
            raw = tomllib.loads(f.read_text(encoding="utf-8"))
            t = ItemType(
                name=raw["type"],
                prefix=raw["prefix"],
                links=tuple(raw.get("links", [])),
                columns=tuple(raw.get("columns", [])),
                schema=raw.get("schema", {"type": "object"}),
                spans_required=bool(raw.get("spans_required", False)),
                standalone=bool(raw.get("standalone", False)),
            )
            if t.name in out:
                raise CodexError(f"item type {t.name!r} defined twice ({f})")
            if any(o.prefix == t.prefix for o in out.values()):
                raise CodexError(f"item type prefix {t.prefix!r} used twice ({f})")
            out[t.name] = t
    return out


@dataclass
class Item:
    id: str
    type: str
    text: str
    spans: list[spanlib.Span] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)
    status: str = "active"
    fields: dict[str, Any] = field(default_factory=dict)
    by: str = "llm"
    rev: int = 1
    created: str = ""
    updated: str = ""

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "text": self.text,
            "spans": [s.as_json() for s in self.spans],
            "links": self.links,
            "status": self.status,
            "fields": self.fields,
            "by": self.by,
            "rev": self.rev,
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Item:
        return cls(
            id=d["id"],
            type=d["type"],
            text=d.get("text", ""),
            spans=[spanlib.Span.from_json(s) for s in d.get("spans", [])],
            links=[dict(x) for x in d.get("links", [])],
            status=d.get("status", "active"),
            fields=dict(d.get("fields", {})),
            by=d.get("by", "llm"),
            rev=int(d.get("rev", 1)),
            created=d.get("created", ""),
            updated=d.get("updated", ""),
        )


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class Codex:
    """A work's Codex, loaded into memory with indexes by id, type, paragraph and link."""

    def __init__(self, work_root: Path, types: dict[str, ItemType] | None = None) -> None:
        self.root = work_root / DIR
        if not (self.root / "codex.toml").is_file():
            raise CodexError(f"no Codex in {work_root}; run `lc codex init`")
        self.meta = tomllib.loads((self.root / "codex.toml").read_text(encoding="utf-8"))
        self.types = types or load_types()
        self.items: dict[str, Item] = {}
        self.load_errors: list[str] = []
        for f in sorted((self.root / "items").glob("*.jsonl")):
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    item = Item.from_json(json.loads(line))
                except (ValueError, KeyError, spanlib.SpanError) as exc:
                    self.load_errors.append(f"{f.name}:{n}: unreadable item ({exc})")
                    continue
                if item.id in self.items:
                    self.load_errors.append(f"{f.name}:{n}: duplicate id {item.id}")
                    continue
                self.items[item.id] = item
        self._reindex()

    # -- creation and files -------------------------------------------------

    @staticmethod
    def init(work_root: Path, draft: str) -> Codex:
        root = work_root / DIR
        if (root / "codex.toml").exists():
            raise CodexError(f"a Codex already exists in {work_root}")
        (root / "items").mkdir(parents=True, exist_ok=True)
        _write_atomic(
            root / "codex.toml",
            f'codex_schema = {SCHEMA_VERSION}\nsynced_draft = "{draft}"\n',
        )
        return Codex(work_root)

    @property
    def draft(self) -> str:
        return str(self.meta.get("synced_draft", ""))

    def set_draft(self, draft: str) -> None:
        self.meta["synced_draft"] = draft
        _write_atomic(
            self.root / "codex.toml",
            f"codex_schema = {self.meta.get('codex_schema', SCHEMA_VERSION)}\n"
            f'synced_draft = "{draft}"\n',
        )

    def _save(self, type_name: str) -> None:
        rows = sorted((i for i in self.items.values() if i.type == type_name), key=lambda i: i.id)
        text = "".join(json.dumps(i.as_json(), ensure_ascii=False) + "\n" for i in rows)
        _write_atomic(self.root / "items" / f"{type_name}.jsonl", text)

    def _log(self, op: str, item: Item, before: dict[str, Any] | None, by: str) -> None:
        entry = {
            "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "draft": self.draft,
            "item": item.id,
            "op": op,
            "by": by,
            "after": item.as_json(),
        }
        if before is not None:
            entry["before"] = before
        with (self.root / "changes.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _reindex(self) -> None:
        self.by_type: dict[str, list[str]] = defaultdict(list)
        self.by_para: dict[str, set[str]] = defaultdict(set)
        self.links_in: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for item in self.items.values():
            self.by_type[item.type].append(item.id)
            for s in item.spans:
                self.by_para[s.start.para].add(item.id)
                self.by_para[s.end.para].add(item.id)
            for link in item.links:
                self.links_in[link["to"]].append((item.id, link["rel"]))

    # -- writing --------------------------------------------------------------

    def errors_for(self, item: Item) -> list[str]:
        t = self.types.get(item.type)
        if t is None:
            return [f"{item.id}: unknown type {item.type!r}"]
        errs = [f"{item.id}.fields{e[1:]}" for e in validate.check(item.fields, t.schema, t.schema)]
        if not item.id.startswith(t.prefix + "-"):
            errs.append(f"{item.id}: id must start with {t.prefix}-")
        if item.status not in STATUSES:
            errs.append(f"{item.id}: status {item.status!r} not one of {STATUSES}")
        if item.by not in BY:
            errs.append(f"{item.id}: by {item.by!r} not one of {BY}")
        if t.spans_required and not item.spans:
            errs.append(f"{item.id}: a {item.type} needs at least one span")
        for link in item.links:
            if link.get("rel") not in t.links:
                errs.append(f"{item.id}: link {link.get('rel')!r} not allowed for {item.type}")
        return errs

    def _new_id(self, prefix: str) -> str:
        while True:
            candidate = f"{prefix}-{secrets.token_hex(4)}"
            if candidate not in self.items:
                return candidate

    def add(
        self,
        type_name: str,
        text: str,
        fields: dict[str, Any] | None = None,
        spans: list[spanlib.Span] | None = None,
        links: list[dict[str, str]] | None = None,
        by: str = "llm",
    ) -> Item:
        t = self.types.get(type_name)
        if t is None:
            raise CodexError(f"unknown item type {type_name!r}; known: {sorted(self.types)}")
        item = Item(
            id=self._new_id(t.prefix),
            type=type_name,
            text=text,
            spans=list(spans or []),
            links=list(links or []),
            fields=dict(fields or {}),
            by=by,
            created=self.draft,
            updated=self.draft,
        )
        self._commit("add", item, None, by)
        return item

    def update(self, item_id: str, by: str = "llm", **changes: Any) -> Item:
        old = self.get(item_id)
        before = old.as_json()
        allowed = {"text", "spans", "links", "status", "fields"}
        unknown = set(changes) - allowed
        if unknown:
            raise CodexError(f"cannot change {sorted(unknown)}; allowed: {sorted(allowed)}")
        item = Item.from_json(before)
        for k, v in changes.items():
            setattr(item, k, v)
        item.rev, item.updated, item.by = old.rev + 1, self.draft, by
        self._commit("update", item, before, by)
        return item

    def retire(self, item_id: str, by: str = "llm") -> Item:
        return self.update(item_id, by=by, status="retired")

    def _commit(self, op: str, item: Item, before: dict[str, Any] | None, by: str) -> None:
        errs = self.errors_for(item)
        errs += [
            f"{item.id}: link to unknown item {link['to']}"
            for link in item.links
            if link["to"] not in self.items and link["to"] != item.id
        ]
        if errs:
            raise CodexError("; ".join(errs))
        self.items[item.id] = item
        self._save(item.type)
        self._log(op, item, before, by)
        self._reindex()

    def replace_all(self, items: list[Item], op: str = "sync", by: str = "script") -> None:
        """Write many changed items at once (sync); each type file is rewritten once."""
        changed_types = set()
        for item in items:
            before = self.items[item.id].as_json() if item.id in self.items else None
            self.items[item.id] = item
            changed_types.add(item.type)
            self._log(op, item, before, by)
        for t in sorted(changed_types):
            self._save(t)
        self._reindex()

    # -- reading --------------------------------------------------------------

    def get(self, item_id: str) -> Item:
        try:
            return self.items[item_id]
        except KeyError:
            raise CodexError(f"no item {item_id!r}") from None

    def of_type(self, type_name: str) -> list[Item]:
        return [self.items[i] for i in sorted(self.by_type.get(type_name, []))]

    def at_paragraph(self, anchor: str) -> list[Item]:
        return [self.items[i] for i in sorted(self.by_para.get(anchor, set()))]

    def linked_to(self, item_id: str) -> list[tuple[Item, str]]:
        return [(self.items[src], rel) for src, rel in self.links_in.get(item_id, [])]

    def find(self, words: str) -> list[Item]:
        terms = words.casefold().split()
        out = []
        for item in self.items.values():
            hay = (item.text + " " + json.dumps(item.fields, ensure_ascii=False)).casefold()
            if all(t in hay for t in terms):
                out.append(item)
        return sorted(out, key=lambda i: i.id)

    # -- checking -------------------------------------------------------------

    def check(self) -> list[str]:
        """Every problem that would let knowledge rot silently (empty when clean)."""
        problems = list(self.load_errors)
        for item in sorted(self.items.values(), key=lambda i: i.id):
            problems += self.errors_for(item)
            for link in item.links:
                target = self.items.get(link["to"])
                if target is None:
                    problems.append(f"{item.id}: dead link {link['rel']} -> {link['to']}")
                elif target.status == "retired" and item.status != "retired":
                    problems.append(f"{item.id}: links to retired {target.id}")
            if item.status == "retired":
                continue
            t = self.types.get(item.type)
            floating = not item.spans and not item.links and not self.links_in.get(item.id)
            if floating and t is not None and not t.standalone:
                problems.append(f"{item.id}: orphan (no spans, no links)")
            for s in item.spans:
                stale = s.draft != self.draft or s.state in ("changed", "lost")
                if stale and item.status != "needs_reread":
                    problems.append(
                        f"{item.id}: stale span ({s.state}, {s.draft}) not marked needs_reread"
                    )
        return problems
