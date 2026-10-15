"""Revision rounds: open issues in the Codex become located actions and a letter.

Rounds follow editorial order: structural first, then scene and character,
then prose and dialogue. ``build`` takes the active problem issues of the
earliest level that still has any undecided, scores them (severity x
confidence x the profile's weight / effort) and records the round in
``revisions/round-NN/round.json``. An action's status is the writer's latest
decision on its issue (a ``decision`` item); ``mark`` records one. ``letter``
renders the writer-facing ``letter.md`` in the work's language. The script only
arranges what the issues say; it never writes prose for the work. Quoted wording
that is not in the draft is flagged unless the writer turned prose suggestions fully on
(``minor`` allows only short fixes, so long new passages are still flagged).
"""

from __future__ import annotations

import json
import re
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from litcritic import checklist, kinds, locate, query, settings, structure
from litcritic.codex import Codex, CodexError, Item
from litcritic.workspace import MANIFEST

LEVELS = ("structural", "scene", "line")
SEVERITY = {"high": 3.0, "medium": 2.0, "low": 1.0}
EFFORT = {"S": 1.0, "M": 1.5, "L": 2.0}
QUOTE = re.compile(r"«([^»]+)»|“([^”]+)”|\"([^\"]+)\"")
MAX_QUOTE_WORDS = 12
ISSUE_LEVEL = {
    "book": "structural",
    "part": "structural",
    "chapter": "structural",
    "scene": "scene",
    "paragraph": "line",
    "line": "line",
    "mechanics": "line",
}
VERDICT_STATUS = {
    "accepted": "accepted",
    "rejected": "rejected",
    "done": "done",
    "done_differently": "done",
    "deferred": "deferred",
}
STATUSES = ("pending", "accepted", "rejected", "done", "deferred")
OPEN = ("pending", "accepted", "deferred")  # an action still to address

DEFAULT_OPTIONS = {
    "es": ["Mantenerlo así (si es deliberado, dime por qué)", "Revisarlo como se describe"],
    "en": ["Keep it as it is (if it is deliberate, tell me why)", "Revise it as described"],
}


class RoundError(Exception):
    """A round cannot be built, marked or rendered."""


def load_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def round_dirs(ws_root: Path) -> list[Path]:
    base = ws_root / "revisions"
    return sorted(p for p in base.glob("round-[0-9][0-9]") if p.is_dir()) if base.is_dir() else []


def load_profile(ws_root: Path) -> dict[str, Any]:
    f = ws_root / "analysis" / "profile.toml"
    return tomllib.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}


def language(ws_root: Path) -> str:
    """The work's language: the profile's, else the work manifest's, else English."""
    profile = load_profile(ws_root)
    if profile.get("language"):
        return str(profile["language"])
    manifest = ws_root / MANIFEST
    if manifest.is_file():
        return str(tomllib.loads(manifest.read_text(encoding="utf-8")).get("language", "en"))
    return "en"


def prose_flags(action: dict[str, Any], draft_text: str) -> list[str]:
    """Quoted passages in an action that are long and not copied from the draft."""
    flags = []
    fields = [action.get("what", ""), action.get("why", ""), *action.get("options", [])]
    for text in fields:
        for m in QUOTE.finditer(str(text)):
            quoted = next(g for g in m.groups() if g)
            if len(quoted.split()) > MAX_QUOTE_WORDS and quoted not in draft_text:
                flags.append(
                    f"{action.get('id')}: quoted text not in the manuscript: {quoted[:40]}…"
                )
    return flags


# --- issues and decisions ----------------------------------------------------------


def decision(cx: Codex, issue_id: str) -> Item | None:
    """The writer's latest active decision on an issue."""
    found = [
        src
        for src, rel in cx.linked_to(issue_id)
        if rel == "about" and src.type == "decision" and src.status != "retired"
    ]
    return max(found, key=lambda d: (str(d.fields.get("at", "")), d.rev, d.id)) if found else None


def action_status(cx: Codex, issue_id: str) -> str:
    d = decision(cx, issue_id)
    return VERDICT_STATUS.get(str(d.fields.get("verdict")), "pending") if d else "pending"


