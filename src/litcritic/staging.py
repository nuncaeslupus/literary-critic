"""Self-update (release phase 2): build a newer release's runtime for the launcher.

When the update check finds a newer release, ``stage`` downloads its wheel and hashed
requirements, builds ``runtime/X.Y.Z`` with the uv the app gave this server (``UV``,
release Q-5), self-tests it (``initialize`` and ``tools/list``) and only then names it
``current`` in ``runtime/state.json``. ``extension/launch.py`` runs it at the next start
and rolls back if it fails to start. Nothing changes in the running server.

A release that sets ``reinstall`` (the manifest or the launcher changed), the "Update
automatically" setting off (``LC_AUTO_UPDATE``), or no uv leaves the phase-1 notice
instead. Any failure leaves the runtime unnamed; it is retried the next day.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from litcritic import __version__, kit

AUTO_ENV = "LC_AUTO_UPDATE"  # the manifest passes the writer's checkbox; unset means off
ROOT_ENV = "LC_RUNTIME_DIR"  # tests; else %LOCALAPPDATA%\literary-critic\runtime
DOWNLOAD = "https://github.com/nuncaeslupus/literary-critic/releases/download/v{v}/{name}"
RETRY_SECONDS = kit.CACHE_SECONDS  # a failed staging is retried the next day
LOCK_SECONDS = 3600  # an older lock was left by a server that died mid-staging
STEP_TIMEOUT = 900  # seconds for each uv step; installing pulls pywin32 from PyPI
SELFTEST_TIMEOUT = 120
OFF = {"", "0", "false", "no", "off"}

Fetch = Callable[[str], bytes]
Run = Callable[..., Any]  # subprocess.run's signature

SELFTEST = [
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"capabilities": {}, "clientInfo": {"name": "staging", "version": "0"}},
    },
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
]


def runtime_root() -> Path:
    if os.environ.get(ROOT_ENV):
        return Path(os.environ[ROOT_ENV])
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "literary-critic" / "runtime"


def enabled() -> bool:
    return os.environ.get(AUTO_ENV, "").strip().lower() not in OFF


def find_uv() -> str | None:
    return os.environ.get("UV") or shutil.which("uv")


def python_of(runtime: Path) -> Path:
    if sys.platform == "win32":
        return runtime / "Scripts" / "python.exe"
    return runtime / "bin" / "python"


def load(root: Path) -> dict[str, Any]:
    try:
        state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def save(root: Path, state: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / "state.json.tmp"
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(root / "state.json")


def _newer(version: object, than: str = __version__) -> bool:
    mine, other = kit._parse(than), kit._parse(str(version))
    return mine is not None and other is not None and other > mine


def running_staged() -> str | None:
    """The staged version this server runs, when the launcher started one."""
    with contextlib.suppress(OSError):
        prefix = Path(sys.prefix).resolve()
        if prefix.parent == runtime_root().resolve():
            return prefix.name
    return None


def status() -> dict[str, bool]:
    """``applied`` (once per version: this start runs a staged update) and
    ``restart_needed`` (a staged newer version waits for the app to restart)."""
    try:
        root = runtime_root()
        state = load(root)
        running = running_staged()
        applied = running is not None and state.get("announced") != running
        if applied:
            state["announced"] = running
            save(root, state)
        current = state.get("current")
        waiting = _newer(current) and current not in (state.get("bad") or [])
        return {"applied": applied, "restart_needed": waiting}
    except Exception:  # an unreadable runtime folder is no update, never an error
        return {"applied": False, "restart_needed": False}


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "literary-critic"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        body: bytes = resp.read()
        return body


@contextlib.contextmanager
def _lock(root: Path) -> Iterator[bool]:
    """One staging at a time: the app may start two servers at once."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / "staging.lock"
    with contextlib.suppress(OSError):
        if time.time() - path.stat().st_mtime > LOCK_SECONDS:
            path.unlink()
    try:
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except OSError:
        yield False
        return
    try:
        yield True
    finally:
        with contextlib.suppress(OSError):
            path.unlink()


