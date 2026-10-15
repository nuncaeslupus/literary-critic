"""``lc mcp``: literary-critic as an MCP server for the Claude desktop app.

The desktop extension (``literary-critic.mcpb``) starts this server; the app talks to it
over stdio with newline-delimited JSON-RPC 2.0. It is a small standard-library server of
its own: doc-control's ``mcp`` module is internal to doc-control, so it is not reused.

A tool is a name, a description, an input schema and a handler that takes the
arguments and returns a JSON object. Every result is one ``text`` block holding that
object. A handler raises ``ToolError`` for a fault the writer cannot fix by answering a
question (a refused path); "not found" and "cancelled" are ordinary results. Any other
exception is also returned as ``isError``, so a bug never kills the server.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import time
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from litcritic import __version__, change, plan, rounds, settings, structure
from litcritic.workspace import Workspace, repo_root

PROTOCOL_VERSION = "2025-06-18"  # answered when the client names none
SERVER_NAME = "literary-critic"
UI_EXTENSION = "io.modelcontextprotocol/ui"
UI_MIME = "text/html;profile=mcp-app"
PLACES_URI = "ui://literary-critic/places"
CHANGE_URI = "ui://literary-critic/change"
UI_PAGES = {
    PLACES_URI: Path(__file__).with_name("ui") / "places.html",
    CHANGE_URI: Path(__file__).with_name("ui") / "change.html",
}

Handler = Callable[[dict[str, Any]], dict[str, Any]]


class ToolError(Exception):
    """A tool fault, returned to the chat as ``isError`` with ``{"error": code, ...}``."""

    def __init__(self, code: str, **detail: Any) -> None:
        super().__init__(code)
        self.payload = {"error": code, **detail}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: Handler
    properties: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    ui: str = ""  # the ``ui://`` page that renders this tool's result (MCP Apps)
    app_only: bool = False  # hidden from the model: only an MCP App page may call it

    def listing(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "object", "properties": self.properties}
        if self.required:
            schema["required"] = list(self.required)
        out = {"name": self.name, "description": self.description, "inputSchema": schema}
        if self.app_only:
            out["_meta"] = {"ui": {"visibility": ["app"]}}
        elif self.ui:
            out["_meta"] = {"ui": {"resourceUri": self.ui, "visibility": ["model", "app"]}}
        return out


class Server:
    def __init__(
        self,
        tools: Iterable[Tool],
        instructions: str = "",
        version: str = __version__,
        log: TextIO | None = None,
    ) -> None:
        self.tools = {t.name: t for t in tools}
        self.instructions = instructions
        self.version = version
        self.log = log
        self.client: dict[str, Any] = {}

    def _note(self, *parts: object) -> None:
        if self.log is not None:
            print(*parts, file=self.log, flush=True)

    def handle(self, msg: Any) -> dict[str, Any] | None:
        """The response to one message, or None for a notification."""
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return _error(None, -32600, "invalid request")
        method, msg_id = msg.get("method"), msg.get("id")
        params = msg.get("params") or {}
        if "id" not in msg:
            return None
        if method == "initialize":
            self.client = params if isinstance(params, dict) else {}
            result: dict[str, Any] = {
                "protocolVersion": self.client.get("protocolVersion") or PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "extensions": {UI_EXTENSION: {"mimeTypes": [UI_MIME]}},
                },
                "serverInfo": {"name": SERVER_NAME, "version": self.version},
            }
            if self.instructions:
                result["instructions"] = self.instructions
            return _result(msg_id, result)
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(msg_id, {"tools": [t.listing() for t in self.tools.values()]})
        if method == "tools/call":
            return self._call(msg_id, params)
        if method == "resources/list":
            pages = [{"uri": u, "name": p.stem, "mimeType": UI_MIME} for u, p in UI_PAGES.items()]
            return _result(msg_id, {"resources": pages})
        if method == "resources/templates/list":
            return _result(msg_id, {"resourceTemplates": []})
        if method == "resources/read":
            uri = params.get("uri")
            if uri not in UI_PAGES:
                return _error(msg_id, -32002, f"resource not found: {uri}")
            text = UI_PAGES[uri].read_text(encoding="utf-8")
            contents = [{"uri": uri, "mimeType": UI_MIME, "text": text}]
            return _result(msg_id, {"contents": contents})
        return _error(msg_id, -32601, f"method not found: {method}")

    def _call(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        tool = self.tools.get(name) if isinstance(name, str) else None
        if tool is None:
            return _error(msg_id, -32602, f"unknown tool: {name}")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return _error(msg_id, -32602, "arguments must be an object")
        missing = [k for k in tool.required if k not in args]
        try:
            if missing:
                raise ToolError("missing_arguments", missing=missing)
            out, is_error = tool.handler(args), False
        except ToolError as exc:
            out, is_error = exc.payload, True
        except Exception as exc:
            self._note(traceback.format_exc())
            out, is_error = {"error": "internal", "detail": repr(exc)}, True
        self._note("call", name, "error" if is_error else "ok")
        text = json.dumps(out, ensure_ascii=False, indent=1)
        result: dict[str, Any] = {"content": [{"type": "text", "text": text}], "isError": is_error}
        if tool.ui and not is_error:
            result["structuredContent"] = out
            result["_meta"] = {"ui": {"resourceUri": tool.ui}}
        return _result(msg_id, result)

    def serve(self, stdin: TextIO, stdout: TextIO) -> None:
        for line in stdin:
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                reply: dict[str, Any] | None = _error(None, -32700, "parse error")
            else:
                reply = self.handle(msg)
            if reply is not None:
                stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
                stdout.flush()


def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


GUIDE = "01-chat-guide.md"
LAST_USED = Path(".cache") / "last_used"
ADD_FOLDER_HINT = (
    "If the novel is in another folder, offer to add it: add_folder opens the folder "
    "picker on the writer's screen."
)
SETUP_HINT = (
    "not_set_up lists novels in the granted folders that were never set up. If one is "
    "the writer's novel, confirm in one line, then call setup with its folder."
)
SETUP_NEXT = (
    "Tell the writer which file you will work on and how many earlier versions you found, "
    "and ask them to confirm (another file: setup again with manuscript). Then ask, one at "
    "a time: what they want (work through aspects together, or a full reader's report); "
    "who writes the new words, with ai_notice shown in full above the choices (you write "
    "everything, recommended; small fixes; suggested passages), recorded with setup "
    "prose_suggestions off, minor or on (minor and on with ack_ai_notice); and whether you may "
    "type approved changes into their file (setup edit_in_place yes or no). Then call "
    "resume with the novel's name."
)
NEXT_STEPS = {
    "setup": "Bring the manuscript in: find the novel's file and set it up (05-setup.md).",
    "index": "Finish indexing the novel, so questions are answered from the Codex "
    "(20-codex-items.md).",
    "round": "Continue the open revision round with the next pending action (60-rounds.md).",
    "overview": "Offer an overview: what works and the three biggest problems "
    "(30-orientation.md, 40-checks.md).",
    "plan": "Follow the work plan: carry on with the active part, or propose the next one "
    "and wait for the writer's word (00-guide.md).",
    "next_round": "Ask whether there is a new draft (50-new-draft.md) or start the next "
    "round (60-rounds.md).",
}


def guide() -> str:
    return (repo_root() / "prompts" / GUIDE).read_text(encoding="utf-8")


def _last_used(ws: Workspace) -> float:
    for f in (ws.root / LAST_USED, ws.root / "work.toml"):
        try:
            return f.stat().st_mtime
        except OSError:
            continue
    return 0.0


def _touch(ws: Workspace) -> None:
    f = ws.root / LAST_USED
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(time.strftime("%Y-%m-%dT%H:%M:%S") + "\n", encoding="utf-8")
    except OSError:
        pass  # ordering only: a read-only folder still resumes


def _entry(ws: Workspace) -> dict[str, Any]:
    try:
        meta = ws.manifest
    except (OSError, ValueError):
        meta = {}
    novel = ws.root.parent if ws.root.name == "literary-critic" else ws.root
    return {
        "title": meta.get("title") or novel.name,
        "id": meta.get("id", ""),
        "folder": str(novel),
        "last_used": time.strftime("%Y-%m-%d %H:%M", time.localtime(_last_used(ws))),
    }


def works_list(grant: Any) -> list[dict[str, Any]]:
    """The works in the granted folders, most recently used first."""
    found = sorted(grant.works(), key=_last_used, reverse=True)
    return [_entry(ws) for ws in found]


def _index_state(root: Path) -> dict[str, Any] | None:
    try:
        doc = json.loads((root / "index" / "work" / "plan.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    packets = doc.get("packets") or []
    todo = sum(1 for p in packets if p.get("status") != "done")
    return {"packets": len(packets), "todo": todo}


PLAN_TIMELINE = 5


def _plan_state(root: Path) -> dict[str, Any] | None:
    """The plan's active part, next parts and last events; None when there is no plan."""
    try:
        now = plan.status(root, PLAN_TIMELINE)
    except (OSError, ValueError, plan.PlanError, plan.Refused):
        return None
    if now.get("status") != "ok" or now.get("mode") is None:  # change events alone: no plan
        return None
    keep = ("mode", "active", "next", "by_status", "timeline")
    return {k: now[k] for k in keep}