def level_of(issue: Item, checks: dict[str, checklist.Check]) -> str | None:
    """The round level of an issue; None for checks that produce no action."""
    check = checks.get(str(issue.fields.get("check", "")))
    if check is not None:
        return check.action_level if check.action_level in LEVELS else None
    return ISSUE_LEVEL.get(str(issue.fields.get("level")), "scene")


def _area_of(issue: Item, checks: dict[str, checklist.Check]) -> str | None:
    check = checks.get(str(issue.fields.get("check", "")))
    return check.area if check is not None else None


def score(issue: Item, weights: dict[str, float], check: checklist.Check | None) -> float:
    weight = 1.0
    if check is not None:
        weight = float(weights.get(check.id, weights.get(check.area, 1.0)))
    f = issue.fields
    return (
        SEVERITY.get(str(f.get("severity")), 1.0)
        * float(f.get("confidence", 1.0))
        * weight
        / EFFORT.get(str(f.get("effort", "M")), 1.5)
    )


def _anchor(issue: Item) -> str | None:
    return issue.spans[0].start.para if issue.spans else None


def located(cx: Codex, issue: Item, loc: locate.Locations) -> locate.Locator | None:
    """Where an issue is, for the writer; None when it has no place in the synced draft."""
    a = _anchor(issue)
    if a is None or issue.spans[0].draft != cx.draft:
        return None
    try:
        return loc.locate(a)
    except KeyError:
        return None


def _locator(ws_root: Path, cx: Codex, lang: str) -> tuple[query.Index, locate.Locations]:
    ix = query.load(ws_root, cx.draft)
    return ix, locate.Locations.of_workspace(ws_root, cx.draft, ix, lang)


def _round_meta(d: Path) -> dict[str, Any]:
    return dict(load_json(d / "round.json", {}))


def round_actions(
    ws_root: Path,
    d: Path,
    cx: Codex | None = None,
    loc: locate.Locations | None = None,
) -> list[dict[str, Any]]:
    """A round's actions with their issue's current text, place and status.

    A retired issue's action reads ``withdrawn``; one whose passage changed has
    no place until it is re-read.
    """
    cx = cx or Codex(ws_root)
    meta = _round_meta(d)
    lang = str(meta.get("language") or language(ws_root))
    if loc is None:
        _, loc = _locator(ws_root, cx, lang)
    out = []
    for entry in meta.get("actions", []):
        try:
            issue = cx.get(entry["issue"])
        except CodexError:
            continue
        where = located(cx, issue, loc) if issue.status == "active" else None
        f = issue.fields
        out.append(
            {
                "id": entry["id"],
                "issue": issue.id,
                "level": meta.get("level"),
                "round": meta.get("round"),
                "what": issue.text,
                "why": str(f.get("why") or ""),
                "where": where.as_where() if where else None,
                "options": list(
                    f.get("options") or DEFAULT_OPTIONS.get(lang, DEFAULT_OPTIONS["en"])
                ),
                "severity": f.get("severity"),
                "status": "withdrawn" if issue.status == "retired" else action_status(cx, issue.id),
            }
        )
    return out


# --- rounds -------------------------------------------------------------------------


