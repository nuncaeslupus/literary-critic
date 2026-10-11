"""Locate and create per-novel workspaces, which always live outside this repo."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

HOME_ENV = "LITCRITIC_HOME"
REGISTRY_ENV = "LITCRITIC_REGISTRY"
DEFAULT_HOME = Path.home() / "literary-critic"
MANIFEST = "work.toml"
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


def registry_file() -> Path:
    """Per-user list of workspace roots created outside the default home."""
    env = os.environ.get(REGISTRY_ENV)
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "litcritic" / "workspaces.txt"


def register(root: Path) -> None:
    """Remember a workspace created outside the default home, so slugs find it."""
    reg = registry_file()
    known = reg.read_text(encoding="utf-8").splitlines() if reg.is_file() else []
    if str(root) not in known:
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text("\n".join([*known, str(root)]) + "\n", encoding="utf-8")


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
    """Refuse workspaces inside this repo's work tree.

    An unpacked chat kit is not a work tree (nothing there is committed), so
    its own folder may hold workspaces; a git checkout of the tool may not.
    """
    resolved = path.expanduser().resolve()
    tool = repo_root().resolve()
    inside = resolved == tool or tool in resolved.parents
    if inside and (tool / ".git").exists():
        raise WorkspaceError(f"workspace {resolved} is inside the tool repo {tool}")
    top = _git_toplevel(resolved)
    if top is not None and top == tool:
        raise WorkspaceError(f"workspace {resolved} is inside the tool repo work tree")


def create(
    slug: str,
    title: str,
    language: str,
    base: Path | None = None,
    author: str = "",
    kind: str = "novel",
    series: str = "",
    tags: tuple[str, ...] = (),
) -> Workspace:
    """Create an empty work: a folder named ``slug`` with a unique id in ``work.toml``."""
    if not slug or "/" in slug or slug.startswith("."):
        raise WorkspaceError(f"invalid slug: {slug!r}")
    root = ((base or home()).expanduser() / slug).resolve()
    check_location(root)
    if (root / MANIFEST).exists():
        raise WorkspaceError(f"workspace already exists: {root}")
    for sub in SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    q = json.dumps  # JSON string escaping is valid TOML basic-string escaping
    work_id = f"{slug}-{secrets.token_hex(3)}"
    (root / MANIFEST).write_text(
        f"id = {q(work_id)}\nslug = {q(slug)}\ntitle = {q(title)}\nauthor = {q(author)}\n"
        f"kind = {q(kind)}\nseries = {q(series)}\ntags = {q(list(tags))}\n"
        f'language = {q(language)}\nmode = "revision"\nschema_version = 2\n',
        encoding="utf-8",
    )
    (root / GUARD_TERMS).write_text(
        "# One term per line: title, character, place and other names that must\n"
        "# never appear in the literary-critic repo. Lines starting with # are ignored.\n"
        f"{' '.join(title.split())}\n",
        encoding="utf-8",
    )
    register(root)
    return Workspace(root)


def _under(root: Path) -> set[Path]:
    """Work folders anywhere under ``root`` (hidden folders and works' insides skipped)."""
    found: set[Path] = set()
    if not root.is_dir():
        return found
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = list(d.iterdir())
        except OSError:
            continue
        if (d / MANIFEST).is_file():
            found.add(d.resolve())
            continue  # a work never contains another work
        stack += [e for e in entries if e.is_dir() and not e.name.startswith(".")]
    return found


def all_workspaces(base: Path | None = None) -> list[Workspace]:
    """Works under ``base`` (default home, any depth), plus registered ones without a base."""
    found = _under((base or home()).expanduser())
    if base is None and registry_file().is_file():
        for line in registry_file().read_text(encoding="utf-8").splitlines():
            p = Path(line.strip())
            if line.strip() and (p / MANIFEST).is_file():
                found.add(p.resolve())
    return [Workspace(p) for p in sorted(found)]


def resolve(ref: str, base: Path | None = None) -> Workspace:
    """A workspace from a folder path or a slug (searched under ``base``/home and the registry)."""
    path = Path(ref).expanduser()
    if (path / MANIFEST).is_file():
        check_location(path.resolve())
        return Workspace(path.resolve())
    works = all_workspaces(base)
    by_id = [ws for ws in works if ws.manifest.get("id") == ref]
    if by_id:
        return by_id[0]
    matches = [ws for ws in works if ws.root.name == ref or ws.manifest.get("slug") == ref]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise WorkspaceError(f"no work {ref!r} (give its id, folder or run `lc init`)")
    ids = ", ".join(str(ws.manifest.get("id", ws.root)) for ws in matches)
    raise WorkspaceError(f"several works named {ref!r}; give one of these ids: {ids}")