def state(ws: Workspace) -> dict[str, Any]:
    """Where the work stands, and the next step to propose."""
    out: dict[str, Any] = _entry(ws)
    try:
        out["language"] = ws.manifest.get("language", "")
    except (OSError, ValueError):
        out["language"] = ""
    try:
        out["draft"] = structure.latest_version(ws.root)
    except FileNotFoundError:
        out["draft"] = None
    try:
        now = settings.load(ws.root)
        out["prose_suggestions"] = now["prose_suggestions"]
        out["edit_in_place"] = now["edit_in_place"]
    except (OSError, ValueError, settings.SettingsError):
        out["prose_suggestions"], out["edit_in_place"] = False, None
    out["index"] = _index_state(ws.root)
    try:
        out["round"] = rounds.status(ws.root)
    except (OSError, ValueError, rounds.RoundError):
        out["round"] = None
    out["plan"] = _plan_state(ws.root)
    notes = sorted((ws.root / "log").glob("*.md")) if (ws.root / "log").is_dir() else []
    out["last_notes"] = notes[-1].name if notes else None
    if out["draft"] is None:
        step = "setup"
    elif out["index"] is None or out["index"]["todo"]:
        step = "index"
    elif out["plan"] and (out["plan"]["active"] or out["plan"]["next"]):
        step = "plan"
    elif out["round"] and out["round"]["by_status"].get("pending"):
        step = "round"
    elif out["round"] is None:
        step = "overview"
    else:
        step = "next_round"
    out["next_step"] = {"step": step, "say": NEXT_STEPS[step]}
    return out