def build(
    ws_root: Path,
    version: str | None = None,
    level: str | None = None,
    area: str | None = None,
    issues: list[str] | None = None,
) -> tuple[Path, list[dict[str, Any]], list[str]]:
    """Record the next round; returns (round.json path, actions, warnings).

    A latest round with no letter and no decision on any of its issues has not been
    put to the writer yet, so it is rebuilt in place (same number) rather than
    followed. Once its letter exists, its numbering is fixed.
    ``version`` is accepted for the CLI and must be the Codex's synced draft.
    ``area`` keeps only issues of checks in that checklist area, and ``issues`` only
    those ids; both narrow the open problems before the level is chosen.
    """
    cx = Codex(ws_root)
    if version and version != cx.draft:
        raise RoundError(f"the Codex is synced to {cx.draft}; run `lc codex sync` first")
    cat = checklist.load(kinds.of_work(ws_root).CHECKLIST)
    checks = {c.id: c for c in cat.checks}
    weights = {str(k): float(v) for k, v in load_profile(ws_root).get("weights", {}).items()}
    lang = language(ws_root)
    dirs = round_dirs(ws_root)
    reuse = None
    if dirs:
        last = _round_meta(dirs[-1]).get("actions") or []
        sent = (dirs[-1] / "letter.md").exists()
        if last and not sent and all(decision(cx, a["issue"]) is None for a in last):
            reuse = dirs[-1]
    in_rounds = {a["issue"] for d in dirs if d != reuse for a in _round_meta(d).get("actions", [])}
    problems = [
        i
        for i in cx.of_type("issue")
        if i.status == "active"
        and i.fields.get("kind", "problem") == "problem"
        and decision(cx, i.id) is None
        and i.id not in in_rounds
        and level_of(i, checks) is not None
        and (issues is None or i.id in issues)
        and (area is None or _area_of(i, checks) == area)
    ]
    if level is None:
        level = next(
            (lv for lv in LEVELS if any(level_of(i, checks) == lv for i in problems)), None
        )
        if level is None:
            raise RoundError("no open problem issues: nothing for a new round")
    chosen = [i for i in problems if level_of(i, checks) == level]
    if not chosen:
        raise RoundError(f"no open {level} issues without a decision")
    chosen.sort(key=lambda i: -score(i, weights, checks.get(str(i.fields.get("check", "")))))
    previous = [a for d in dirs if d != reuse for a in _round_meta(d).get("actions", [])]
    next_id = 1 + max((int(a["id"][1:]) for a in previous), default=0)
    number = int(reuse.name.split("-")[1]) if reuse else len(dirs) + 1
    out_dir = ws_root / "revisions" / f"round-{number:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "round": number,
        "level": level,
        "version": cx.draft,
        "language": lang,
        "actions": [{"id": f"A{next_id + k}", "issue": i.id} for k, i in enumerate(chosen)],
    }
    out = out_dir / "round.json"
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ix, loc = _locator(ws_root, cx, lang)
    actions = round_actions(ws_root, out_dir, cx, loc)
    text = "\n".join(ix.paragraphs)
    try:
        prose_on = settings.load(ws_root)["prose_suggestions"] is True
    except settings.SettingsError:
        prose_on = False
    warnings = [] if prose_on else [w for a in actions for w in prose_flags(a, text)]
    latest = structure.latest_version(ws_root)
    if latest != cx.draft:
        warnings.append(f"{latest} is ingested but the Codex is on {cx.draft}: run `lc codex sync`")
    warnings += [f"{a['id']}: its place is gone from {cx.draft}" for a in actions if not a["where"]]
    return out, actions, warnings


def latest_round(ws_root: Path) -> Path:
    dirs = round_dirs(ws_root)
    if not dirs:
        raise RoundError("no rounds yet; run `lc round build` first")
    return dirs[-1]


def mark(ws_root: Path, action_id: str, status: str, reason: str = "") -> dict[str, Any]:
    """Record the writer's decision on an action's issue (``pending`` withdraws it)."""
    if status not in STATUSES:
        raise RoundError(f"status must be one of {STATUSES}")
    cx = Codex(ws_root)
    for d in reversed(round_dirs(ws_root)):
        for entry in _round_meta(d).get("actions", []):
            if entry["id"] != action_id:
                continue
            if entry["issue"] not in cx.items:
                raise RoundError(f"{action_id}: its issue {entry['issue']} is not in the Codex")
            current = decision(cx, entry["issue"])
            if current is not None:
                cx.retire(current.id, by="writer")
            if status != "pending":
                at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                fields = {"verdict": status, "at": at, **({"reason": reason} if reason else {})}
                cx.add(
                    "decision",
                    f"{action_id}: {status}",
                    fields,
                    links=[{"rel": "about", "to": entry["issue"]}],
                    by="writer",
                )
            found = [a for a in round_actions(ws_root, d, cx) if a["id"] == action_id]
            if not found:
                raise RoundError(f"{action_id}: its issue could not be read from the Codex")
            return found[0]
    raise RoundError(f"no action {action_id!r}")


