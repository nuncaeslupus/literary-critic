"""The work plan the writer steers: ordered parts, each with a status, and the log of every move.

``<ws>/plan/log.jsonl`` is append-only and the source of truth, one event per line.
``<ws>/plan/plan.json`` is the snapshot replayed from it, rewritten after every
command (temp file, then replace) and never edited by hand; ``lc plan check`` compares
it with a fresh replay. ``apply`` is pure: a state and an event give the next state.

A part moves ``proposed -> todo -> active -> done``; ``proposed``, ``todo`` and
``active`` can be ``skipped`` (reason required); ``skipped`` and ``done`` can be
reopened to ``todo`` (reason required). ``move`` and ``edit`` work from any status.
The assistant records a writer's move only on the writer's word (``--by writer``).

Event fields: ``seq``, ``at`` (UTC), ``by`` (``writer`` | ``tool``), ``event``, ``part``,
``reason`` (where required), ``refs``, and ``data`` for what the event carries (the new
part's kind and title, the part it goes after, the edited fields).
"""

from __future__ import annotations

import copy
import json
import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from litcritic import rounds, workspace
from litcritic.codex import Codex, CodexError

SCHEMA_VERSION = 1
PLAN_DIR = "plan"
LOG = "log.jsonl"
SNAPSHOT = "plan.json"

MODES = ("iterative", "report")
PROFILE_MODES = {"revision": "iterative", "reader-report": "report"}
KINDS = ("overview", "checks", "round", "report", "report-part", "new-draft", "aspect")
STATUSES = ("proposed", "todo", "active", "done", "skipped")
BY = ("writer", "tool")

# command -> (event name, statuses it may start from, status it leads to)
COMMANDS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "accept": ("accepted", ("proposed",), "todo"),
    "start": ("started", ("proposed", "todo"), "active"),
    "done": ("done", ("active",), "done"),
    "skip": ("skipped", ("proposed", "todo", "active"), "skipped"),
    "reopen": ("reopened", ("skipped", "done"), "todo"),
}
_EVENT_TARGET = {ev: target for ev, _sources, target in COMMANDS.values()}
_PART_EVENTS = (*_EVENT_TARGET, "moved", "edited")
REASON_REQUIRED = frozenset({"skipped", "dismissed", "reopened"})
_TITLES = {
    "en": {
        "overview": "Overview: what works, the biggest problems",
        "checks": "Checks on the whole text",
        "report": "The reader report",
    },
    "es": {
        "overview": "Panorama: qué funciona, los problemas mayores",
        "checks": "Revisiones sobre todo el texto",
        "report": "El informe de lectura",
    },
}
_SEEDS = {"iterative": ("overview",), "report": ("checks", "report")}


class PlanError(Exception):
    """The plan files cannot be read or written."""