def resume(grant: Any, work: str = "") -> dict[str, Any]:
    """The named work's state and the guide; with no name, the only work there."""
    if work.strip():
        hits = grant.lookup(work)
    else:
        hits = grant.works()
        if len(hits) > 1:
            return {"choose": works_list(grant), "say": "Ask which novel to work on."}
    if not hits:
        out: dict[str, Any] = {"not_found": work, "works": works_list(grant)}
        fresh = _not_set_up(grant, work)
        if fresh:
            out["not_set_up"] = fresh
            out["hint"] = SETUP_HINT
        else:
            out["hint"] = ADD_FOLDER_HINT
        return out
    if len(hits) > 1:
        return {"ambiguous": work, "works": [_entry(ws) for ws in hits]}
    ws = hits[0]
    _touch(ws)
    return {"work": state(ws), "guide": guide()}


def _not_set_up(grant: Any, name: str) -> list[dict[str, str]]:
    """The granted novels never set up, the ones ``name`` names first."""
    from litcritic.folders import matches  # folders imports ToolError from here

    found = grant.unset()
    named = [d for d in found if name.strip() and matches(d, name)]
    return [
        {"name": d.name, "folder": str(d), **({"named": "yes"} if d in named else {})}
        for d in named + [d for d in found if d not in named]
    ]