def _quiet() -> dict[str, Any]:
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def selftest(python: Path, run: Run = subprocess.run) -> bool:
    """The staged server answers ``initialize`` and lists its tools."""
    lines = "".join(json.dumps(m) + "\n" for m in SELFTEST)
    env = {**os.environ, AUTO_ENV: "false"}  # the self-test never stages in turn
    try:
        done = run(
            [str(python), "-m", "litcritic", "mcp"],
            input=lines,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=SELFTEST_TIMEOUT,
            env=env,
            **_quiet(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    replies: dict[Any, Any] = {}
    for line in str(done.stdout).splitlines():
        with contextlib.suppress(ValueError, AttributeError):
            reply = json.loads(line)
            replies[reply.get("id")] = reply
    tools = (replies.get(2) or {}).get("result", {}).get("tools")
    return bool((replies.get(1) or {}).get("result")) and bool(tools)


def _build(version: str, root: Path, uv: str, fetch: Fetch, run: Run) -> str:
    meta = json.loads(fetch(DOWNLOAD.format(v=version, name="release.json")))
    if meta.get("reinstall") is True:
        return "reinstall"
    downloads = root / "downloads" / version
    shutil.rmtree(downloads, ignore_errors=True)
    downloads.mkdir(parents=True)
    reqs = f"requirements-{version}.txt"
    for name in (reqs, f"literary_critic-{version}-py3-none-any.whl"):
        (downloads / name).write_bytes(fetch(DOWNLOAD.format(v=version, name=name)))
    target = root / version
    shutil.rmtree(target, ignore_errors=True)
    steps = (
        [uv, "venv", "--python", sys.executable, str(target)],
        [uv, "pip", "install", "--require-hashes", "--python", str(python_of(target)),
         "-r", str(downloads / reqs)],
    )  # fmt: skip
    for cmd in steps:  # the requirements name the wheel relative to its folder
        run(cmd, cwd=downloads, check=True, capture_output=True, timeout=STEP_TIMEOUT, **_quiet())
    shutil.rmtree(downloads, ignore_errors=True)
    if not selftest(python_of(target), run):
        shutil.rmtree(target, ignore_errors=True)
        return "failed"
    state = load(root)
    old = state.get("current")
    if old != version:
        state["previous"] = old if isinstance(old, str) else None
    state["current"] = version
    (state.get("failures") or {}).pop(version, None)
    save(root, state)
    return "staged"


def stage(
    latest: str | None,
    *,
    force: bool = False,
    fetch: Fetch = download,
    run: Run = subprocess.run,
) -> str:
    """Stage release ``latest`` for the next start. The outcome: ``staged``, ``ready``
    (staged before), ``none`` (nothing newer), ``off`` (setting off or no uv),
    ``reinstall`` (needs the ``.mcpb``), ``busy`` (another server is staging) or
    ``failed``. ``force`` ("update now") skips the daily retry limit."""
    if not latest or not _newer(latest):
        return "none"
    uv = find_uv()
    if not enabled() or not uv:
        return "off"
    root = runtime_root()
    state = load(root)
    if latest in (state.get("bad") or []):
        return "failed"
    if state.get("current") == latest and python_of(root / latest).is_file():
        return "ready"
    tried = (state.get("tried") or {}).get(latest)
    if not force and isinstance(tried, int | float) and time.time() - tried < RETRY_SECONDS:
        return "failed"
    with _lock(root) as held:
        if not held:
            return "busy"
        state.setdefault("tried", {})[latest] = time.time()
        save(root, state)
        try:
            return _build(latest, root, uv, fetch, run)
        except Exception:  # offline, a bad hash, a uv error: try again tomorrow
            shutil.rmtree(root / latest, ignore_errors=True)
            return "failed"
