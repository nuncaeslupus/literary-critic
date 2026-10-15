"""The one door to doc-control: every document read or write goes through here.

doc-control (PyPI ``doc-control``, stdlib only) owns the generic primitives —
reading Word documents (and plain text, Markdown or OpenDocument text as if
they were one),
segmenting, diffing, locating and editing Word documents as tracked changes.
This module is the only place that imports it, so a change in its API touches
one file. Calls run in-process with doc-control's own request schemas.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

API_MAJOR = 1  # the doc-control API major version this code was written against
MIN_VERSION = (0, 7, 0)  # resource.action operation names
INSTALL_HINT = "install doc-control 0.7 (API 1.x): pip install 'doc-control>=0.7,<0.8'"


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
    """Refuse a doc-control whose API major version this code does not know, or one
    older than ``MIN_VERSION``."""
    global _checked
    if _checked:
        return
    envelope = _execute("capabilities", {})
    api = str(envelope.get("api", ""))
    if api.split(".")[0] != str(API_MAJOR):
        raise DocError("API_UNSUPPORTED", f"doc-control API {api} is not supported", INSTALL_HINT)
    version = str((envelope.get("result") or {}).get("version", ""))
    parts = tuple(int(n) for n in re.findall(r"\d+", version)[:3])
    if parts and parts < MIN_VERSION:
        raise DocError("API_UNSUPPORTED", f"doc-control {version} is too old", INSTALL_HINT)
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

    def __init__(self, path: str | Path, text_mode: str | None = None) -> None:
        self.path = str(path)
        self.text_mode = text_mode  # how a .txt is cut into paragraphs; None: doc-control's auto
        self._doc: Any = None

    def _handle(self) -> Any:
        if self._doc is None:
            check()
            try:
                from doc_control import api
            except ImportError as exc:
                raise _missing() from exc
            with _errors():
                self._doc = api.open(self.path, text_mode=self.text_mode)
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

    def source(self) -> dict[str, Any]:
        """How doc-control read a ``.txt``, ``.md`` or ``.odt`` file: ``format`` and, for
        text, ``encoding`` and ``mode`` (``blocks``, ``lines`` or ``markdown``); empty
        for a Word document."""
        with _errors():
            reply = self._handle().reply("doc.info")
        return dict((reply.doc or {}).get("source") or {})

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


def open(path: str | Path, text_mode: str | None = None) -> Document:
    """Open ``path`` for several doc-control operations; use it as a context manager.

    ``text_mode`` (``auto``, ``blocks`` or ``lines``) is how doc-control cuts a ``.txt``
    into paragraphs; None leaves doc-control's default (``auto``).
    """
    return Document(path, text_mode)
