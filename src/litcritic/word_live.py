"""The one adapter to the writer's open Word (see ``docs/word-control-interface.md``).

Every operation takes and returns a JSON object. Two backends:

- **manual** (default, today): returns ``{"status": "manual", "how": "computer-use",
  "steps": [...], "writer": "..."}`` — the steps the agent performs with computer
  use, and the plain instruction for the writer when computer use is not available;
- **command**: when ``$LITCRITIC_WORD_CONTROL`` names the Word-control extension's
  command, it runs ``<command> <operation>`` with the request on stdin and returns
  the JSON it prints. Nothing else in literary-critic changes when it arrives.

Edits never go through Word itself today: ``lc docx edits`` / ``rename`` change the
file while Word has it closed, and this adapter only saves, closes, reopens and
brings Word to the passage.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from litcritic import locate

ENV = "LITCRITIC_WORD_CONTROL"
TIMEOUT = 60

# operation -> (request keys, response keys when the extension did it)
OPERATIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "locate": (("document", "find"), ("status", "found")),
    "apply_edits": (("document", "edits"), ("status", "applied", "skipped")),
    "rename": (("document", "old", "new", "case_sensitive"), ("status", "count")),
    "save": (("document",), ("status",)),
    "close": (("document", "save"), ("status",)),
    "reopen": (("document",), ("status",)),
    "selection": (("document",), ("status", "text", "find")),
}
MANUAL_KEYS = ("status", "how", "steps", "writer")
OPTIONAL = {"locate": ("locator", "language")}  # request keys that may be absent


class WordLiveError(Exception):
    """A request the adapter cannot send (unknown operation, missing keys)."""


def _keys(platform: str) -> tuple[str, str]:
    """(modifier key name, app switch hint) for the writer's system."""
    if platform == "darwin":
        return "Cmd", "click Word in the Dock"
    return "Ctrl", "click Word in the taskbar"


def _name(payload: dict[str, Any]) -> str:
    return Path(str(payload.get("document", "the document"))).name


def _where(locator: Any, lang: str) -> str:
    """The writer's locator line (as everywhere else in the tool), or "" when incomplete."""
    if not isinstance(locator, dict):
        return ""
    needed = ("chapter", "first_words", "last_words")
    if not all(isinstance(locator.get(k), str) and locator[k] for k in needed):
        return ""
    try:
        return locate.describe(locate.from_where({"anchor": "", **locator}), lang)
    except (TypeError, ValueError):
        return ""


def manual(op: str, payload: dict[str, Any], platform: str = sys.platform) -> dict[str, Any]:
    """What the agent does with computer use, and what to tell the writer otherwise."""
    mod, switch = _keys(platform)
    name = _name(payload)
    steps: list[str]
    if op == "locate":
        steps = [
            f"Bring Word to the front with {name} open ({switch}).",
            f"Press {mod}+F, type exactly: {payload['find']}",
            "Press Enter: Word selects the passage. Close the search box; leave the "
            "selection for the writer to see.",
            "If nothing is found, tell the writer where it is in plain words instead.",
        ]
        lang = str(payload.get("language") or "en")
        where = _where(payload.get("locator"), lang)
        if lang == "es":
            writer = f"En {name}: {where}." if where else f"En {name}, busca «{payload['find']}»."
        else:
            writer = (
                f"In {name}: {where}." if where else f"In {name}, look for “{payload['find']}”."
            )
    elif op in ("apply_edits", "rename"):
        steps = [
            f"Run `lc docx status` first. If {name} is open in Word, save and close it "
            f"({mod}+S, then {mod}+W), or ask the writer to.",
            "Apply the change with `lc docx edits` or `lc docx rename`.",
            f"Reopen {name} in Word (double-click it in its folder); the change shows "
            "as a tracked change the writer can accept or reject.",
        ]
        writer = f"Please save and close {name} in Word; I will tell you when to open it again."
    elif op == "save":
        steps = [f"Bring Word to the front ({switch}) and press {mod}+S."]
        writer = f"Please save {name} in Word ({mod}+S)."
    elif op == "close":
        verb = f"press {mod}+S, then {mod}+W" if payload.get("save") else f"press {mod}+W"
        steps = [
            f"Bring Word to the front ({switch}) and {verb}.",
            "If Word asks whether to save, answer as the writer decided; never discard "
            "their unsaved work without asking.",
        ]
        writer = (
            f"Please save and close {name} in Word."
            if payload.get("save")
            else f"Please close {name} in Word; when it asks, choose not to save."
        )
    elif op == "reopen":
        steps = [f"Open {name} from its folder (double-click it) and bring Word to the front."]
        writer = f"You can open {name} again now."
    else:  # selection
        steps = [
            "Bring Word to the front and read the selected text from the screen.",
            "Pass the first words to `lc docx locate` to find it in the document.",
        ]
        writer = "Please copy the passage you mean and paste it here."
    return {"status": "manual", "how": "computer-use", "steps": steps, "writer": writer}


def _split(command: str) -> list[str]:
    """The command's words; Windows paths keep their backslashes."""
    if os.name != "nt":
        return shlex.split(command)
    return [w.strip('"') for w in shlex.split(command, posix=False)]


def _command(op: str, payload: dict[str, Any], command: str) -> dict[str, Any]:
    try:
        done = subprocess.run(
            [*_split(command), op],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=TIMEOUT,
            check=False,
        )
        out = json.loads(done.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {"status": "error", "message": f"Word-control did not answer: {exc}"}
    if not isinstance(out, dict):
        return {"status": "error", "message": "Word-control answered with something else"}
    return out


def call(op: str, payload: dict[str, Any], platform: str = sys.platform) -> dict[str, Any]:
    """Run one operation; falls back to manual steps when the extension is not there
    or fails."""
    if op not in OPERATIONS:
        raise WordLiveError(f"unknown operation {op!r}; one of {', '.join(OPERATIONS)}")
    request, _ = OPERATIONS[op]
    missing = [k for k in request if k not in payload and k not in OPTIONAL.get(op, ())]
    if missing:
        raise WordLiveError(f"{op} needs {', '.join(missing)}")
    if payload.get("locator") is not None and not isinstance(payload["locator"], dict):
        raise WordLiveError("locator must be the object `lc docx locate` prints")
    command = os.environ.get(ENV, "").strip()
    if command:
        out = _command(op, payload, command)
        if out.get("status") not in ("error", None):
            return out
        return {**manual(op, payload, platform), "extension_error": out.get("message", "")}
    return manual(op, payload, platform)


def _cmd(args: Any) -> int:
    try:
        raw = args.payload
        inline = raw.lstrip().startswith(("{", "["))
        payload = json.loads(raw if inline else Path(raw).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("the payload must be a JSON object")
        out = call(args.op, payload)
    except (WordLiveError, ValueError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if out.get("status") == "refused" else 0


def register(sub: Any) -> None:
    p = sub.add_parser("word", help="act on the open Word (computer-use steps today)")
    p.add_argument("op", choices=list(OPERATIONS))
    p.add_argument("--payload", required=True, help="the request: JSON, or a JSON file")
    p.set_defaults(func=_cmd)
