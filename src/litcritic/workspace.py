"""Locate and create per-novel workspaces, which always live outside this repo."""

from __future__ import annotations

import os
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

HOME_ENV = "LITCRITIC_HOME"
DEFAULT_HOME = Path.home() / "literary-critic"
MANIFEST = "workspace.toml"
GUARD_TERMS = "guard-terms.txt"
SUBDIRS = ("manuscript", "text", "index", "metrics", "analysis", "revisions", "log")


class WorkspaceError(Exception):
    """Raised when a workspace path is invalid or unsafe."""


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def manifest(self) -> dict[str, object]:
        return tomllib.loads((self.root / MANIFEST).read_text(encoding="utf-8"))

    @property
    def guard_terms_file(self) -> Path:
        return self.root / GUARD_TERMS


def home() -> Path:
    """Directory holding all workspaces ($LITCRITIC_HOME or ~/literary-critic)."""
    env = os.environ.get(HOME_ENV)
    return Path(env).expanduser() if env else DEFAULT_HOME


def repo_root() -> Path:
    """Root of this tool's source tree."""
    return Path(__file__).resolve().parents[2]


def _git_toplevel(path: Path) -> Path | None:
    probe = path if path.is_dir() else path.parent
    while not probe.exists():
        probe = probe.parent
    try:
        out = subprocess.run(
            ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return Path(out.stdout.strip()).resolve()


def check_location(path: Path) -> None:
    """Refuse workspaces inside this repo's work tree."""
    resolved = path.expanduser().resolve()
    tool = repo_root().resolve()
    if resolved == tool or tool in resolved.parents:
        raise WorkspaceError(f"workspace {resolved} is inside the tool repo {tool}")
    top = _git_toplevel(resolved)
    if top is not None and top == tool:
        raise WorkspaceError(f"workspace {resolved} is inside the tool repo work tree")


def create(slug: str, title: str, language: str, base: Path | None = None) -> Workspace:
    """Create an empty workspace skeleton for one novel."""
    if not slug or "/" in slug or slug.startswith("."):
        raise WorkspaceError(f"invalid slug: {slug!r}")
    root = (base or home()) / slug
    check_location(root)
    if (root / MANIFEST).exists():
        raise WorkspaceError(f"workspace already exists: {root}")
    for sub in SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / MANIFEST).write_text(
        f'slug = "{slug}"\ntitle = "{title}"\nlanguage = "{language}"\n'
        'audience = "writer"\nschema_version = 1\n',
        encoding="utf-8",
    )
    (root / GUARD_TERMS).write_text(
        "# One term per line: title, character, place and other names that must\n"
        "# never appear in the literary-critic repo. Lines starting with # are ignored.\n"
        f"{title}\n",
        encoding="utf-8",
    )
    return Workspace(root)


def all_workspaces(base: Path | None = None) -> list[Workspace]:
    root = base or home()
    if not root.is_dir():
        return []
    return [Workspace(p.parent) for p in sorted(root.glob(f"*/{MANIFEST}"))]
