"""Smoke-test a packed ``.mcpb`` the way the Claude app runs it, before it is released.

Unpack it, ``uv sync`` it with a uv-managed Python only (the writer has no Python), start
``launch.py`` and drive ``initialize``, ``tools/list`` and ``works`` over JSON-RPC, then
check that every installed package is the version ``uv.lock`` pins and, on Windows, that
pywin32 imports (doc-control's live engine needs it).

    python scripts/smoke_mcpb.py dist/literary-critic-X.Y.Z.mcpb
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

NEEDED = ("doc-control",)  # must be installed, whatever else the lock holds
TOOLS = ("works", "resume", "change_card")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def lock_versions(lock_text: str) -> dict[str, str]:
    return {
        _norm(p["name"]): str(p["version"])
        for p in tomllib.loads(lock_text).get("package", [])
        if "version" in p
    }


def version_problems(installed: dict[str, str], lock_text: str) -> list[str]:
    """Every way the installed packages differ from the lock: a version it does not pin,
    a package it does not hold, a needed package missing. Empty when they match."""
    locked = lock_versions(lock_text)
    have = {_norm(k): v for k, v in installed.items()}
    problems = [
        f"{name} {version} installed, lock has {locked.get(name, 'nothing')}"
        for name, version in sorted(have.items())
        if locked.get(name) != version
    ]
    problems += [f"{name} not installed" for name in NEEDED if name not in have]
    return problems


def _env() -> dict[str, str]:
    env = {**os.environ, "UV_PYTHON_PREFERENCE": "only-managed"}
    env.pop("VIRTUAL_ENV", None)
    return env


def _installed(bundle: Path) -> dict[str, str]:
    out = subprocess.run(
        ["uv", "pip", "list", "--format", "json", "--directory", str(bundle)],
        check=True,
        capture_output=True,
        text=True,
        env=_env(),
    ).stdout
    return {p["name"]: p["version"] for p in json.loads(out)}


def _rpc(bundle: Path, folders: Path) -> list[dict[str, object]]:
    sends = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "works"}},
    ]
    env = {**_env(), "LITCRITIC_FOLDERS": str(folders / "folders.json")}
    done = subprocess.run(
        ["uv", "run", "--frozen", "--directory", str(bundle), "launch.py", str(folders)],
        input="".join(json.dumps(s) + "\n" for s in sends),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=600,
    )
    replies = [json.loads(line) for line in done.stdout.splitlines() if line.startswith("{")]
    if len(replies) != len(sends):
        raise SystemExit(f"smoke: {len(replies)} replies\n{done.stdout}\n{done.stderr}")
    return replies


def smoke(mcpb: Path) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "bundle"
        with zipfile.ZipFile(mcpb) as z:
            z.extractall(bundle)
        subprocess.run(
            ["uv", "sync", "--frozen", "--directory", str(bundle)], check=True, env=_env()
        )
        problems = version_problems(_installed(bundle), (bundle / "uv.lock").read_text("utf-8"))
        replies = _rpc(bundle, Path(tmp))
        problems += [f"{r['id']}: {r['error']}" for r in replies if "error" in r]
        tools = {t["name"] for t in replies[1].get("result", {}).get("tools", [])}  # type: ignore[union-attr]
        problems += [f"tool {t} missing" for t in TOOLS if t not in tools]
        works = replies[2].get("result", {})
        if not isinstance(works, dict) or works.get("isError"):
            problems.append(f"works failed: {works}")
        if sys.platform == "win32":
            probe = ["uv", "run", "--frozen", "--directory", str(bundle), "python", "-c"]
            got = subprocess.run([*probe, "import win32com.client"], env=_env(), check=False)
            if got.returncode:
                problems.append("pywin32 does not import")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    problems = smoke(Path(args[0]))
    for p in problems:
        print(f"smoke: {p}", file=sys.stderr)
    print("smoke: ok" if not problems else f"smoke: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