def setup_work(grant: Any, a: dict[str, Any]) -> dict[str, Any]:
    """`lc setup` on a granted folder: find the manuscript and prepare the working folder,
    or record the writer's choices on a work already set up."""
    from litcritic import settings, setup

    if not str(a.get("folder") or "").strip():
        raise ToolError("missing_arguments", missing=["folder"])
    folder = grant.confine(str(a["folder"]))
    manuscript = a.get("manuscript")
    chosen = grant.confine(str(manuscript), base=folder) if manuscript else None
    prose = a.get("prose_suggestions")
    edit = a.get("edit_in_place")
    try:
        out = setup.setup(
            folder,
            "" if prose is None else str(prose).lower(),
            bool(a.get("ack_ai_notice")),
            chosen,
            "" if edit is None else ("yes" if edit in (True, "yes") else "no"),
        )
    except settings.NoticeRequired as exc:
        lang = setup._language(folder / setup.WORKSPACE_DIR)
        return {
            "status": "refused",
            "reason": "ai_notice",
            "message": str(exc),
            "notice": settings.notice(lang),
        }
    except (setup.SetupError, settings.SettingsError, OSError, ValueError) as exc:
        raise ToolError("setup_failed", message=str(exc)) from None
    out["say"] = SETUP_NEXT
    return out


def _add_folder(grant: Any) -> Handler:
    from litcritic.folders import add_folder  # folders imports ToolError from here

    return lambda a: add_folder(grant)


# `lc` subcommands the chat may run on a work; everything else (guard, init, kit, setup,
# upgrade, pack, mcp…) stays with the person who looks after the tool.
RUN_ALLOWED = (
    "show",
    "find",
    "context",
    "locate",
    "round",
    "codex",
    "index",
    "metrics",
    "diff",
    "report",
    "plan",
    "change",
)
RUN_OUTPUT_CAP = 20000  # characters of output returned to the chat


def _work(grant: Any, work: str) -> Workspace | dict[str, Any]:
    """The one work named ``work``, or the result to return instead."""
    hits = grant.lookup(work) if work.strip() else []
    if len(hits) == 1:
        found: Workspace = hits[0]
        return found
    if hits:
        return {"ambiguous": work, "works": [_entry(ws) for ws in hits]}
    return {"not_found": work, "works": works_list(grant), "hint": ADD_FOLDER_HINT}


def _parse(argv: list[str]) -> Any:
    from litcritic.cli import build_parser  # cli imports this module

    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            return build_parser().parse_args(argv)
    except SystemExit:
        raise ToolError("bad_command", detail=err.getvalue().strip()) from None


def run_lc(grant: Any, work: str, argv: Any) -> dict[str, Any]:
    """Run one allow-listed ``lc`` subcommand on a work; argv is a list, never a shell string."""
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        raise ToolError("not_allowed", detail="command must be a list of arguments")
    if argv[0] not in RUN_ALLOWED:
        raise ToolError("not_allowed", command=argv[0], allowed=list(RUN_ALLOWED))
    ws = _work(grant, work)
    if isinstance(ws, dict):
        return ws
    return _run_argv(grant, ws, argv)


def _run_argv(grant: Any, ws: Workspace, argv: list[str]) -> dict[str, Any]:
    """Run ``lc`` in this process on ``ws``: output captured, paths confined."""
    for a in argv[1:]:
        if a.split("=")[0] in ("--workspace", "--home"):
            raise ToolError("not_allowed", detail=f"{a} is set by the tool")
        if "/" in a or "\\" in a or a.startswith(".."):
            grant.confine(a, base=ws.root)
    try:
        args = _parse([*argv, "--workspace", str(ws.root)])
    except ToolError:
        args = _parse(argv)  # a subcommand without --workspace (`codex questions`)
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = args.func(args)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    text = out.getvalue()
    result: dict[str, Any] = {"exit": code or 0, "output": text[:RUN_OUTPUT_CAP]}
    if len(text) > RUN_OUTPUT_CAP:
        result["truncated"] = len(text)
    if err.getvalue().strip():
        result["errors"] = err.getvalue().strip()[:RUN_OUTPUT_CAP]
    return result


