"""The Codex as read-only SQL: the query surface the LLM and every tool use.

``View`` builds an in-memory SQLite database (Python's standard ``sqlite3``)
from the Codex and the synced draft. Nothing is written to disk: the Codex
files stay the only storage, and the view is rebuilt on each load. The table
layout below is the contract (``SCHEMA_VERSION``); callers write SQL against it.

Computed tables (tokens, n-grams, mentions, co-presence) are built only when a
query names them. The connection refuses writes, attachments and pragmas, and
stops any query that runs longer than ``TIMEOUT`` seconds.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
import tomllib
from collections.abc import Iterable, Sequence
from itertools import combinations
from pathlib import Path
from typing import Any

from litcritic import query, workspace
from litcritic import spans as spanlib
from litcritic.codex import Codex
from litcritic.textstats import WORD, strip_accents

SCHEMA_VERSION = 1
TIMEOUT = 2.0
NGRAM_MAX = 4
TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*|\d+|[^\w\s]")

BASE = """
CREATE TABLE works(id TEXT, title TEXT, author TEXT, kind TEXT, series TEXT,
                   language TEXT, draft TEXT);
CREATE TABLE paragraphs(idx INTEGER PRIMARY KEY, anchor TEXT UNIQUE, part INTEGER,
                        chapter TEXT, scene TEXT, words INTEGER, text TEXT);
CREATE TABLE chapters(id TEXT PRIMARY KEY, idx INTEGER, title TEXT, words INTEGER,
                      first_idx INTEGER, last_idx INTEGER);
CREATE TABLE scenes(id TEXT PRIMARY KEY, chapter TEXT, idx INTEGER, words INTEGER,
                    first_idx INTEGER, last_idx INTEGER);
CREATE TABLE items(id TEXT PRIMARY KEY, type TEXT, status TEXT, text TEXT, by TEXT,
                   rev INTEGER, fields_json TEXT);
CREATE TABLE spans(item_id TEXT, k INTEGER, start_idx INTEGER, start_off INTEGER,
                   end_idx INTEGER, end_off INTEGER, words INTEGER, state TEXT);
