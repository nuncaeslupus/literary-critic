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
from collections.abc import Sequence
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
CREATE VIEW para_pos AS
  SELECT idx, SUM(words) OVER (ORDER BY idx) - words AS word0, words FROM paragraphs;
CREATE INDEX spans_item ON spans(item_id);
CREATE INDEX spans_start ON spans(start_idx);
CREATE INDEX links_src ON links(src);
CREATE INDEX links_dst ON links(dst);
"""

# Computed tables: (columns, index column, what it is). Built only when a query names them.
COMPUTED: dict[str, tuple[tuple[str, ...], str, str]] = {
    "tokens": (
        ("para_idx", "pos", "form", "norm", "is_word"),
        "norm",
        "every word, number and punctuation mark; pos counts all tokens in the paragraph;"
        " norm = lower case, no accents",
    ),
    "ngrams": (
        ("n", "norm", "para_idx", "pos"),
        "norm",
        f"word sequences of 2..{NGRAM_MAX} inside a paragraph (norm forms);"
        " pos is the tokens.pos of the first word",
    ),
    "mentions": (
        ("entity_id", "para_idx", "off", "form"),
        "entity_id",
        "where each entity's name or alias appears (off = character offset in the paragraph)",
    ),
    "copresence": (
        ("a", "b", "scene", "chapter"),
        "a",
        "pairs of entities mentioned in the same scene (a < b)",
    ),
}
STRING = re.compile(r"'(?:[^']|'')*'")
TABLE_REF = re.compile(r"\b(?:from|join)\s+\"?(\w+)", re.I)


class ViewError(Exception):
    """A query cannot run."""


def norm(word: str) -> str:
    return strip_accents(word).casefold()


def _phrase_sql(text: Any) -> str | None:
    """SQL ``phrase(x)``: the words of x in norm form, as ngrams.norm stores them."""
    return None if text is None else " ".join(norm(w) for w in WORD.findall(str(text)))


def _norm_sql(text: Any) -> str | None:
    """SQL ``norm(x)``: lower case, no accents, single spaces (as tokens.norm)."""
    return None if text is None else " ".join(norm(str(text)).split())


class View:
    def __init__(self, work_root: Path, cx: Codex | None = None) -> None:
        self.root = work_root
        self.cx = cx or Codex(work_root)
        ix = query.load(work_root, self.cx.draft)
        self.text = spanlib.Text(ix.paragraphs, ix.anchors, self.cx.draft)
        self.structure = json.loads(
            (work_root / "index" / self.cx.draft / "structure.json").read_text(encoding="utf-8")
        )
        # No statement cache: a write prepared while building must never be reused later.
        self.conn = sqlite3.connect(":memory:", cached_statements=0)
        self.built: set[str] = set()
        self._writable = True
        self.conn.set_authorizer(self._authorize)
        self.conn.create_function("norm", 1, _norm_sql, deterministic=True)
        self.conn.create_function("phrase", 1, _phrase_sql, deterministic=True)
        self.conn.executescript(BASE)
        self._fill_base()
        self._views()
        self._seal()

    # -- guards ----------------------------------------------------------------

    def _seal(self) -> None:
        """Back to read-only; setting the authorizer again expires prepared statements."""
        self._writable = False
        self.conn.set_authorizer(self._authorize)

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
        f = self.root / workspace.MANIFEST
        return tomllib.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}

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
        named = {m.lower() for m in TABLE_REF.findall(STRING.sub("''", sql))}
        for name in COMPUTED:
            if name in named and name not in self.built:
                self._build(name)

    def _build(self, name: str) -> None:
        if name == "ngrams" and "tokens" not in self.built:
            self._build("tokens")
        if name == "copresence" and "mentions" not in self.built:
            self._build("mentions")
        cols, key, _ = COMPUTED[name]
        self._writable = True
        try:
            self.conn.execute(f"CREATE TABLE {name}({', '.join(cols)})")
            try:
                getattr(self, f"_build_{name}")()
                self.conn.execute(f"CREATE INDEX {name}_{key} ON {name}({key})")
            except BaseException:
                self.conn.execute(f"DROP TABLE {name}")
                raise
            self.built.add(name)
        finally:
            self._seal()

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
            "SELECT para_idx, pos, norm FROM tokens WHERE is_word = 1 ORDER BY para_idx, pos"
        )
        by_para: dict[int, list[tuple[int, str]]] = {}
        for i, pos, w in cur:
            by_para.setdefault(i, []).append((pos, w))
        for i, words in by_para.items():
            for n in range(2, NGRAM_MAX + 1):
                for k in range(len(words) - n + 1):
                    gram = " ".join(w for _, w in words[k : k + n])
                    rows.append((n, gram, i, words[k][0]))
        self.conn.executemany("INSERT INTO ngrams VALUES (?,?,?,?)", rows)

    def _build_mentions(self) -> None:
        exact: dict[str, list[str]] = {}
        folded: dict[str, list[str]] = {}
        for ent in self.cx.of_type("entity"):
            if ent.status == "retired":
                continue
            forms = {ent.fields.get("name", ""), *ent.fields.get("aliases", [])} - {""}
            for n in forms:
                if ent.fields.get("exact_case"):
                    exact.setdefault(n, []).append(ent.id)
                else:
                    folded.setdefault(n.casefold(), []).append(ent.id)
        patterns: list[tuple[re.Pattern[str], dict[str, list[str]], int]] = []
        for names, flags in ((exact, 0), (folded, re.I)):
            if names:
                alts = "|".join(map(re.escape, sorted(names, key=len, reverse=True)))
                patterns.append((re.compile(rf"(?<!\w)(?:{alts})(?!\w)", flags), names, flags))
        rows = []
        for i, p in enumerate(self.text.paragraphs):
            for rx, names, flags in patterns:
                for m in rx.finditer(p):
                    key = m.group().casefold() if flags else m.group()
                    rows += [(e, i, m.start(), m.group()) for e in names.get(key, [])]
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
        self,
        sql: str,
        params: dict[str, Any] | Sequence[Any] = (),
        max_rows: int | None = None,
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        """Columns and rows of one read-only query (at most ``max_rows`` + 1 rows when set)."""
        self._need(sql)
        deadline = time.monotonic() + TIMEOUT
        self.conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
        try:
            cur = self.conn.execute(sql, params)
            rows = cur.fetchall() if max_rows is None else cur.fetchmany(max_rows + 1)
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
            self._seal()
        for name, (cols, _, doc) in COMPUTED.items():
            lines.append(f"{name}({', '.join(cols)})  -- computed: {doc}")
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


def max_rows(budget: int) -> int:
    """How many rows a budget can show at most (one token per row, at least)."""
    return max(1, budget - query.FOOTER_RESERVE)


def cell(v: Any) -> Any:
    return v.hex() if isinstance(v, bytes) else v


def table(cols: list[str], rows: Sequence[tuple[Any, ...]], budget: int, more: bool) -> str:
    """Rows as ``a | b | c`` lines, cut to the token budget with a footer.

    ``more`` says the query had rows beyond those passed in.
    """
    out = query.Out(budget)
    out.add(" | ".join(cols))
    shown = 0
    for r in rows:
        line = " | ".join("" if v is None else str(cell(v)) for v in r)
        if not out.add(line):
            if shown == 0:
                out.add_cut(line)
                shown = 1
            break
        shown += 1
    if shown < len(rows) or more:
        return out.finish("… more rows; add LIMIT, narrow the query or raise --budget")
    return out.finish()
