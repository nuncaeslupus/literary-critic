"""The one door to doc-control: every document read or write goes through here.

doc-control (PyPI ``doc-control``, stdlib only) owns the generic primitives —
reading, segmenting, diffing, locating and editing Word documents as tracked
changes. This module is the only place that imports it, so a change in its API
touches one file. Calls run in-process with doc-control's own request schemas.
"""

from __future__ import annotations

from typing import Any

API_MAJOR = 1  # the doc-control API major version this code was written against
INSTALL_HINT = "install a doc-control release with API 1.x: pip install 'doc-control>=0.0.1,<0.1'"


class DocError(Exception):
    """An error envelope from doc-control, or doc-control missing or incompatible."""

    def __init__(self, code: str, message: str, hint: str = "") -> None:
        super().__init__(f"{message} ({hint})" if hint else message)
        self.code = code
        self.message = message
        self.hint = hint


_checked = False


def _execute(op: str, request: dict[str, Any]) -> dict[str, Any]:
    try:
        from doc_control.cli import execute
        from doc_control.registry import load_operations
    except ImportError as exc:
        raise DocError("NOT_INSTALLED", "doc-control is not installed", INSTALL_HINT) from exc
    envelope, _ = execute(load_operations(), op, request)
    return envelope


def check() -> None:
    """Refuse a doc-control whose API major version this code does not know."""
    global _checked
    if _checked:
        return
    envelope = _execute("capabilities", {})
    api = str(envelope.get("api", ""))
    if api.split(".")[0] != str(API_MAJOR):
        raise DocError("API_UNSUPPORTED", f"doc-control API {api} is not supported", INSTALL_HINT)
    _checked = True


def run(op: str, request: dict[str, Any]) -> dict[str, Any]:
    """Run one doc-control operation; return its ``result`` or raise ``DocError``.

    Warnings, when doc-control sends any, come back under ``result["_warnings"]``.
    """
    check()
    envelope = _execute(op, request)
    if not envelope.get("ok"):
        err = envelope.get("error", {})
        raise DocError(err.get("code", "INTERNAL"), err.get("message", op), err.get("hint", ""))
    result: dict[str, Any] = dict(envelope.get("result") or {})
    if envelope.get("warnings"):
        result["_warnings"] = envelope["warnings"]
    return result