WORK_HINT = (
    "Use when the writer talks about their novel or manuscript, or wants to continue, "
    "resume or work on it."
)


def _json_run(grant: Any, work: str, argv: list[str]) -> dict[str, Any]:
    """A ``docx`` subcommand's JSON answer (they print JSON on success and on refusal)."""
    ws = _work(grant, work)
    if isinstance(ws, dict):
        return ws
    ran = _run_argv(grant, ws, argv)
    try:
        out: dict[str, Any] = json.loads(ran["output"])
    except ValueError:
        return ran
    return out


def locate(grant: Any, work: str, target: str, go: bool = True) -> dict[str, Any]:
    """Where a passage is for the writer, and with ``go`` Word taken there (`docx locate`)."""
    return _json_run(grant, work, ["docx", "locate", target, *(["--go"] if go else [])])


def places(grant: Any, work: str, targets: list[str]) -> dict[str, Any]:
    """A list of places, rendered by the places page as one button each."""
    if not targets:
        raise ToolError("missing_arguments", missing=["targets"])
    out = _json_run(grant, work, ["docx", "places", *[str(t) for t in targets]])
    live = out.get("live")
    if out.get("status") != "ok" or not isinstance(live, dict):
        return out
    shown: dict[str, Any] = {**live["arguments"], "writer": out.get("writer", "")}
    if out.get("missing"):
        shown["missing"] = out["missing"]
    return shown


def change_card(grant: Any, work: str, cid: str) -> dict[str, Any]:
    """A proposed change as a card, rendered by the change page (Approve and Dismiss)."""
    ws = _work(grant, work)
    if isinstance(ws, dict):
        return ws
    try:
        one = change.status(ws.root, cid)["changes"][0]
    except plan.Refused as exc:
        raise ToolError(exc.reason, message=exc.message) from None
    return {"card": one["card"], "id": one["id"], "status": one["status"], "work": work}


def change_status(grant: Any, args: dict[str, Any]) -> dict[str, Any]:
    """The change page's check on load: the change's status now, not when the card was shown."""
    work, cid = str(args.get("work") or ""), str(args.get("change") or "")
    ws = _work(grant, work)
    if isinstance(ws, dict):
        return ws
    try:
        one = change.status(ws.root, cid)["changes"][0]
    except plan.Refused as exc:
        raise ToolError(exc.reason, message=exc.message) from None
    return {"id": one["id"], "status": one["status"], "work": work}


def change_approve(grant: Any, args: dict[str, Any]) -> dict[str, Any]:
    """The change page's Approve button: the id only. Applies it, then takes Word there."""
    work, cid = str(args.get("work") or ""), str(args.get("change") or "")
    ws = _work(grant, work)
    if isinstance(ws, dict):
        return ws
    try:
        out, code = change.approve(ws.root, cid)
    except plan.Refused as exc:
        raise ToolError(exc.reason, message=exc.message) from None
    except (OSError, ValueError, plan.PlanError) as exc:
        raise ToolError("error", message=str(exc)) from None
    if code != 0:
        raise ToolError(str(out.get("reason") or "refused"), message=str(out.get("message") or ""))
    locate = out.get("locate") or {}
    if live := locate.get("live"):  # the edit is in the open Word, not yet in the file
        from litcritic import word_live

        out["went"] = word_live.go(Path(live["doc"]), str(live["find_phrase"]))
    elif target := locate.get("target"):
        out["went"] = _json_run(grant, work, ["docx", "locate", "--quote", target, "--go"])
    return out


