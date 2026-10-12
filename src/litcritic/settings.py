"""Per-writer settings kept in the workspace's ``analysis/profile.toml``.

``prose_suggestions`` (default off): whether the assistant may propose wording
for the novel. Turning it on needs the writer to have read the AI-text notice
(D-22); the moment they acknowledged it is recorded as ``ai_notice_ack``.
"""

from __future__ import annotations

import re
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROFILE = Path("analysis") / "profile.toml"
KEYS = ("prose_suggestions", "ai_notice_ack", "edit_in_place")

AI_NOTICE = {
    "en": (
        "Before you turn on wording suggestions, please know:\n"
        "- Text written by an AI may later be identified as AI-written, by detection "
        "tools and by watermarks some providers add.\n"
        "- Publishers, agents and contests may ask you to disclose AI-written text, "
        "or may not accept it. Authorship and rights questions can follow.\n"
        "- We recommend that you do the writing: the tool shows what to change, where "
        "and why, and you choose the words.\n"
        "If you still want suggested wording, that is your choice, and it can be turned "
        "off at any time."
    ),
    "es": (
        "Antes de activar las propuestas de redacción, conviene saber:\n"
        "- Un texto escrito por una IA puede identificarse después como tal, con "
        "herramientas de detección y con marcas de agua que añaden algunos proveedores.\n"
        "- Editoriales, agentes y concursos pueden pedir que declares el texto escrito "
        "por IA, o no aceptarlo. Pueden surgir dudas de autoría y derechos.\n"
        "- Te recomendamos escribir tú: la herramienta te muestra qué cambiar, dónde y "
        "por qué, y tú eliges las palabras.\n"
        "Si aun así quieres propuestas de redacción, es tu decisión, y puedes "
        "desactivarlas cuando quieras."
    ),
}


class NoticeRequired(Exception):
    """Turning prose suggestions on needs the AI-text notice acknowledged."""


class SettingsError(Exception):
    """The profile cannot be read, or the setting could not be written safely."""


NEEDS_ACK = "turning prose suggestions on needs --ack-ai-notice"


def check(prose: str, ack: bool) -> None:
    """Raise unless the requested change is allowed (``prose`` is "on", "off" or "")."""
    if prose == "on" and not ack:
        raise NoticeRequired(NEEDS_ACK)
    if ack and prose != "on":
        raise SettingsError("--ack-ai-notice goes with --prose-suggestions on")


def notice(lang: str) -> str:
    return AI_NOTICE.get(lang, AI_NOTICE["en"])


def _read(ws_root: Path) -> dict[str, Any]:
    f = ws_root / PROFILE
    try:
        return tomllib.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    except (OSError, ValueError) as exc:
        raise SettingsError(f"{PROFILE} cannot be read: {exc}") from exc


def _settings(profile: dict[str, Any]) -> dict[str, Any]:
    ack = profile.get("ai_notice_ack")
    ack = ack if isinstance(ack, str) and ack else ""
    edit = profile.get("edit_in_place")
    return {
        # On only when written as a real boolean true and with the notice acknowledged.
        "prose_suggestions": profile.get("prose_suggestions") is True and bool(ack),
        "ai_notice_ack": ack,
        # The writer's answer to "may approved changes go into the file?"; None = not asked.
        "edit_in_place": edit if isinstance(edit, bool) else None,
    }


def load(ws_root: Path) -> dict[str, Any]:
    return _settings(_read(ws_root))


def _toml(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


TABLE = re.compile(r"\s*\[\[?\s*[\w.\"' -]+\s*\]\]?\s*(#.*)?$")


def _write(ws_root: Path, values: dict[str, object], language: str) -> None:
    """Set top-level keys in profile.toml, keeping every other line as it is. A new
    profile gets the required ``mode`` and ``language`` too."""
    f = ws_root / PROFILE
    lines = (
        f.read_text(encoding="utf-8").splitlines()
        if f.is_file()
        else [
            'mode = "revision"',
            f"language = {_toml(language)}",
        ]
    )
    first_table = next((i for i, ln in enumerate(lines) if TABLE.match(ln)), len(lines))
    key = re.compile(r"\s*(" + "|".join(values) + r")\s*=")
    head = [ln for ln in lines[:first_table] if not key.match(ln)]
    new = [f"{k} = {_toml(v)}" for k, v in values.items() if v != ""]
    text = "\n".join([*head, *new, *lines[first_table:]]) + "\n"
    try:
        written = tomllib.loads(text)
    except ValueError as exc:
        raise SettingsError(f"{PROFILE} would not parse; edit it by hand: {exc}") from exc
    if any(written.get(k, "") != v for k, v in values.items()):
        raise SettingsError(f"{PROFILE} has a layout this tool cannot edit safely; edit it by hand")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")


def set_prose_suggestions(
    ws_root: Path, on: bool, ack: bool = False, language: str = "en"
) -> dict[str, Any]:
    """Turn prose suggestions on (needs ``ack``) or off; returns the settings."""
    check("on" if on else "off", ack if on else False)
    current = load(ws_root)
    if on == current["prose_suggestions"] and on == bool(_read(ws_root).get("prose_suggestions")):
        return current
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if on else ""
    _write(ws_root, {"prose_suggestions": on, "ai_notice_ack": stamp}, language)
    return load(ws_root)


def set_edit_in_place(ws_root: Path, on: bool, language: str = "en") -> dict[str, Any]:
    """Record whether approved changes may be applied to the writer's file."""
    if load(ws_root)["edit_in_place"] is not on:
        _write(ws_root, {"edit_in_place": on}, language)
    return load(ws_root)
