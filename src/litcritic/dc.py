"""The one door to doc-control: every document read or write goes through here.

doc-control (PyPI ``doc-control``, stdlib only) owns the generic primitives —
reading, segmenting, diffing, locating and editing Word documents as tracked
changes. This module is the only place that imports it, so a change in its API
touches one file. Calls run in-process with doc-control's own request schemas.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

API_MAJOR = 1  # the doc-control API major version this code was written against
INSTALL_HINT = "install a doc-control release with API 1.x: pip install 'doc-control>=0.0.1,<0.1'"


class DocError(Exception):
    """An error envelope from doc-control, or doc-control missing or incompatible."""

    def __init__(
        self, code: str, message: str, hint: str = "", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(f"{message} ({hint})" if hint else message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details or {}  # doc-control's ``error.details`` (candidates, paragraph…)


_checked = False


def _missing() -> DocError:
    return DocError("NOT_INSTALLED", "doc-control is not installed", INSTALL_HINT)


def _execute(op: str, request: dict[str, Any]) -> dict[str, Any]:
    try:
        from doc_control.cli import execute
        from doc_control.registry import load_operations
    except ImportError as exc:
        raise _missing() from exc
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

    Warnings, when doc-control sends any, come back under ``result["_warnings"]``;
    the cursor of a capped list, when more follows, under ``result["_next"]``.
    """
    check()
    envelope = _execute(op, request)
    if not envelope.get("ok"):
        err = envelope.get("error", {})
        raise DocError(
            err.get("code", "INTERNAL"),
            err.get("message", op),
            err.get("hint", ""),
            err.get("details") or {},
        )
    result: dict[str, Any] = dict(envelope.get("result") or {})
    if envelope.get("warnings"):
        result["_warnings"] = envelope["warnings"]
    if envelope.get("next"):
        result["_next"] = envelope["next"]
    return result


class Document:
    """A document held open for several operations (doc-control's in-process API).

    doc-control parses the file once and reuses the parse for every read until the
    file changes. Results are whole: no response cap, no cursor to follow.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._doc: Any = None

    def _handle(self) -> Any:
        if self._doc is None:
            check()
            try:
                from doc_control import api
            except ImportError as exc:
                raise _missing() from exc
            self._doc = api.open(self.path)
        return self._doc

    def run(self, op: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
        """The result of ``op`` on this document (``doc`` filled in); raises ``DocError``."""
        with _errors():
            result: dict[str, Any] = self._handle().run(op, request or {})
        return result

    def paragraphs(self, *, normalized: bool = False, pages: bool = False) -> list[dict[str, Any]]:
        """Every paragraph with its address (``at``), text, style and layout facts."""
        with _errors():
            rows: list[dict[str, Any]] = self._handle().paragraphs(
                normalized=normalized, pages=pages
            )
        return rows

    def close(self) -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None

    def __enter__(self) -> Document:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@contextmanager
def _errors() -> Iterator[None]:
    """doc-control's exceptions as ``DocError``."""
    try:
        from doc_control.errors import HINTS, DocControlError
    except ImportError as exc:
        raise _missing() from exc
    try:
        yield
    except DocControlError as exc:
        hint = HINTS.get(exc.code, "")
        raise DocError(str(exc.code), exc.message, hint, dict(exc.details)) from exc


def open(path: str | Path) -> Document:
    """Open ``path`` for several doc-control operations; use it as a context manager."""
    return Document(path)