def status(ws_root: Path) -> dict[str, Any]:
    d = latest_round(ws_root)
    actions = round_actions(ws_root, d)
    counts: dict[str, int] = {}
    for a in actions:
        counts[a["status"]] = counts.get(a["status"], 0) + 1
    open_high = [
        a["id"]
        for a in actions
        if a["status"] in ("pending", "accepted") and a["severity"] == "high" and a["where"]
    ]
    return {
        "round": d.name,
        "level": _round_meta(d).get("level"),
        "actions": len(actions),
        "by_status": counts,
        "open_high": open_high,
        "can_close": not open_high,
        # What is still to address, in the round's order: what the writer sees as "what remains".
        "remaining": [
            {k: a[k] for k in ("id", "status", "severity", "what", "where")}
            for a in actions
            if a["status"] in OPEN
        ],
    }


# --- letter ---------------------------------------------------------------------------

TEXT: dict[str, dict[str, Any]] = {
    "es": {
        "title": "Ronda {n}: {level}",
        "levels": {
            "structural": "estructura",
            "scene": "escenas y personajes",
            "line": "prosa y diálogo",
        },
        "intro": (
            "En esta ronda nos ocupamos solo de {level}. Cada punto dice qué mirar, por qué y "
            "qué opciones hay; tú decides qué cambiar y cómo escribirlo. Para cada uno, dime "
            "si lo aceptas, lo rechazas o lo dejas para más adelante. Vamos de uno en uno."
        ),
        "strengths": "Lo que funciona y conviene proteger",
        "actions": "Qué revisar",
        "where": "Dónde",
        "what": "Qué",
        "why": "Por qué",
        "options": "Opciones",
    },
    "en": {
        "title": "Round {n}: {level}",
        "levels": {
            "structural": "structure",
            "scene": "scenes and characters",
            "line": "prose and dialogue",
        },
        "intro": (
            "This round covers {level} only. Each point says what to look at, why, and which "
            "options there are; you decide what to change and how to write it. For each one, "
            "tell me whether you accept it, reject it or leave it for later. One at a time."
        ),
        "strengths": "What works and should be protected",
        "actions": "What to look at",
        "where": "Where",
        "what": "What",
        "why": "Why",
        "options": "Options",
    },
}


def letter(ws_root: Path, version: str | None = None) -> Path:
    """Render the latest round's letter from the Codex's issues."""
    d = latest_round(ws_root)
    cx = Codex(ws_root)
    meta = _round_meta(d)
    lang = str(meta.get("language") or language(ws_root))
    _, loc = _locator(ws_root, cx, lang)
    actions = [a for a in round_actions(ws_root, d, cx, loc) if a["where"]]
    t = TEXT.get(lang, TEXT["en"])
    level_name = t["levels"][str(meta.get("level", "structural"))]
    n = int(d.name.split("-")[1])
    lines = [
        f"# {t['title'].format(n=n, level=level_name)}",
        "",
        t["intro"].format(level=level_name),
        "",
    ]
    strengths = strength_lines(ws_root, cx, lang, loc)
    if strengths:
        lines += [f"## {t['strengths']}", "", *strengths, ""]
    lines += [f"## {t['actions']}", ""]
    for k, a in enumerate(actions, 1):  # actions without a place wait in the re-read queue
        where = locate.describe(locate.from_where(a["where"]), lang)
        lines += [
            f"### {k}. {a['what']}",
            "",
            f"**{t['where']}:** {where}",
            "",
            f"**{t['why']}:** {a['why']}",
            "",
            f"**{t['options']}:**",
            *[f"- {o}" for o in a["options"]],
            "",
        ]
    out = d / "letter.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def located_line(cx: Codex, issue: Item, loc: locate.Locations, lang: str) -> str | None:
    """'- why (where)' for an issue, or None when its place is gone."""
    where = located(cx, issue, loc)
    if where is None:
        return None
    return f"- {issue.fields.get('why') or issue.text} ({locate.describe(where, lang)})"


def live(cx: Codex, kind: str) -> list[Item]:
    """Active issues of a kind (problem or strength) the writer has not rejected or closed."""
    return [
        i
        for i in cx.of_type("issue")
        if i.status == "active"
        and i.fields.get("kind", "problem") == kind
        and action_status(cx, i.id) in OPEN
    ]


def strength_lines(
    ws_root: Path, cx: Codex, lang: str, loc: locate.Locations | None = None
) -> list[str]:
    strengths = live(cx, "strength")
    if not strengths:
        return []
    if loc is None:
        _, loc = _locator(ws_root, cx, lang)
    return [line for i in strengths if (line := located_line(cx, i, loc, lang))]
