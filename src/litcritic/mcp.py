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

from litcritic import __version__, rounds, settings, structure
from litcritic.workspace import Workspace, repo_root

PROTOCOL_VERSION = "2025-06-18"  # answered when the client names none
SERVER_NAME = "literary-critic"

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

    def listing(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "object", "properties": self.properties}
        if self.required:
            schema["required"] = list(self.required)
        return {"name": self.name, "description": self.description, "inputSchema": schema}


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
                "capabilities": {"tools": {}},
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
        return _result(msg_id, {"content": [{"type": "text", "text": text}], "isError": is_error})

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
NEXT_STEPS = {
    "setup": "Bring the manuscript in: find the novel's file and set it up (05-setup.md).",
    "index": "Finish indexing the novel, so questions are answered from the Codex "
    "(20-codex-items.md).",
    "round": "Continue the open revision round with the next pending action (60-rounds.md).",
    "overview": "Offer an overview: what works and the three biggest problems "
    "(30-orientation.md, 40-checks.md).",
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
    notes = sorted((ws.root / "log").glob("*.md")) if (ws.root / "log").is_dir() else []
    out["last_notes"] = notes[-1].name if notes else None
    if out["draft"] is None:
        step = "setup"
    elif out["index"] is None or out["index"]["todo"]:
        step = "index"
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
        return {
            "not_found": work,
            "works": works_list(grant),
            "hint": ADD_FOLDER_HINT,
        }
    if len(hits) > 1:
        return {"ambiguous": work, "works": [_entry(ws) for ws in hits]}
    ws = hits[0]
    _touch(ws)
    return {"work": state(ws), "guide": guide()}


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