class Refused(Exception):
    """A move the plan does not allow. ``reason`` is one of a fixed set."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


# --- files -------------------------------------------------------------------


def _dir(root: Path) -> Path:
    return root / PLAN_DIR


def log_path(root: Path) -> Path:
    return _dir(root) / LOG


def snapshot_path(root: Path) -> Path:
    return _dir(root) / SNAPSHOT


def read_log(root: Path) -> list[dict[str, Any]]:
    f = log_path(root)
    if not f.is_file():
        return []
    events: list[dict[str, Any]] = []
    for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except ValueError as exc:
            raise PlanError(f"{LOG} line {n} is not JSON: {exc}") from exc
        if not isinstance(ev, dict) or not isinstance(ev.get("seq"), int) or not ev.get("event"):
            raise PlanError(f"{LOG} line {n} is not an event")
        events.append(ev)
    return events


def _append(root: Path, event: dict[str, Any]) -> None:
    _dir(root).mkdir(parents=True, exist_ok=True)
    with log_path(root).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def write_snapshot(root: Path, state: dict[str, Any]) -> None:
    """Atomically replace plan.json (temp file in the same folder, then replace)."""
    _dir(root).mkdir(parents=True, exist_ok=True)
    final = snapshot_path(root)
    tmp = final.with_name(final.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, final)


# --- the pure core -----------------------------------------------------------


def empty_state(mode: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "parts": [],
        "changes": {},
        "last_seq": 0,
    }


def _find(state: dict[str, Any], part_id: object) -> dict[str, Any] | None:
    for p in state["parts"]:
        if p["id"] == part_id:
            return p  # type: ignore[no-any-return]
    return None


def next_part_id(state: dict[str, Any]) -> str:
    nums = [int(p["id"][1:]) for p in state["parts"] if p["id"][1:].isdigit()]
    return f"P{max(nums, default=0) + 1}"


def _renumber(state: dict[str, Any]) -> None:
    for i, p in enumerate(state["parts"], 1):
        p["order"] = i


def refusal(state: dict[str, Any], event: dict[str, Any]) -> Refused | None:
    """Why ``event`` may not follow ``state``, or None. Unknown event names pass."""
    name = event.get("event")
    if event.get("by") not in BY:
        return Refused("missing_by", "say who moves the part: --by writer or --by tool")
    if name in REASON_REQUIRED and not str(event.get("reason") or "").strip():
        return Refused("missing_reason", f"{name} needs a reason, in the writer's words")
    data = event.get("data") or {}
    if name == "initialized":
        if state["last_seq"] or state["mode"]:
            return Refused("already_initialized", "this work already has a plan")
        if data.get("mode") not in MODES:
            return Refused("invalid", f"mode must be one of {', '.join(MODES)}")
        seeded = [p.get("status", "proposed") for p in data.get("parts", [])]
        if any(st not in STATUSES for st in seeded) or seeded.count("active") > 1:
            return Refused("invalid", "seeded parts need valid statuses and at most one active")
        return None
    if name != "added" and name not in _PART_EVENTS:
        return None
    if state["mode"] is None:
        return Refused("no_plan", "there is no plan yet: run `lc plan init`")
    if name == "added":
        if data.get("kind") not in KINDS:
            return Refused("invalid", f"kind must be one of {', '.join(KINDS)}")
        if not str(data.get("title") or "").strip():
            return Refused("invalid", "a part needs a title")
        if event.get("part") != next_part_id(state):
            return Refused("invalid", "the part id does not follow the plan")
        after = data.get("after")
        if after and _find(state, after) is None:
            return Refused("unknown_part", f"no part {after}")
        return None
    part = _find(state, event.get("part"))
    if part is None:
        return Refused("unknown_part", f"no part {event.get('part')}")
    for cmd, (ev, sources, _target) in COMMANDS.items():
        if ev == name and part["status"] not in sources:
            return Refused("transition", f"`{cmd}` cannot move a part that is {part['status']}")
    if name == "started":
        other = next((p for p in state["parts"] if p["status"] == "active"), None)
        if other is not None:
            return Refused("one_active", f"{other['id']} is already active")
    if name == "moved":
        after = data.get("after")
        if after and _find(state, after) is None:
            return Refused("unknown_part", f"no part {after}")
        if after == part["id"]:
            return Refused("invalid", "a part cannot go after itself")
    if name == "edited":
        if not ({"title", "refs"} & set(data)):
            return Refused("invalid", "edit needs a title or refs")
        if "title" in data and not str(data["title"]).strip():
            return Refused("invalid", "a part needs a title")
        if "refs" in data and not isinstance(data["refs"], dict):
            return Refused("invalid", "refs must be an object")
    return None


def apply(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """The state after ``event``. Pure; raises Refused when the event does not fit."""
    bad = refusal(state, event)
    if bad is not None:
        raise bad
    new = copy.deepcopy(state)
    new["last_seq"] = int(event["seq"])
    name = event["event"]
    data = event.get("data") or {}
    if name == "initialized":
        new["mode"] = data["mode"]
        for part in data.get("parts", []):
            new["parts"].append(
                {
                    **part,
                    "status": part.get("status", "proposed"),
                    "origin": "tool",
                    "refs": part.get("refs") or {},
                }
            )
        _renumber(new)
    elif name == "added":
        part = {
            "id": event["part"],
            "kind": data["kind"],
            "title": data["title"],
            "status": "todo" if event["by"] == "writer" else "proposed",
            "order": 0,
            "origin": event["by"],
            "refs": event.get("refs") or {},
        }
        after = data.get("after")
        at = len(new["parts"]) if not after else 1 + new["parts"].index(_find(new, after))
        new["parts"].insert(at, part)
        _renumber(new)
    elif name in _EVENT_TARGET:
        part = _find(new, event["part"])
        assert part is not None
        part["status"] = _EVENT_TARGET[name]
    elif name == "moved":
        part = _find(new, event["part"])
        assert part is not None
        new["parts"].remove(part)
        after = data.get("after")
        at = 0 if not after else 1 + new["parts"].index(_find(new, after))
        new["parts"].insert(at, part)
        _renumber(new)
    elif name == "edited":
        part = _find(new, event["part"])
        assert part is not None
        if "title" in data:
            part["title"] = data["title"]
        if "refs" in data:
            part["refs"] = data["refs"]
    return new  # unknown event names are kept in the log and skipped


def replay(events: list[dict[str, Any]]) -> dict[str, Any]:
    state = empty_state()
    for ev in events:
        try:
            state = apply(state, ev)
        except Refused as exc:
            raise PlanError(f"{LOG} event {ev.get('seq')}: {exc.message}") from exc
    return state


# --- commands ----------------------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def seed_parts(mode: str, language: str = "en") -> list[dict[str, Any]]:
    titles = _TITLES.get(language, _TITLES["en"])
    return [
        {"id": f"P{i}", "kind": kind, "title": titles[kind]}
        for i, kind in enumerate(_SEEDS[mode], 1)
    ]


def _round_title(d: Path, language: str) -> str:
    meta = rounds.load_json(d / "round.json", {})
    text = rounds.TEXT.get(language, rounds.TEXT["en"])
    level = str(meta.get("level") or "")
    return str(text["title"]).format(
        n=int(d.name.split("-")[1]), level=text["levels"].get(level, level)
    )


def round_parts(root: Path, language: str = "en") -> list[dict[str, Any]]:
    """One ``round`` part per existing round; the latest with open actions is active.

    Read-only. A workspace whose Codex cannot be read counts its rounds as done.
    """
    dirs = rounds.round_dirs(root)
    if not dirs:
        return []
    open_by_round: dict[str, int] = {}
    try:
        cx = Codex(root)
        open_by_round = {d.name: rounds.open_actions(root, d, cx) for d in dirs}
    except (CodexError, OSError, ValueError):
        pass
    active = next((d.name for d in reversed(dirs) if open_by_round.get(d.name)), None)
    return [
        {
            "id": f"P{i}",
            "kind": "round",
            "title": _round_title(d, language),
            "status": "active" if d.name == active else "done",
            "refs": {"round": d.name},
        }
        for i, d in enumerate(dirs, 1)
    ]


def initial_parts(root: Path, mode: str) -> list[dict[str, Any]]:
    """What ``init`` seeds: the rounds already there, else the mode's proposed parts."""
    language = _language(root)
    return round_parts(root, language) or seed_parts(mode, language)


