"""Decide what a new doc-control release means for this project (run daily by CI).

A newer version inside the range ``pyproject.toml`` pins is a bump PR: the lock upgrades
doc-control and the patch version goes up, so merging the PR releases it. A version
outside the range opens an issue instead: the range is a code decision.

    python scripts/doccontrol_bump.py [--apply]   # --apply bumps pyproject.toml's version

Prints ``action=none|pr|issue``, ``latest=`` and ``version=`` lines (also to
``$GITHUB_OUTPUT`` when set).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPI = "https://pypi.org/pypi/doc-control/json"
RANGE = re.compile(r'"doc-control(?:\[[^\]]*\])?>=([\d.]+),<([\d.]+)"')
VERSION = re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"', re.M)


def _v(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in text.split("."))


def pinned_range(pyproject: str) -> tuple[str, str]:
    m = RANGE.search(pyproject)
    if not m:
        raise SystemExit("doccontrol_bump: no doc-control>=X,<Y range in pyproject.toml")
    return m.group(1), m.group(2)


def locked(lock: str) -> str:
    for p in tomllib.loads(lock).get("package", []):
        if p.get("name") == "doc-control":
            return str(p["version"])
    raise SystemExit("doccontrol_bump: doc-control is not in uv.lock")


def decide(current: str, latest: str, low: str, high: str) -> str:
    """``pr`` for a newer version inside ``[low, high)``, ``issue`` for one at or past
    ``high``, else ``none``."""
    if _v(latest) <= _v(current):
        return "none"
    if _v(latest) >= _v(high):
        return "issue"
    return "pr" if _v(latest) >= _v(low) else "none"


def bump_patch(pyproject: str) -> tuple[str, str]:
    m = VERSION.search(pyproject)
    if not m:
        raise SystemExit("doccontrol_bump: no version in pyproject.toml")
    new = f"{m.group(1)}.{m.group(2)}.{int(m.group(3)) + 1}"
    return pyproject[: m.start()] + f'version = "{new}"' + pyproject[m.end() :], new


def latest_on_pypi() -> str:
    with urllib.request.urlopen(PYPI, timeout=30) as resp:
        return str(json.loads(resp.read().decode("utf-8"))["info"]["version"])


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    low, high = pinned_range(pyproject)
    latest = latest_on_pypi()
    action = decide(locked((ROOT / "uv.lock").read_text(encoding="utf-8")), latest, low, high)
    version = ""
    if action == "pr" and "--apply" in args:
        text, version = bump_patch(pyproject)
        (ROOT / "pyproject.toml").write_text(text, encoding="utf-8")
    lines = [f"action={action}", f"latest={latest}", f"version={version}", f"range={low},<{high}"]
    print("\n".join(lines))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            out.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