CREATE TABLE links(src TEXT, rel TEXT, dst TEXT);
CREATE INDEX spans_item ON spans(item_id);
CREATE INDEX spans_start ON spans(start_idx);
CREATE INDEX links_src ON links(src);
CREATE INDEX links_dst ON links(dst);
"""

COMPUTED = {
    "tokens": "CREATE TABLE tokens(para_idx INTEGER, pos INTEGER, form TEXT, norm TEXT,"
    " is_word INTEGER); CREATE INDEX tokens_norm ON tokens(norm);",
    "ngrams": "CREATE TABLE ngrams(n INTEGER, norm TEXT, para_idx INTEGER, pos INTEGER);"
    " CREATE INDEX ngrams_norm ON ngrams(norm);",
    "mentions": "CREATE TABLE mentions(entity_id TEXT, para_idx INTEGER, off INTEGER,"
    " form TEXT); CREATE INDEX mentions_entity ON mentions(entity_id);",
    "copresence": "CREATE TABLE copresence(a TEXT, b TEXT, scene TEXT, chapter TEXT);",
}
DOCS = {
    "tokens": "computed: every word, number and punctuation mark; norm = lower case, no accents",
    "ngrams": f"computed: word sequences of 2..{NGRAM_MAX} inside a paragraph (norm forms)",
    "mentions": "computed: where each entity's name or alias appears",
    "copresence": "computed: pairs of entities mentioned in the same scene (a < b)",
}


class ViewError(Exception):
    """A query cannot run."""


def norm(word: str) -> str:
    return strip_accents(word).casefold()


class View:
    def __init__(self, work_root: Path, cx: Codex | None = None) -> None:
        self.root = work_root
        self.cx = cx or Codex(work_root)
        ix = query.load(work_root, self.cx.draft)
        self.text = spanlib.Text(ix.paragraphs, ix.anchors, self.cx.draft)
        self.structure = json.loads(
            (work_root / "index" / self.cx.draft / "structure.json").read_text(encoding="utf-8")
        )
        self.conn = sqlite3.connect(":memory:")
        self.built: set[str] = set()
        self._writable = True
        self.conn.set_authorizer(self._authorize)
        self.conn.executescript(BASE)
        self._fill_base()
        self._views()
        self._writable = False

    # -- guards ----------------------------------------------------------------

    def _authorize(self, action: int, *args: Any) -> int:
        if self._writable:
            return sqlite3.SQLITE_OK
        allowed = (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION)
        if action in allowed:
            return sqlite3.SQLITE_OK
        recursive = getattr(sqlite3, "SQLITE_RECURSIVE", 33)
        return sqlite3.SQLITE_OK if action == recursive else sqlite3.SQLITE_DENY

    # -- building --------------------------------------------------------------

    def _fill_base(self) -> None:
        c, meta = self.conn, self._work_meta()
        c.execute(
            "INSERT INTO works VALUES (?,?,?,?,?,?,?)",
            (
                meta.get("id") or meta.get("slug") or self.root.name,
                meta.get("title", ""),
                meta.get("author", ""),
                meta.get("kind", "novel"),
                meta.get("series", ""),
                meta.get("language", ""),
                self.cx.draft,
            ),
        )
        anchors = self.text.anchors
        rows = []
        for i, (a, p) in enumerate(zip(anchors, self.text.paragraphs, strict=True)):
            part = re.match(r"p(\d+)\.", a)
            rows.append(
                (
                    i,
                    a,
                    int(part.group(1)) if part else 0,
                    query.chapter_key(a),
                    a.rsplit(".p", 1)[0],
                    len(WORD.findall(p)),
                    p,
                )
            )
        c.executemany("INSERT INTO paragraphs VALUES (?,?,?,?,?,?,?)", rows)
        for k, ch in enumerate(self.structure["chapters"]):
            cid = query.chapter_key(ch["id"])
            c.execute(
                "INSERT INTO chapters VALUES (?,?,?,?,?,?)",
                (cid, k, ch["title"], ch["words"], ch["start"], ch["end"]),
            )
            for n, sc in enumerate(ch["scenes"]):
                c.execute(
                    "INSERT INTO scenes VALUES (?,?,?,?,?,?)",
                    (sc["id"], cid, n, sc["words"], sc["start"], sc["end"]),
                )
        items, span_rows, link_rows = [], [], []
        for it in self.cx.items.values():
            items.append(
                (
                    it.id,
                    it.type,
                    it.status,
                    it.text,
                    it.by,
                    it.rev,
                    json.dumps(it.fields, ensure_ascii=False),
                )
            )
            for k, s in enumerate(it.spans):
                span_rows.append((it.id, k, *self._span_row(s)))
            link_rows += [(it.id, x["rel"], x["to"]) for x in it.links]
        c.executemany("INSERT INTO items VALUES (?,?,?,?,?,?,?)", items)
        c.executemany("INSERT INTO spans VALUES (?,?,?,?,?,?,?,?)", span_rows)
        c.executemany("INSERT INTO links VALUES (?,?,?)", link_rows)

    def _work_meta(self) -> dict[str, Any]:
        for name in ("work.toml", workspace.MANIFEST):
            f = self.root / name
            if f.is_file():
                return tomllib.loads(f.read_text(encoding="utf-8"))
        return {}

    def _span_row(self, s: spanlib.Span) -> tuple[Any, ...]:
        t = self.text
        i0, i1 = t.index.get(s.start.para), t.index.get(s.end.para)
        if s.draft != t.draft or i0 is None or i1 is None:
            return (None, None, None, None, 0, s.state)
        g0, g1 = t.starts[i0] + s.start.off, t.starts[i1] + s.end.off
        return (i0, s.start.off, i1, s.end.off, len(WORD.findall(t.joined[g0:g1])), s.state)

    def _views(self) -> None:
        for name, t in self.cx.types.items():
            cols = ", ".join(f"json_extract(i.fields_json, '$.{c}') AS \"{c}\"" for c in t.columns)
            self.conn.execute(
                f'CREATE VIEW "v_{name}" AS SELECT i.id, i.status, i.text,'
                f" {cols + ',' if cols else ''}"
                " (SELECT start_idx FROM spans s WHERE s.item_id = i.id AND s.k = 0) AS para_idx,"
                " (SELECT COALESCE(SUM(words), 0) FROM spans s WHERE s.item_id = i.id) AS words"
                f" FROM items i WHERE i.type = '{name}'"
            )

    def _need(self, sql: str) -> None:
        for name in COMPUTED:
            if name not in self.built and re.search(rf"\b{name}\b", sql, re.I):
                self._build(name)

    def _build(self, name: str) -> None:
        was, self._writable = self._writable, True
        try:
            if name == "ngrams":
                self._need("tokens")
            if name == "copresence":
                self._need("mentions")
            self.conn.executescript(COMPUTED[name])
            getattr(self, f"_build_{name}")()
            self.built.add(name)
        finally:
            self._writable = was

    def _build_tokens(self) -> None:
        rows = []
        for i, p in enumerate(self.text.paragraphs):
            for pos, m in enumerate(TOKEN.finditer(p)):
                w = m.group()
                rows.append((i, pos, w, norm(w), 1 if WORD.fullmatch(w) else 0))
        self.conn.executemany("INSERT INTO tokens VALUES (?,?,?,?,?)", rows)

    def _build_ngrams(self) -> None:
        rows = []
        cur = self.conn.execute(
            "SELECT para_idx, norm FROM tokens WHERE is_word = 1 ORDER BY rowid"
        )
        by_para: dict[int, list[str]] = {}
        for i, w in cur:
            by_para.setdefault(i, []).append(w)
        for i, words in by_para.items():
            for n in range(2, NGRAM_MAX + 1):
                for pos in range(len(words) - n + 1):
                    rows.append((n, " ".join(words[pos : pos + n]), i, pos))
        self.conn.executemany("INSERT INTO ngrams VALUES (?,?,?,?)", rows)

    def _build_mentions(self) -> None:
        rows = []
        for ent in self.cx.of_type("entity"):
            if ent.status == "retired":
                continue
            names = [ent.fields.get("name", ""), *ent.fields.get("aliases", [])]
            names = sorted({n for n in names if n}, key=len, reverse=True)
            if not names:
                continue
            flags = 0 if ent.fields.get("exact_case") else re.I
            rx = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, names)) + r")(?!\w)", flags)
            for i, p in enumerate(self.text.paragraphs):
                rows += [(ent.id, i, m.start(), m.group()) for m in rx.finditer(p)]
        self.conn.executemany("INSERT INTO mentions VALUES (?,?,?,?)", rows)

    def _build_copresence(self) -> None:
        by_scene: dict[tuple[str, str], set[str]] = {}
        cur = self.conn.execute(
            "SELECT DISTINCT m.entity_id, p.scene, p.chapter FROM mentions m"
            " JOIN paragraphs p ON p.idx = m.para_idx"
        )
        for ent, scene, chapter in cur:
            by_scene.setdefault((scene, chapter), set()).add(ent)
        rows = [
            (a, b, scene, chapter)
            for (scene, chapter), ents in by_scene.items()
            for a, b in combinations(sorted(ents), 2)
        ]
        self.conn.executemany("INSERT INTO copresence VALUES (?,?,?,?)", rows)

    # -- querying --------------------------------------------------------------

    def run(
        self, sql: str, params: dict[str, Any] | Sequence[Any] = ()
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        """Columns and rows of one read-only query."""
        self._need(sql)
        deadline = time.monotonic() + TIMEOUT
        self.conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
        try:
            cur = self.conn.execute(sql, params)
            rows = cur.fetchall()
        except sqlite3.DatabaseError as exc:
            if time.monotonic() > deadline:
                raise ViewError(f"query stopped after {TIMEOUT:g} s; narrow it") from exc
            raise ViewError(str(exc)) from exc
        finally:
            self.conn.set_progress_handler(None, 0)
        cols = [d[0] for d in cur.description or []]
        return cols, rows

    def schema(self) -> str:
        """The documented tables and views, for the LLM writing a query."""
        lines = [f"codex_schema = {SCHEMA_VERSION}  (read-only SQLite; json_extract available)"]
        self._writable = True  # PRAGMA table_info is refused to queries
        try:
            lines += self._describe()
        finally:
            self._writable = False
        for name, sql in COMPUTED.items():
            cols = re.search(r"\((.*?)\);", sql)
            names = [c.split()[0] for c in cols.group(1).split(",")] if cols else []
            lines.append(f"{name}({', '.join(names)})  -- {DOCS[name]}")
        return "\n".join(lines)

    def _describe(self) -> list[str]:
        lines = []
        for (name,) in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            " AND name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ):
            if name in COMPUTED:
                continue
            cols = [r[1] for r in self.conn.execute(f'PRAGMA table_info("{name}")')]
            lines.append(f"{name}({', '.join(cols)})")
        return lines


def table(cols: list[str], rows: Iterable[tuple[Any, ...]], budget: int) -> str:
    """Rows as ``a | b | c`` lines, cut to the token budget with a footer."""
    out = query.Out(budget)
    out.add(" | ".join(cols))
    rows = list(rows)
    shown = 0
    for r in rows:
        if not out.add(" | ".join("" if v is None else str(v) for v in r)):
            break
        shown += 1
    rest = len(rows) - shown
    return out.finish(f"… {rest} more rows; add LIMIT or narrow the query" if rest else "")
