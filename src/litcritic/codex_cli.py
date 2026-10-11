"""`lc codex …` commands: write, read and check a work's Codex."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from litcritic import query, questions, structure, sync, view, workspace
from litcritic import spans as spanlib
from litcritic.codex import Codex, CodexError, Item
from litcritic.view import ViewError


def _text(ws_root: Path, draft: str) -> spanlib.Text:
    ix = query.load(ws_root, draft, codex=False)
    return spanlib.Text(ix.paragraphs, ix.anchors, draft)


def _spans(args: argparse.Namespace, cx: Codex, root: Path) -> list[spanlib.Span]:
    out = []
    if args.span or args.quote or args.unit:
        text = _text(root, cx.draft)
        for unit in args.unit or []:
            if re.search(r"\.p\d+$", unit):
                raise CodexError(f"--unit {unit!r}: name a chapter or scene, not a paragraph")
            try:
                r = query.paragraph_range(query.Index(text.paragraphs, text.anchors, [], []), unit)
                last = r[-1]
                end = (text.anchors[last], len(text.paragraphs[last]))
                out.append(spanlib.make(text, cx.draft, text.anchors[r[0]], 0, *end))
            except (KeyError, spanlib.SpanError) as exc:
                raise CodexError(f"--unit {unit!r}: not a chapter or scene with text") from exc
        for raw in args.span or []:
            try:
                a, b = raw.split("-", 1)
                pa, oa = a.rsplit(":", 1)
                pb, ob = b.rsplit(":", 1)
            except ValueError:
                raise CodexError(f"--span {raw!r}: use ANCHOR:OFF-ANCHOR:OFF") from None
            out.append(spanlib.make(text, cx.draft, pa, int(oa), pb, int(ob)))
        for q in args.quote or []:
            out.append(spanlib.from_quote(text, cx.draft, q, args.within or ""))
    return out


def _value(raw: str) -> int | float | str:
    """A --param value: numbers bind as numbers, everything else as text."""
    for kind in (int, float):
        try:
            return kind(raw)
        except ValueError:
            pass
    return raw


def _params(raw: list[str] | None) -> dict[str, int | float | str]:
    out = {}
    for entry in raw or []:
        name, sep, value = entry.partition("=")
        if not sep or not name:
            raise CodexError(f"--param {entry!r}: use NAME=VALUE")
        out[name] = _value(value)
    return out


def coverage(root: Path | None = None) -> tuple[list[str], list[str]]:
    """(measurable check ids, problems) across every kind's checklist (or one ``root``).

    A measurable check must name a known question that runs without parameters
    (every parameter has a default), so checks can run unattended.
    """
    from litcritic import checklist, kinds

    qs = questions.load()
    roots = [root] if root else sorted({kinds.get(k).CHECKLIST for k in kinds.available()})
    measurable, problems = [], []
    for r in roots:
        cat = checklist.load(r)
        problems += [
            f"{r.name}: {e}" for e in cat.errors if "measurable" in e or "codex_question" in e
        ]
        for c in cat.checks:
            if c.raw.get("measurable") is not True:
                continue
            measurable.append(c.id)
            q = c.raw.get("codex_question")
            if not isinstance(q, str) or q not in qs:
                problems.append(f"{c.id}: codex_question {q!r} is not a named question")
            elif set(qs[q].params) - set(qs[q].defaults):
                problems.append(f"{c.id}: {q} needs parameters without defaults")
    return measurable, problems


def _list_questions(show_coverage: bool = False) -> int:
    try:
        qs = questions.load()
        measurable, problems = coverage() if show_coverage else ([], [])
    except questions.QuestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for q in qs.values():
        params = ", ".join(f"{k}={q.defaults[k]}" if k in q.defaults else k for k in q.params)
        print(f"{q.id} [{q.family}] {q.title}" + (f"  ({params})" if params else ""))
    if show_coverage:
        for p in problems:
            print(f"problem: {p}")
        ok = len(measurable) - len(problems)
        print(f"coverage: {ok}/{len(measurable)} measurable checks have a named question")
        return 1 if problems else 0
    return 0


def _links(raw: list[str] | None) -> list[dict[str, str]]:
    out = []
    for entry in raw or []:
        rel, _, to = entry.partition(":")
        if not to:
            raise CodexError(f"--link {entry!r}: use REL:ITEM_ID")
        out.append({"rel": rel, "to": to})
    return out


def _fields(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise CodexError("--fields must be a JSON object")
    return data


def _line(item: Item) -> str:
    where = ""
    if item.spans:
        s = item.spans[0]
        where = f" @{s.start.para}" + ("" if s.state == "ok" else f" [{s.state}]")
        if len(item.spans) > 1:
            where += f" +{len(item.spans) - 1}"
    flag = "" if item.status == "active" else f" ({item.status})"
    return f"{item.id} {item.type}{flag}{where}: {item.text}"


def _run(args: argparse.Namespace) -> int:
    if args.codex_cmd == "questions":
        return _list_questions(args.coverage)
    try:
        ws = workspace.resolve(args.workspace, args.home)
        if args.codex_cmd == "init":
            cx = Codex.init(ws.root, args.version or structure.latest_version(ws.root))
            print(f"Codex ready at {cx.root} (draft {cx.draft})")
            return 0
        cx = Codex(ws.root)
        if args.codex_cmd == "add":
            item = cx.add(
                args.type,
                args.text,
                _fields(args.fields),
                _spans(args, cx, ws.root),
                _links(args.link),
                by=args.by,
            )
            print(item.id)
        elif args.codex_cmd == "update":
            changes: dict[str, Any] = {}
            if args.text is not None:
                changes["text"] = args.text
            if args.fields is not None:
                changes["fields"] = {**cx.get(args.id).fields, **_fields(args.fields)}
            new_spans = _spans(args, cx, ws.root)
            if new_spans:
                changes["spans"] = new_spans
                if cx.get(args.id).status == "needs_reread":
                    changes["status"] = "active"
            if args.link:
                changes["links"] = cx.get(args.id).links + _links(args.link)
            print(cx.update(args.id, by=args.by, **changes).id)
        elif args.codex_cmd == "retire":
            print(cx.retire(args.id, by=args.by).id)
        elif args.codex_cmd == "show":
            out = query.Out(args.budget)
            item = cx.get(args.id)
            if args.json:
                print(json.dumps(item.as_json(), ensure_ascii=False, indent=1))
                return 0
            out.add(_line(item))
            if item.fields:
                out.add("fields: " + json.dumps(item.fields, ensure_ascii=False))
            for s in item.spans:
                last = s.end.off > 0 and s.end.para != s.start.para  # end is exclusive
                where = s.start.para + (f"-{s.end.para}" if last else "")
                words = " ".join((s.exact or f"{s.head} … {s.tail}").split())
                cut = words if len(words) <= 80 else words[:77] + "..."
                out.add(f'at {where} [{s.state}, {s.draft}]: "{cut}"')
            incoming = cx.linked_to(item.id)
            if not item.links and not incoming:
                out.add("links: none")
            for link in item.links:
                target = cx.items.get(link["to"])
                label = _line(target) if target else f"{link['to']} (missing)"
                out.add(f"-> {link['rel']} {label}")
            for src, rel in incoming:
                out.add(f"<- {rel} {_line(src)}")
            print(out.finish(), end="")
        elif args.codex_cmd == "find":
            out = query.Out(args.budget)
            hits = [i for i in cx.find(args.words) if not args.type or i.type == args.type]
            out.add(f"{len(hits)} items")
            shown = 0
            for item in hits:
                if not out.add(_line(item)):
                    break
                shown += 1
            rest = len(hits) - shown
            print(out.finish(f"… {rest} more; add words or --type" if rest else ""), end="")
        elif args.codex_cmd == "sql":
            v = view.View(ws.root, cx)
            if args.schema:
                print(v.schema())
                return 0
            if not args.query:
                raise CodexError("give a query, or --schema to see the tables")
            params = _params(args.param)
            cap = view.max_rows(args.budget)
            cols, rows = v.run(args.query, params, max_rows=cap)
            more = len(rows) > cap
            rows = rows[:cap]
            if args.json:
                cells = [[view.cell(x) for x in r] for r in rows]
                payload: dict[str, Any] = {"columns": cols, "rows": cells}
                while cells and query.estimate_tokens(json.dumps(payload)) > args.budget:
                    cells = cells[: len(cells) // 2]
                    payload["rows"] = cells
                    more = True
                payload["more"] = more
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(view.table(cols, rows, args.budget, more), end="")
        elif args.codex_cmd == "ask":
            qs = questions.load()
            if args.question not in qs:
                raise CodexError(f"unknown question {args.question!r}; see `lc codex questions`")
            q = qs[args.question]
            given = _params(args.param)
            questions.bind(q, given)  # fail fast, before the view is built
            v = view.View(ws.root, cx)
            cap = view.max_rows(args.budget)
            cols, rows = questions.ask(v, q, given, max_rows=cap)
            print(f"{q.title}")
            print(view.table(cols, rows[:cap], args.budget, len(rows) > cap), end="")
        elif args.codex_cmd == "sync":
            report = sync.sync(ws.root, args.version, cx)
            print("\n".join(report.lines()))
        elif args.codex_cmd == "check":
            problems = cx.check()
            for p in problems:
                print(p)
            print("ok" if not problems else f"{len(problems)} problem(s)")
            return 1 if problems else 0
        return 0
    except (
        CodexError,
        spanlib.SpanError,
        workspace.WorkspaceError,
        ViewError,
        questions.QuestionError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def register(sub: Any) -> None:
    p = sub.add_parser("codex", help="the work's knowledge base: items on text spans")
    csub = p.add_subparsers(dest="codex_cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--workspace", required=True, help="workspace folder or slug")
        sp.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
        sp.set_defaults(func=_run)

    def writing(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--fields", default=None, help="typed fields as a JSON object")
        sp.add_argument("--span", action="append", help="ANCHOR:OFF-ANCHOR:OFF (repeatable)")
        sp.add_argument("--quote", action="append", help="exact text, found once (repeatable)")
        sp.add_argument("--within", default=None, help="limit --quote to a chapter or scene")
        sp.add_argument("--unit", action="append", help="a whole chapter or scene (repeatable)")
        sp.add_argument("--link", action="append", help="REL:ITEM_ID (repeatable)")
        sp.add_argument("--by", choices=("llm", "writer", "script"), default="llm")

    p_init = csub.add_parser("init", help="create the Codex for a work")
    p_init.add_argument("--version", default=None, help="draft to start from (default latest)")
    common(p_init)
    p_add = csub.add_parser("add", help="add an item")
    p_add.add_argument("type")
    p_add.add_argument("--text", required=True, help="one line saying what the item is")
    writing(p_add)
    common(p_add)
    p_upd = csub.add_parser("update", help="change an item's text, fields, spans or links")
    p_upd.add_argument("id")
    p_upd.add_argument("--text", default=None)
    writing(p_upd)
    common(p_upd)
    p_ret = csub.add_parser("retire", help="retire an item (never deleted)")
    p_ret.add_argument("id")
    p_ret.add_argument("--by", choices=("llm", "writer", "script"), default="llm")
    common(p_ret)
    p_show = csub.add_parser("show", help="an item with its links both ways")
    p_show.add_argument("id")
    p_show.add_argument("--json", action="store_true")
    p_show.add_argument("--budget", type=int, default=query.DEFAULT_BUDGET)
    common(p_show)
    p_find = csub.add_parser("find", help="items whose text or fields contain all words")
    p_find.add_argument("words")
    p_find.add_argument("--type", default=None)
    p_find.add_argument("--budget", type=int, default=query.DEFAULT_BUDGET)
    common(p_find)
    p_sql = csub.add_parser("sql", help="run one read-only SQL query against the Codex")
    p_sql.add_argument("query", nargs="?", default=None)
    p_sql.add_argument("--param", action="append", help="NAME=VALUE for :NAME in the query")
    p_sql.add_argument("--schema", action="store_true", help="print the tables and views")
    p_sql.add_argument("--json", action="store_true")
    p_sql.add_argument("--budget", type=int, default=query.DEFAULT_BUDGET)
    common(p_sql)
    p_ask = csub.add_parser("ask", help="run a named question (see `lc codex questions`)")
    p_ask.add_argument("question")
    p_ask.add_argument("--param", action="append", help="NAME=VALUE")
    p_ask.add_argument("--budget", type=int, default=query.DEFAULT_BUDGET)
    common(p_ask)
    p_qs = csub.add_parser("questions", help="list the named questions")
    p_qs.add_argument("--coverage", action="store_true", help="check measurable checklist checks")
    p_qs.set_defaults(func=_run)
    p_sync = csub.add_parser("sync", help="bring the Codex up to the latest (or given) draft")
    p_sync.add_argument("--version", default=None, help="draft to sync to (default latest)")
    common(p_sync)
    p_chk = csub.add_parser("check", help="dead links, orphans, stale spans, bad items")
    common(p_chk)
