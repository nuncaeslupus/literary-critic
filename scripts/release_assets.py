"""Build the staging assets of a release: wheel, hashed requirements, release.json.

The runtime updater downloads these beside the .mcpb. Every package in the requirements
file, and the project's own wheel, is pinned by hash so it installs with --require-hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = "extension"


def _run(*cmd: str) -> str:
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def build_wheel(out: Path) -> Path:
    """Build the project's wheel into ``out`` and return its path."""
    out.mkdir(parents=True, exist_ok=True)
    _run("uv", "build", "--wheel", "--out-dir", str(out))
    wheels = sorted(out.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one wheel in {out}, found {len(wheels)}")
    return wheels[0]


def export_requirements() -> str:
    """The locked runtime packages with hashes (no dev tools, no project itself)."""
    return _run(
        "uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--hashes",
        "--no-header", "--no-annotate",
    )  # fmt: skip


def requirements_text(exported: str, wheel: Path) -> str:
    """The exported lock plus the project's own wheel, pinned by hash."""
    pins = [ln for ln in exported.splitlines() if ln.strip()]
    body = "\n".join(pins)
    unhashed = [
        ln
        for ln in re.split(r"\n(?=\S)", body)
        if ln and not ln.startswith(("#", "-")) and "--hash=sha256:" not in ln
    ]
    if unhashed:
        raise SystemExit(f"packages without a hash: {unhashed[0].split()[0]}")
    own = f"literary-critic @ ./{wheel.name} \\n    --hash=sha256:{sha256(wheel)}"
    return f"{body}\n{own}\n"


def changed_since(tag: str | None, path: str = EXTENSION_DIR) -> bool:
    """True when ``path`` differs between ``tag`` and HEAD (False with no earlier release)."""
    if tag is None:
        return False
    return bool(_run("git", "diff", "--name-only", tag, "HEAD", "--", path).strip())


def previous_release_tag(version: str) -> str | None:
    tags = _run("git", "tag", "--list", "v*", "--sort=-v:refname").split()
    return next((t for t in tags if t != f"v{version}"), None)


def release_json(version: str, reinstall: bool) -> str:
    return json.dumps({"version": version, "reinstall": reinstall}, indent=2) + "\n"


def build(out: Path) -> list[Path]:
    version = project_version()
    wheel = build_wheel(out)
    reqs = out / f"requirements-{version}.txt"
    reqs.write_text(requirements_text(export_requirements(), wheel), encoding="utf-8")
    meta = out / "release.json"
    reinstall = changed_since(previous_release_tag(version))
    meta.write_text(release_json(version, reinstall), encoding="utf-8")
    return [wheel, reqs, meta]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    for p in build(ap.parse_args().out):
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