def change_dismiss(grant: Any, args: dict[str, Any]) -> dict[str, Any]:
    """The change page's Dismiss button."""
    work, cid = str(args.get("work") or ""), str(args.get("change") or "")
    ws = _work(grant, work)
    if isinstance(ws, dict):
        return ws
    try:
        return change.dismiss(ws.root, cid, str(args.get("reason") or ""))
    except plan.Refused as exc:
        raise ToolError(exc.reason, message=exc.message) from None
    except (OSError, ValueError, plan.PlanError) as exc:
        raise ToolError("error", message=str(exc)) from None


def plan_status(grant: Any, work: str) -> dict[str, Any]:
    """The work plan: parts, the active one, what comes next (`lc plan status`)."""
    ws = _work(grant, work)
    if isinstance(ws, dict):
        return ws
    try:
        return plan.status(ws.root)
    except (OSError, ValueError, plan.PlanError) as exc:
        raise ToolError("error", message=str(exc)) from None


SELECT_KEYS = ("at", "find_phrase", "find_phrase_across", "mode", "front")


def select(args: dict[str, Any]) -> dict[str, Any]:
    """The places page's button: doc-control's ``live.select`` in the open Word."""
    from litcritic import dc, word_live

    doc = str(args.get("doc") or "")
    if not doc or "/" in doc or "\\" in doc:
        raise ToolError("not_allowed", detail="doc is the open document's file name")
    request = {"doc": doc, **{k: args[k] for k in SELECT_KEYS if k in args}}
    try:
        return {"ok": True, "result": word_live.run("live.select", request)}
    except dc.DocError as exc:
        return {"ok": False, "error": {"code": exc.code, "message": exc.message}}


WORK_ARG = {"type": "string", "description": "the novel's title or folder name"}


def _opt(a: dict[str, Any], key: str, flag: str = "") -> list[str]:
    value = a.get(key)
    if not value:
        return []
    return [flag, str(value)] if flag else [str(value)]


