"""The extension's entry point: start ``lc mcp`` over the folders the writer granted.

The app runs it with uv in the unpacked bundle, so the bundled project is already
installed. A newer runtime staged under ``%LOCALAPPDATA%\\literary-critic\\runtime\\X.Y.Z``
and named in ``runtime\\state.json`` runs instead. A runtime that exits with an error
within ``QUICK_EXIT`` seconds failed to start; after ``MAX_FAILURES`` of those it is
marked bad, and the next start runs the previous one or the bundled one. Two runtimes are
kept. This file runs before any runtime is chosen, so it imports only the standard
library until it settles on the bundled one.

An optional folder setting the writer left empty can reach us as its unexpanded
placeholder, which is not a folder and is dropped.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable
from pathlib import Path

QUICK_EXIT = 10.0  # seconds; an error exit sooner than this is a failed start
MAX_FAILURES = 2
HERE = Path(__file__).resolve().parent
VERSION = re.compile(r"\d+\.\d+\.\d+")


def folders(argv: list[str]) -> list[str]:
    return [a for a in argv if a.strip() and not a.startswith("${")]


def runtime_root() -> Path:
    if os.environ.get("LC_RUNTIME_DIR"):
        return Path(os.environ["LC_RUNTIME_DIR"])
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "literary-critic" / "runtime"


def key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def python_of(runtime: Path) -> Path | None:
    for exe in (runtime / "Scripts" / "python.exe", runtime / "bin" / "python"):
        if exe.is_file():
            return exe
    return None


def bundled_version() -> str:
    try:
        with (HERE / "pyproject.toml").open("rb") as f:
            return str(tomllib.load(f)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0.0.0"


def load(root: Path) -> dict:
    try:
        state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def save(root: Path, state: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / "state.json.tmp"
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(root / "state.json")


def candidates(state: dict) -> list[str]:
    bad = set(state.get("bad") or [])
    named = (state.get("current"), state.get("previous"))
    return [v for v in named if isinstance(v, str) and VERSION.fullmatch(v) and v not in bad]


def choose(state: dict, root: Path, bundled: str) -> str | None:
    """The staged version to run, or None for the bundled runtime."""
    for v in candidates(state):
        if key(v) > key(bundled) and python_of(root / v):
            return v
    return None


def record(state: dict, version: str, seconds: float, code: int) -> None:
    failures = state.setdefault("failures", {})
    if code == 0 or seconds >= QUICK_EXIT:
        failures.pop(version, None)
        return
    failures[version] = failures.get(version, 0) + 1
    bad = state.setdefault("bad", [])
    if failures[version] >= MAX_FAILURES and version not in bad:
        bad.append(version)


def prune(root: Path, state: dict) -> None:
    """Keep current and previous, and anything newer that staging may still be building."""
    keep = candidates(state)
    if not keep:
        return
    floor = min(key(v) for v in keep)
    for d in root.iterdir() if root.is_dir() else ():
        old = VERSION.fullmatch(d.name) and d.name not in keep and d.is_dir()
        if old and (d.name in (state.get("bad") or []) or key(d.name) < floor):
            shutil.rmtree(d, ignore_errors=True)  # a second server may still hold it


def serve_bundled(args: list[str]) -> int:
    from litcritic.cli import main as lc  # the bundled environment, synced by the app

    return lc(["mcp", *args])


def main(
    argv: list[str],
    *,
    call: Callable[[list[str]], int] = subprocess.call,
    serve: Callable[[list[str]], int] = serve_bundled,
    clock: Callable[[], float] = time.monotonic,
    bundled: str | None = None,
) -> int:
    args = folders(argv)
    root = runtime_root()
    state = load(root)
    prune(root, state)
    version = choose(state, root, bundled or bundled_version())
    if version is None:
        print("launch: bundled runtime", file=sys.stderr)
        return serve(args)
    print(f"launch: runtime {version}", file=sys.stderr)
    python = python_of(root / version)
    start = clock()
    code = call([str(python), "-m", "litcritic", "mcp", *args])
    state = load(root)  # staging may have written while the server ran
    record(state, version, clock() - start, code)
    save(root, state)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
