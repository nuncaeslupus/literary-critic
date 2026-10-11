"""Revision rounds: findings become prioritised, located actions and a letter.

Rounds follow editorial order: structural first, then scene and character,
then prose and dialogue. ``build`` takes the open problem findings of the
earliest level that still has any, scores them (severity x confidence x the
profile's weight / effort) and writes ``revisions/round-NN/actions.json``.
``letter`` renders the writer-facing ``letter.md`` in the novel's language.
The script only arranges what the findings say; it never writes prose for the
novel, and it flags quoted passages in actions that are not in the manuscript.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from litcritic import checklist, locate, query, validate
from litcritic.workspace import repo_root

LEVELS = ("structural", "scene", "line")
STAGE_LEVEL = {
    "orientation": "structural",
    "developmental": "structural",
    "scene": "scene",
    "line": "line",
    "verification": "line",
}
SEVERITY = {"high": 3.0, "medium": 2.0, "low": 1.0}
EFFORT = {"S": 1.0, "M": 1.5, "L": 2.0}
QUOTE = re.compile(r"«([^»]+)»|“([^”]+)”|\"([^\"]+)\"")
MAX_QUOTE_WORDS = 12

DEFAULT_OPTIONS = {
    "es": ["Mantenerlo así (si es deliberado, dime por qué)", "Revisarlo como se describe"],
    "en": ["Keep it as it is (if it is deliberate, tell me why)", "Revise it as described"],
}


class RoundError(Exception):
    """Findings or rounds cannot be processed."""


def _load_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def round_dirs(ws_root: Path) -> list[Path]:
    base = ws_root / "revisions"
    return sorted(p for p in base.glob("round-[0-9][0-9]") if p.is_dir()) if base.is_dir() else []


def level_of(finding: dict[str, Any], checks: dict[str, checklist.Check]) -> str:
    check = checks.get(finding["check_id"])
    if check is None:
        return "scene"
    if check.action_level in LEVELS:
        return check.action_level
    return STAGE_LEVEL.get(check.stage, "scene")


def score(
    finding: dict[str, Any], weights: dict[str, float], check: checklist.Check | None
) -> float:
    weight = 1.0
    if check is not None:
        weight = float(weights.get(check.id, weights.get(check.area, 1.0)))
    return (
        SEVERITY.get(finding["severity"], 1.0)
        * float(finding["confidence"])
        * weight
        / EFFORT.get(finding["effort"], 1.5)
    )


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


def _paragraph_anchor(ix: query.Index, anchor: str) -> str:
    return ix.anchors[query._range(ix, anchor).start]


def build(
    ws_root: Path, version: str | None = None, level: str | None = None
) -> tuple[Path, list[dict[str, Any]], list[str]]:
    """Write the next round's actions; returns (path, actions, warnings)."""
    ix = query.load(ws_root, version)
    version = version or _latest(ws_root)
    findings = _load_json(ws_root / "analysis" / "findings.json", None)
    if findings is None:
        raise RoundError("no analysis/findings.json yet; run the checks first")
    cat = checklist.load(repo_root() / "checklist")
    errors = validate.validate("finding", findings, cat)
    if errors:
        raise RoundError("findings are invalid: " + "; ".join(errors[:5]))
    checks = {c.id: c for c in cat.checks}
    profile_file = ws_root / "analysis" / "profile.toml"
    profile = (
        tomllib.loads(profile_file.read_text(encoding="utf-8")) if profile_file.is_file() else {}
    )
    weights = {str(k): float(v) for k, v in profile.get("weights", {}).items()}
    lang = _language(ws_root, profile)
    problems = [f for f in findings if f["kind"] == "problem" and f["status"] == "open"]
    if level is None:
        level = next(
            (lv for lv in LEVELS if any(level_of(f, checks) == lv for f in problems)), None
        )
        if level is None:
            raise RoundError("no open problem findings: nothing for a new round")
    chosen = [f for f in problems if level_of(f, checks) == level]
    chosen.sort(key=lambda f: -score(f, weights, checks.get(f["check_id"])))
    previous = [a for d in round_dirs(ws_root) for a in _load_json(d / "actions.json", [])]
    next_id = 1 + max((int(a["id"][1:]) for a in previous), default=0)
    number = len(round_dirs(ws_root)) + 1
    loc = locate.LocatorBuilder(ix, locate.load_meta(ws_root, version))
    actions = []
    for k, f in enumerate(chosen):
        check = checks.get(f["check_id"])
        where = loc.locate(_paragraph_anchor(ix, f["anchors"][0])).as_where()
        actions.append(
            {
                "schema_version": 1,
                "id": f"A{next_id + k}",
                "finding_ids": [f["id"]],
                "level": level,
                "round": number,
                "what": f.get("what") or (check.title if check else f["check_id"]),
                "why": f.get("explanation") or (check.question if check else ""),
                "where": where,
                "options": f.get("options") or DEFAULT_OPTIONS.get(lang, DEFAULT_OPTIONS["en"]),
                "status": "pending",
            }
        )
    errors = validate.validate("action", actions)
    if errors:
        raise RoundError("actions are invalid: " + "; ".join(errors[:5]))
    warnings = [w for a in actions for w in prose_flags(a, "\n".join(ix.paragraphs))]
    out_dir = ws_root / "revisions" / f"round-{number:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "actions.json"
    out.write_text(json.dumps(actions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out, actions, warnings


def _latest(ws_root: Path) -> str:
    from litcritic import structure

    return structure.latest_version(ws_root)


def _language(ws_root: Path, profile: dict[str, Any]) -> str:
    if profile.get("language"):
        return str(profile["language"])
    manifest = ws_root / "workspace.toml"
    if manifest.is_file():
        return str(tomllib.loads(manifest.read_text(encoding="utf-8")).get("language", "en"))
    return "en"


def latest_round(ws_root: Path) -> Path:
    dirs = round_dirs(ws_root)
    if not dirs:
        raise RoundError("no rounds yet; run `lc round build` first")
    return dirs[-1]


def mark(ws_root: Path, action_id: str, status: str) -> dict[str, Any]:
    """Set an action's status (pending/accepted/rejected/done/deferred) in its round."""
    for d in reversed(round_dirs(ws_root)):
        path = d / "actions.json"
        actions = _load_json(path, [])
        for a in actions:
            if a["id"] == action_id:
                a["status"] = status
                errors = validate.validate("action", a)
                if errors:
                    raise RoundError("; ".join(errors))
                path.write_text(
                    json.dumps(actions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
                )
                return dict(a)
    raise RoundError(f"no action {action_id!r}")


def status(ws_root: Path) -> dict[str, Any]:
    d = latest_round(ws_root)
    actions = _load_json(d / "actions.json", [])
    counts: dict[str, int] = {}
    for a in actions:
        counts[a["status"]] = counts.get(a["status"], 0) + 1
    findings = {f["id"]: f for f in _load_json(ws_root / "analysis" / "findings.json", [])}
    open_high = [
        a["id"]
        for a in actions
        if a["status"] in ("pending", "accepted")
        and any(findings.get(fid, {}).get("severity") == "high" for fid in a["finding_ids"])
    ]
    return {
        "round": d.name,
        "level": actions[0]["level"] if actions else None,
        "actions": len(actions),
        "by_status": counts,
        "open_high": open_high,
        "can_close": not open_high,
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
    d = latest_round(ws_root)
    actions = _load_json(d / "actions.json", [])
    profile_file = ws_root / "analysis" / "profile.toml"
    profile = (
        tomllib.loads(profile_file.read_text(encoding="utf-8")) if profile_file.is_file() else {}
    )
    lang = _language(ws_root, profile)
    t = TEXT.get(lang, TEXT["en"])
    ix = query.load(ws_root, version)
    loc = locate.LocatorBuilder(ix, locate.load_meta(ws_root, version or _latest(ws_root)))
    level = actions[0]["level"] if actions else "structural"
    level_name = t["levels"][level]
    n = int(d.name.split("-")[1])
    lines = [
        f"# {t['title'].format(n=n, level=level_name)}",
        "",
        t["intro"].format(level=level_name),
        "",
    ]
    findings = _load_json(ws_root / "analysis" / "findings.json", [])
    strengths = [f for f in findings if f["kind"] == "strength" and f["status"] != "rejected"]
    if strengths:
        lines += [f"## {t['strengths']}", ""]
        for f in strengths:
            where = locate.describe(loc.locate(_paragraph_anchor(ix, f["anchors"][0])), lang)
            lines.append(f"- {f.get('explanation', '')} ({where})")
        lines.append("")
    lines += [f"## {t['actions']}", ""]
    for k, a in enumerate(actions, 1):
        where = locate.describe(loc.locate(a["where"]["anchor"]), lang)
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
