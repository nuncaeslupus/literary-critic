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
KEYS = ("prose_suggestions", "ai_notice_ack")

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


def notice(lang: str) -> str:
    return AI_NOTICE.get(lang, AI_NOTICE["en"])


def load(ws_root: Path) -> dict[str, Any]:
    f = ws_root / PROFILE
    profile = tomllib.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    return {
        "prose_suggestions": bool(profile.get("prose_suggestions", False)),
        "ai_notice_ack": str(profile.get("ai_notice_ack", "")),
    }


def _toml(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _write(ws_root: Path, values: dict[str, object]) -> None:
    """Set top-level keys in profile.toml, keeping every other line as it is."""
    f = ws_root / PROFILE
    lines = f.read_text(encoding="utf-8").splitlines() if f.is_file() else []
    first_table = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("[")), len(lines))
    key = re.compile(r"\s*(" + "|".join(KEYS) + r")\s*=")
    head = [ln for ln in lines[:first_table] if not key.match(ln)]
    new = [f"{k} = {_toml(v)}" for k, v in values.items() if v != ""]
    text = "\n".join([*head, *new, *lines[first_table:]]) + "\n"
    tomllib.loads(text)  # never leave a profile that does not parse
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")


def set_prose_suggestions(ws_root: Path, on: bool, ack: bool = False) -> dict[str, Any]:
    """Turn prose suggestions on (needs ``ack``) or off; returns the settings."""
    current = load(ws_root)
    if on and not ack:
        raise NoticeRequired("turning prose suggestions on needs --ack-ai-notice")
    if on == current["prose_suggestions"] and (not on or current["ai_notice_ack"]):
        return current
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if on else ""
    _write(ws_root, {"prose_suggestions": on, "ai_notice_ack": stamp})
    return load(ws_root)
