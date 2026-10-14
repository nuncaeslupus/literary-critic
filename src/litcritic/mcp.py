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

import json
import sys
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, TextIO

from litcritic import __version__

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


def tools(grant: Any) -> list[Tool]:
    """The tools over the granted folders; each task of the desktop plan adds its own."""
    return []


def _cmd(args: Any) -> int:
    from litcritic.folders import Grant  # folders imports ToolError from here

    Server(tools(Grant(args.folders)), log=sys.stderr).serve(sys.stdin, sys.stdout)
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("mcp", help="serve the tools to the Claude desktop app (stdio)")
    p.add_argument("folders", nargs="*", help="folders that hold the novels (the install grant)")
    p.set_defaults(func=_cmd)