def profile_mode(root: Path) -> str | None:
    f = root / "analysis" / "profile.toml"
    try:
        profile = tomllib.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    except (OSError, ValueError):
        return None
    return PROFILE_MODES.get(str(profile.get("mode", "")))


def _language(root: Path) -> str:
    try:
        return rounds.language(root)
    except (OSError, ValueError):
        return "en"


def load_state(root: Path) -> dict[str, Any]:
    return replay(read_log(root))


def record(
    root: Path, name: str, by: str | None, **fields: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Append one event (checked against the replayed log), then write the snapshot.

    Returns ``(state, event)``. Raises Refused and writes nothing when the move is not allowed.
    """
    state = load_state(root)
    event: dict[str, Any] = {
        "seq": state["last_seq"] + 1,
        "at": _now(),
        "by": by,
        "event": name,
    }
    for key in ("part", "reason", "data"):
        if fields.get(key) not in (None, "", {}):
            event[key] = fields[key]
    event["refs"] = fields.get("refs") or {}
    new = apply(state, event)  # raises Refused before anything is written
    _append(root, event)
    write_snapshot(root, new)
    return new, event


def init(
    root: Path, mode: str | None, by: str | None = "tool"
) -> tuple[dict[str, Any], dict[str, Any]]:
    mode = mode or profile_mode(root)
    if mode is None:
        raise Refused("invalid", f"say the mode: --mode {'|'.join(MODES)}")
    data: dict[str, Any] = {"mode": mode, "parts": initial_parts(root, mode)}
    return record(root, "initialized", by, data=data)


def add(
    root: Path,
    kind: str,
    title: str,
    by: str | None,
    after: str | None = None,
    refs: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = load_state(root)
    data: dict[str, Any] = {"kind": kind, "title": title}
    if after:
        data["after"] = after
    return record(root, "added", by, part=next_part_id(state), data=data, refs=refs)


def transition(
    root: Path, command: str, part: str, by: str | None, reason: str = ""
) -> tuple[dict[str, Any], dict[str, Any]]:
    return record(root, COMMANDS[command][0], by, part=part, reason=reason)


def move(
    root: Path, part: str, by: str | None, after: str | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    return record(root, "moved", by, part=part, data={"after": after} if after else {})


def edit(
    root: Path,
    part: str,
    by: str | None,
    title: str | None = None,
    refs: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data: dict[str, Any] = {}
    if title is not None:
        data["title"] = title
    if refs is not None:
        data["refs"] = refs
    return record(root, "edited", by, part=part, data=data)


def status(root: Path, timeline: int = 10) -> dict[str, Any]:
    events = read_log(root)
    if not events:
        mode = profile_mode(root) or "iterative"
        proposed = [
            {
                **p,
                "status": p.get("status", "proposed"),
                "origin": "tool",
                "order": i,
                "refs": p.get("refs") or {},
            }
            for i, p in enumerate(initial_parts(root, mode), 1)
        ]
        return {"status": "no_plan", "mode": mode, "proposed": proposed}
    state = replay(events)
    parts = state["parts"]
    by_status: dict[str, int] = {}
    for p in parts:
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1
    rows = [
        {
            "at": e.get("at"),
            "what": e["event"],
            "id": e.get("part") or e.get("change") or e.get("id"),
            "reason": e.get("reason", ""),
            "by": e.get("by"),
        }
        for e in events
    ]
    rows += _decision_rows(root, parts)
    rows.sort(key=lambda r: str(r["at"] or ""))  # stable: same-time rows keep log order
    active = next((p for p in parts if p["status"] == "active"), None)
    return {
        "status": "ok",
        "mode": state["mode"],
        "active": _with_round(root, active) if active else None,
        "next": [p for p in parts if p["status"] == "todo"][:3],
        "by_status": by_status,
        "timeline": rows[::-1][:timeline] if timeline > 0 else [],
    }


def _round_of(part: dict[str, Any]) -> str | None:
    name = (part.get("refs") or {}).get("round")
    return str(name) if name else None


def _with_round(root: Path, part: dict[str, Any]) -> dict[str, Any]:
    """An active round part with its round and what remains in it (read live)."""
    name = _round_of(part)
    if part["kind"] != "round" or not name:
        return part
    out = {**part, "round": name}
    try:
        st = rounds.status(root, name)
    except (rounds.RoundError, CodexError, OSError, ValueError) as exc:
        return {**out, "remaining": [], "can_close": False, "round_unreadable": str(exc)}
    return {**out, "remaining": st["remaining"], "can_close": st["can_close"]}


def _decision_rows(root: Path, parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The writer's current decisions on the plan's rounds (none when the Codex is unreadable)."""
    names = dict.fromkeys(n for n in map(_round_of, parts) if n)
    out: list[dict[str, Any]] = []
    try:
        cx = Codex(root)
        for name in names:
            meta = rounds.load_json(root / "revisions" / name / "round.json", {})
            for entry in meta.get("actions", []):
                d = rounds.decision(cx, str(entry.get("issue")))
                if d is None:
                    continue
                out.append(
                    {
                        "at": d.fields.get("at"),
                        "what": "decision",
                        "id": entry["id"],
                        "verdict": d.fields.get("verdict"),
                        "reason": d.fields.get("reason", ""),
                        "by": "writer",
                    }
                )
    except (CodexError, OSError, ValueError, KeyError):
        pass
    return out


def command_for(part: dict[str, Any]) -> list[str] | None:
    """The ``lc`` command (after ``lc``) that carries a part out; None when it is read."""
    refs = part.get("refs") or {}
    issues = refs.get("issues")
    filters: list[str] = []
    if refs.get("area"):
        filters = ["--area", str(refs["area"])]
    elif isinstance(issues, list) and issues:
        filters = ["--issues", ",".join(str(i) for i in issues)]
    if part["kind"] == "round":
        if refs.get("round"):
            return ["round", "status"]
        return ["round", "build", *(["--level", str(refs["level"])] if refs.get("level") else [])]
    if part["kind"] in ("aspect", "report-part") and filters:
        return ["round", "build", *filters]
    return None


def next_part(root: Path) -> dict[str, Any]:
    state = load_state(root)
    if state["mode"] is None:
        raise Refused("no_plan", "there is no plan yet: run `lc plan init`")
    part = next((p for p in state["parts"] if p["status"] == "todo"), None)
    return {"status": "ok", "part": part, "command": command_for(part) if part else None}


def check(root: Path, repair: bool = False) -> dict[str, Any]:
    """Compare plan.json with a replay of the log; ``repair`` rewrites it from the log."""
    state = load_state(root)
    snap_file = snapshot_path(root)
    snap: Any = None
    if snap_file.is_file():
        try:
            snap = json.loads(snap_file.read_text(encoding="utf-8"))
        except ValueError:
            snap = None
    if snap == state or (snap is None and not log_path(root).is_file()):
        return {"status": "ok", "last_seq": state["last_seq"]}
    first = _first_difference(snap, state)
    if repair:
        write_snapshot(root, state)
        return {"status": "repaired", "last_seq": state["last_seq"], "differs": first}
    return {"status": "differs", "last_seq": state["last_seq"], "differs": first}


def _first_difference(snap: Any, state: dict[str, Any]) -> str:
    if not isinstance(snap, dict):
        return "plan.json is missing or unreadable"
    have = {p.get("id"): p for p in snap.get("parts", []) if isinstance(p, dict)}
    for p in state["parts"]:
        if have.get(p["id"]) != p:
            return str(p["id"])
    for p_id in have:
        if _find(state, p_id) is None:
            return str(p_id)
    return "the plan's header (mode, changes or last_seq)"


# --- CLI ---------------------------------------------------------------------


def _json_object(text: str | None) -> dict[str, Any] | None:
    if text is None:
        return None
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise Refused("invalid", f"--refs-json is not JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise Refused("invalid", "--refs-json must be a JSON object")
    return value


def _out(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def _answer(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "ok", "event": event}
    if event.get("part"):
        out["part"] = _find(state, event["part"])
    else:
        out["mode"] = state["mode"]
        out["parts"] = state["parts"]
    return out


def _cmd(args: Any) -> int:
    try:
        root = workspace.resolve(args.workspace, args.home).root
        act = args.action
        if act == "status":
            _out(status(root, args.timeline))
            return 0
        if act == "next":
            _out(next_part(root))
            return 0
        if act == "check":
            out = check(root, args.repair)
            _out(out)
            return 1 if out["status"] == "differs" else 0
        if act == "init":
            state, event = init(root, args.mode, args.by or "tool")
        elif act == "add":
            if not args.kind or not args.title:
                raise Refused("invalid", "usage: lc plan add --kind K --title T --by writer")
            refs = _json_object(args.refs_json)
            state, event = add(root, args.kind, args.title, args.by, args.after, refs)
        else:
            if not args.part:
                raise Refused("invalid", f"usage: lc plan {act} P1 --by writer")
            if act == "move":
                state, event = move(root, args.part, args.by, args.after)
            elif act == "edit":
                refs = _json_object(args.refs_json)
                state, event = edit(root, args.part, args.by, args.title, refs)
            else:
                state, event = transition(root, act, args.part, args.by, args.reason or "")
        _out(_answer(state, event))
        return 0
    except Refused as exc:
        _out({"status": "refused", "reason": exc.reason, "message": exc.message})
        return 1
    except (workspace.WorkspaceError, PlanError, OSError, ValueError) as exc:
        _out({"status": "error", "message": str(exc)})
        return 2


def register(sub: Any) -> None:
    p = sub.add_parser("plan", help="the work plan: parts the writer steers, and its log")
    actions = [
        "init",
        "add",
        "accept",
        "start",
        "skip",
        "done",
        "reopen",
        "move",
        "edit",
        "status",
        "next",
        "check",
    ]
    p.add_argument("action", choices=actions)
    p.add_argument("part", nargs="?", default=None, help="the part, e.g. P3")
    p.add_argument("--workspace", required=True, help="workspace folder or slug")
    p.add_argument("--mode", choices=list(MODES), default=None, help="for init")
    p.add_argument("--kind", choices=list(KINDS), default=None, help="for add")
    p.add_argument("--title", default=None, help="for add and edit, in the writer's words")
    p.add_argument("--after", default=None, help="for add and move: the part it goes after")
    p.add_argument("--refs-json", default=None, help="for add and edit: a JSON object of refs")
    p.add_argument("--by", choices=list(BY), default=None, help="who moves it")
    p.add_argument("--reason", default=None, help="why, in the writer's words")
    p.add_argument("--timeline", type=int, default=10, help="status: how many events to list")
    p.add_argument("--repair", action="store_true", help="check: rewrite plan.json from the log")
    p.add_argument("--home", type=Path, default=None, help="where to look for works")
    p.set_defaults(func=_cmd)
