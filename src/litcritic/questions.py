"""Named questions: saved, tested SQL queries over the Codex view.

Each question is ``questions/<id>.sql`` with a TOML header in its leading
``-- `` comment lines: ``id``, ``title``, ``family``, ``params`` (name ->
description) and optional ``defaults``. Checklist checks point to the question
that measures them (``codex_question``); checks and proactive feedback run
them, and the LLM can read them as examples.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from litcritic.view import View

DIR = Path(__file__).parent / "questions"
PARAM = re.compile(r"(?<!:):([a-z_][a-z0-9_]*)")


class QuestionError(Exception):
    """A question is unknown, malformed or missing a parameter."""


@dataclass(frozen=True)
class Question:
    id: str
    title: str
    family: str
    sql: str
    params: dict[str, str] = field(default_factory=dict)
    defaults: dict[str, Any] = field(default_factory=dict)


def parse(text: str, name: str = "?") -> Question:
    head: list[str] = []
    body: list[str] = []
    for line in text.splitlines():
        if not body and line.startswith("--"):
            head.append(line[2:].strip())
        else:
            body.append(line)
    try:
        meta = tomllib.loads("\n".join(head))
    except tomllib.TOMLDecodeError as exc:
        raise QuestionError(f"{name}: bad header ({exc})") from exc
    sql = "\n".join(body).strip()
    missing = [k for k in ("id", "title", "family") if not meta.get(k)]
    if missing or not sql:
        raise QuestionError(f"{name}: header needs {missing or ['a query']}")
    q = Question(
        id=meta["id"],
        title=meta["title"],
        family=meta["family"],
        sql=sql,
        params=dict(meta.get("params", {})),
        defaults=dict(meta.get("defaults", {})),
    )
    used = set(PARAM.findall(sql))
    if used != set(q.params):
        raise QuestionError(
            f"{name}: query uses {sorted(used)}, header declares {sorted(q.params)}"
        )
    return q


def load(*dirs: Path) -> dict[str, Question]:
    out: dict[str, Question] = {}
    for d in (DIR, *dirs):
        for f in sorted(d.glob("*.sql")):
            q = parse(f.read_text(encoding="utf-8"), f.name)
            if q.id != f.stem or q.id in out:
                raise QuestionError(f"{f.name}: id must match the file name and be unique")
            out[q.id] = q
    return out


def bind(q: Question, given: dict[str, Any]) -> dict[str, Any]:
    unknown = set(given) - set(q.params)
    if unknown:
        raise QuestionError(f"{q.id}: unknown parameter(s) {sorted(unknown)}")
    values = {**q.defaults, **given}
    missing = [p for p in q.params if p not in values]
    if missing:
        hints = "; ".join(f"{p}: {q.params[p]}" for p in missing)
        raise QuestionError(f"{q.id}: needs {hints}")
    return values


def ask(
    v: View, q: Question, given: dict[str, Any], max_rows: int | None = None
) -> tuple[list[str], list[tuple[Any, ...]]]:
    return v.run(q.sql, bind(q, given), max_rows=max_rows)
