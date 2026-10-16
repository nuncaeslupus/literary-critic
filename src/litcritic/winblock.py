"""Windows refusing a save, told apart and explained to the writer in clicks.

Two Windows faults look alike in an error message and need opposite fixes:

- **blocked**: access denied (``WinError 5``). On a writer's PC this is usually Windows
  Security's ransomware protection ("Controlled folder access"), which stops programs it
  does not know from writing in Documents, Desktop, Pictures and the like. The program
  must be allowed once in Windows Security (again if an update moves it).
- **open**: a sharing violation (``WinError 32``/``33``): the file is open in another
  program, usually Word. Closing it is enough.

A bare ``Errno 13`` (what ``open()`` raises on Windows for both) is **blocked_or_open**.
``advice`` takes an exception or an error text (doc-control's messages carry the Python
error text) and returns ``{"windows_block": {...}}`` with a ``say`` for the chat, or ``{}``
when it is not one of these faults.
"""

from __future__ import annotations

import re
import sys
from pathlib import PureWindowsPath
from typing import Any

ALLOW_STEPS = (
    "Windows Security > Virus & threat protection > Manage ransomware protection > "
    "Allow an app through Controlled folder access > Add an allowed app > "
    "Recently blocked apps"
)
# Folders Controlled folder access protects by default (English and Spanish names).
PROTECTED = {
    "documents",
    "desktop",
    "pictures",
    "videos",
    "music",
    "favorites",
    "documentos",
    "escritorio",
    "imágenes",
    "vídeos",
    "música",
    "favoritos",
}
_BLOCKED = re.compile(r"\[WinError 5\]|Access is denied|Acceso denegado", re.I)
_OPEN = re.compile(
    r"\[WinError 3[23]\]|being used by another process|utilizado por otro proceso", re.I
)
_EITHER = re.compile(r"\[Errno 13\]|Permission denied|Permiso denegado", re.I)
_PATH = re.compile(r"'([A-Za-z]:\\[^']+|[A-Za-z]:/[^']+)'")

SAY = {
    "blocked": (
        "Windows Security stopped {who} from saving in this folder (ransomware "
        "protection). Nothing is lost. To allow it, open {steps}, and allow {program}. "
        "It may be needed once for literary-critic and once for doc-control, and again "
        "after an update. Then try again."
    ),
    "open": (
        "The file is open in another program, usually Word, so it could not be saved. "
        "Close it there, then try again."
    ),
    "blocked_or_open": (
        "Windows did not let {who} save. If the file is open in Word, close it and try "
        "again. If it is not, Windows Security (ransomware protection) is blocking it: "
        "open {steps}, and allow {program}. Then try again."
    ),
}


def kind(problem: BaseException | str, platform: str = sys.platform) -> str | None:
    """``blocked``, ``open``, ``blocked_or_open``, or None when it is not a Windows refusal."""
    if isinstance(problem, BaseException):
        winerror = getattr(problem, "winerror", None)
        if winerror == 5:
            return "blocked"
        if winerror in (32, 33):
            return "open"
        if isinstance(problem, PermissionError) and platform == "win32":
            return "blocked_or_open"
        if isinstance(problem, OSError):  # its codes said it all; its text is the OS's
            return None
        problem = str(problem)
    if _OPEN.search(problem):
        return "open"
    if _BLOCKED.search(problem):
        return "blocked"
    if _EITHER.search(problem) and (platform == "win32" or "WinError" in problem):
        return "blocked_or_open"
    return None


def _path(problem: BaseException | str) -> str:
    name = getattr(problem, "filename", None)
    if name:
        return str(name)
    found = _PATH.search(str(problem))
    return found.group(1) if found else ""


def protected(path: str) -> bool:
    """The path is inside a folder Controlled folder access protects by default."""
    return any(part.lower() in PROTECTED for part in PureWindowsPath(path).parts[:-1])


def advice(
    problem: BaseException | str,
    program: str | None = None,
    who: str = "literary-critic",
    platform: str = sys.platform,
) -> dict[str, Any]:
    """``{"windows_block": {kind, path, protected_folder, program, say}}``, or ``{}``."""
    found = kind(problem, platform)
    if found is None:
        return {}
    program = program or sys.executable
    path = _path(problem)
    shown = f"the entry for {who} ({program})"
    block: dict[str, Any] = {
        "kind": found,
        "path": path,
        "protected_folder": protected(path) if path else None,
        "program": program,
        "say": SAY[found].format(who=who, steps=ALLOW_STEPS, program=shown),
    }
    return {"windows_block": block}
