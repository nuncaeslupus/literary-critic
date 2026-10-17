"""What the Claude desktop app has installed besides this extension, read from its own files.

Only a standalone doc-control matters: this extension already includes it, and a second
copy lets the chat change the manuscript without the writer's approval (release D-7: it is
reported, not blocked). Every read is best effort: an unreadable file reports nothing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

APP_DIR_ENV = "LITCRITIC_CLAUDE_DIR"
INSTALLATIONS = "extensions-installations.json"
SETTINGS_DIR = "Claude Extensions Settings"
CONFIG = "claude_desktop_config.json"
SELF = "literary-critic"
SAY = (
    "You also have a separate doc-control extension. This tool already includes it; "
    "please remove it in Settings → Extensions so every change goes through your approval."
)


def app_dirs() -> list[Path]:
    """Where the app keeps its files: the override, else the usual place and, on Windows,
    the packaged (MSIX) app's redirected copy of it."""
    env = os.environ.get(APP_DIR_ENV)
    if env:
        return [Path(env).expanduser()]
    if os.name == "nt":
        dirs = []
        if os.environ.get("APPDATA"):
            dirs.append(Path(os.environ["APPDATA"]) / "Claude")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs += sorted((Path(local) / "Packages").glob("Claude_*/LocalCache/Roaming/Claude"))
        return dirs
    if sys.platform == "darwin":
        return [Path.home() / "Library" / "Application Support" / "Claude"]
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return [Path(base) / "Claude"]


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _is_doc_control(*names: Any) -> bool:
    for name in names:
        flat = str(name or "").lower().replace("_", "-").replace(" ", "-")
        if "doc-control" in flat and SELF not in flat:
            return True
    return False


def _entries(data: Any) -> list[tuple[str, dict[str, Any]]]:
    """``(id, entry)`` pairs, whether the file maps ids to entries or lists them."""
    if isinstance(data, dict):
        data = data.get("extensions", data)
    if isinstance(data, dict):
        return [(str(k), v) for k, v in data.items() if isinstance(v, dict)]
    if isinstance(data, list):
        return [(str(v.get("id", "")), v) for v in data if isinstance(v, dict)]
    return []


def _enabled(app: Path, ext_id: str, entry: dict[str, Any]) -> bool:
    for key in ("isEnabled", "enabled"):
        if isinstance(entry.get(key), bool):
            return bool(entry[key])
    settings = _read(app / SETTINGS_DIR / f"{ext_id}.json")
    if isinstance(settings, dict) and isinstance(settings.get("isEnabled"), bool):
        return bool(settings["isEnabled"])
    return True


def _extension(app: Path) -> dict[str, str] | None:
    for ext_id, entry in _entries(_read(app / INSTALLATIONS)):
        manifest = entry.get("manifest")
        manifest = manifest if isinstance(manifest, dict) else {}
        name = manifest.get("name") or entry.get("name") or ext_id
        if _is_doc_control(ext_id, name) and _enabled(app, ext_id, entry):
            return {"kind": "extension", "name": str(name)}
    return None


def _config_entry(app: Path) -> dict[str, str] | None:
    data = _read(app / CONFIG)
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return None
    for name, spec in servers.items():
        spec = spec if isinstance(spec, dict) else {}
        args = spec.get("args")
        args = args if isinstance(args, list) else []
        if SELF not in str(name).lower() and _is_doc_control(name, spec.get("command"), *args):
            return {"kind": "config", "name": str(name)}
    return None


def other_doc_control() -> dict[str, str] | None:
    """``{kind, name, say}`` for an enabled doc-control extension or a config entry that
    runs doc-control, else None."""
    for app in app_dirs():
        found = _extension(app) or _config_entry(app)
        if found:
            return {**found, "say": SAY}
    return None