def tools(grant: Any) -> list[Tool]:
    """The tools over the granted folders (``folders.Grant``); each task of the desktop plan
    adds its own."""
    return [
        Tool(
            "works",
            "List the writer's novels, most recently used first. " + WORK_HINT,
            lambda a: {"works": works_list(grant), "hint": ADD_FOLDER_HINT},
        ),
        Tool(
            "resume",
            "Open a novel: where it stands, the next step, and the guide for this chat. "
            + WORK_HINT
            + " Call it first in a chat, and again with the new name when the writer "
            "switches novels.",
            lambda a: resume(grant, str(a.get("work") or "")),
            {"work": {"type": "string", "description": "the novel's title or folder name"}},
        ),
        Tool(
            "show",
            "Read the novel: the table of contents, or the text of a chapter, scene or "
            "paragraph (c03, c03.s2, c03.s2.p4).",
            lambda a: run_lc(grant, str(a.get("work") or ""), ["show", *_opt(a, "unit")]),
            {"work": WORK_ARG, "unit": {"type": "string"}},
            ("work",),
        ),
        Tool(
            "find",
            "Find the paragraphs of the novel that contain all the words, or a quoted phrase.",
            lambda a: run_lc(
                grant,
                str(a.get("work") or ""),
                ["find", str(a.get("query") or ""), *_opt(a, "within", "--in")],
            ),
            {"work": WORK_ARG, "query": {"type": "string"}, "within": {"type": "string"}},
            ("work", "query"),
        ),
        Tool(
            "ask",
            "Answer a question about the novel from its Codex with a named question "
            "(run `codex questions` to list them); params are NAME=VALUE.",
            lambda a: run_lc(
                grant,
                str(a.get("work") or ""),
                [
                    "codex",
                    "ask",
                    str(a.get("question") or ""),
                    *[x for p in a.get("params") or [] for x in ("--param", str(p))],
                ],
            ),
            {
                "work": WORK_ARG,
                "question": {"type": "string"},
                "params": {"type": "array", "items": {"type": "string"}},
            },
            ("work", "question"),
        ),
        Tool(
            "run",
            "Run another literary-critic command on the novel (round, codex, index, "
            "context, locate, metrics, diff, report), as a list of arguments.",
            lambda a: run_lc(grant, str(a.get("work") or ""), a.get("command")),
            {"work": WORK_ARG, "command": {"type": "array", "items": {"type": "string"}}},
            ("work", "command"),
        ),
        Tool(
            "locate",
            "Take the writer to a passage in the open Word: a chapter (by its number), a "
            'scene, a paragraph anchor or a quote. Then say only "Done.".',
            lambda a: locate(
                grant, str(a.get("work") or ""), str(a.get("target") or ""), a.get("go", True)
            ),
            {"work": WORK_ARG, "target": {"type": "string"}, "go": {"type": "boolean"}},
            ("work", "target"),
        ),
        Tool(
            "places",
            "Show a list of places in the novel as buttons; each click takes Word there.",
            lambda a: places(grant, str(a.get("work") or ""), list(a.get("targets") or [])),
            {"work": WORK_ARG, "targets": {"type": "array", "items": {"type": "string"}}},
            ("work", "targets"),
            ui=PLACES_URI,
        ),
        Tool(
            "plan",
            "Show the work plan: the parts, the active one and what comes next. Say where "
            "the work stands from it.",
            lambda a: plan_status(grant, str(a.get("work") or "")),
            {"work": WORK_ARG},
            ("work",),
        ),
        Tool(
            "change_card",
            "Show a proposed change as a card with Approve and Dismiss buttons. Propose it "
            "first (`run` with `change propose`), then show it; the writer's click decides.",
            lambda a: change_card(grant, str(a.get("work") or ""), str(a.get("change") or "")),
            {"work": WORK_ARG, "change": {"type": "string", "description": "e.g. C1"}},
            ("work", "change"),
            ui=CHANGE_URI,
        ),
        Tool(
            "change_approve",
            "Approve a proposed change (used by the change card's button).",
            lambda a: change_approve(grant, a),
            {"work": WORK_ARG, "change": {"type": "string"}},
            ("work", "change"),
            app_only=True,
        ),
        Tool(
            "change_status",
            "A change's current status (used by the change card when it opens).",
            lambda a: change_status(grant, a),
            {"work": WORK_ARG, "change": {"type": "string"}},
            ("work", "change"),
            app_only=True,
        ),
        Tool(
            "change_dismiss",
            "Dismiss a proposed change (used by the change card's button).",
            lambda a: change_dismiss(grant, a),
            {"work": WORK_ARG, "change": {"type": "string"}, "reason": {"type": "string"}},
            ("work", "change"),
            app_only=True,
        ),
        Tool(
            "select",
            "Put Word's cursor on a place (used by the places buttons).",
            select,
            {
                "doc": {"type": "string"},
                "at": {"type": "string"},
                "find_phrase": {"type": "string"},
                "find_phrase_across": {"type": "boolean"},
                "mode": {"type": "string"},
                "front": {"type": "boolean"},
            },
            ("doc",),
        ),
        Tool(
            "setup",
            "Set up a novel the writer starts on for the first time (resume lists it under "
            "not_set_up): find its manuscript in the folder and prepare the work. Call it "
            "again on the same folder to record the writer's choices.",
            lambda a: setup_work(grant, a),
            {
                "folder": {"type": "string", "description": "the folder holding the novel"},
                "manuscript": {"type": "string", "description": "the writer's choice of file"},
                "prose_suggestions": {"enum": ["off", "minor", "on"]},
                "ack_ai_notice": {"type": "boolean"},
                "edit_in_place": {"type": "boolean"},
            },
            ("folder",),
        ),
        Tool(
            "add_folder",
            "Open the folder picker on the writer's screen to add the folder that holds a "
            "novel the other tools cannot find. Offer it first; the writer's choice is the "
            "permission.",
            _add_folder(grant),
        ),
    ]


def _cmd(args: Any) -> int:
    from litcritic.folders import Grant  # folders imports ToolError from here

    Server(tools(Grant(args.folders)), log=sys.stderr).serve(sys.stdin, sys.stdout)
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("mcp", help="serve the tools to the Claude desktop app (stdio)")
    p.add_argument("folders", nargs="*", help="folders that hold the novels (the install grant)")
    p.set_defaults(func=_cmd)
