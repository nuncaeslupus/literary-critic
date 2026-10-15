"""The folders the desktop extension may touch, and the works found in them.

The writer grants folders twice: the install setting (passed to ``lc mcp`` as
arguments) and every folder picked later with ``add_folder``, kept in
``folders.json``. A granted folder holds novels, or is one novel; a work is found
one level deep, as ``<folder>/<novel>/literary-critic/`` (chat D-10) or a work
folder directly. Every path a tool reads or writes goes through ``confine``.
"""

from __future__ import annotations

import json
import os
import subprocess
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from litcritic.mcp import ToolError
from litcritic.setup import FORMATS, WORKSPACE_DIR
from litcritic.workspace import MANIFEST, Workspace

FOLDERS_ENV = "LITCRITIC_FOLDERS"
PICK_TIMEOUT = 600  # seconds the folder picker waits for the writer
# The Windows folder dialog on a topmost form, so it opens above the app. The path is
# written as UTF-8 without a BOM: the console's code page garbles accented names.
PICKER = r"""
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form -Property @{TopMost = $true}
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Choose the folder that holds your novel'
$dialog.ShowNewFolderButton = $false
if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
  $out = [Console]::OpenStandardOutput()
  $bytes = (New-Object System.Text.UTF8Encoding $false).GetBytes($dialog.SelectedPath)
  $out.Write($bytes, 0, $bytes.Length)
}
"""

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


def state_file() -> Path:
    """``folders.json``: ``%APPDATA%\\literary-critic`` on Windows, else the config dir."""
    env = os.environ.get(FOLDERS_ENV)
    if env:
        return Path(env).expanduser()
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "literary-critic" / "folders.json"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "litcritic" / "folders.json"


def _real(path: Path) -> Path:
    """The path with every link and junction followed, as the OS will open it."""
    return Path(os.path.realpath(path))


def _key(path: Path) -> str:
    return os.path.normcase(str(path))


def _inside(path: Path, root: Path) -> bool:
    """Component-wise, so ``Novels2`` is not inside ``Novels``."""
    p, r = _key(path), _key(root).rstrip(os.sep)
    return p == r or p.startswith(r + os.sep)


def _fold(text: str) -> str:
    """Lower case without accents: ``Época`` and ``epoca`` match."""
    nfkd = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip()


@dataclass
class Grant:
    """The granted folders: the install setting plus those added from the chat."""

    install: list[str] = field(default_factory=list)

    def added(self) -> list[str]:
        try:
            data = json.loads(state_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        folders = data.get("folders") if isinstance(data, dict) else None
        return [f for f in folders or [] if isinstance(f, str)]

    def add(self, folder: str | Path) -> Path:
        """Store a folder the writer picked; returns it as stored."""
        path = _real(Path(folder).expanduser())
        if not path.is_dir():
            raise ToolError("not_a_folder", path=str(folder))
        known = self.added()
        if not any(_key(Path(k)) == _key(path) for k in known):
            out = state_file()
            out.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps({"folders": [*known, str(path)]}, ensure_ascii=False, indent=1)
            out.write_text(text + "\n", encoding="utf-8")
        return path

    def roots(self) -> list[Path]:
        """Existing granted folders, links followed, each once."""
        out: list[Path] = []
        for f in [*self.install, *self.added()]:
            if not f.strip():
                continue
            p = _real(Path(f).expanduser())
            if p.is_dir() and not any(_key(p) == _key(o) for o in out):
                out.append(p)
        return out

    def confine(self, path: str | Path, base: Path | None = None) -> Path:
        """``path`` with links followed, or ``ToolError`` when it leaves every granted folder.

        A relative path is taken from ``base`` (itself confined); without one it is refused.
        """
        p = Path(path).expanduser()
        if not p.is_absolute():
            if base is None:
                raise ToolError("outside_granted_folders", path=str(path))
            p = self.confine(base) / p
        real = _real(p)
        if not any(_inside(real, r) for r in self.roots()):
            raise ToolError("outside_granted_folders", path=str(path))
        return real

    def works(self) -> list[Workspace]:
        """Works one level deep in the granted folders, sorted by path."""
        found: dict[str, Path] = {}
        for root in self.roots():
            try:
                children = [c for c in root.iterdir() if not c.name.startswith(".")]
            except OSError:
                children = []
            for d in [root, *(c for c in children if c.is_dir())]:
                for cand in (d, d / WORKSPACE_DIR):
                    if (cand / MANIFEST).is_file():
                        try:
                            real = self.confine(cand)
                        except ToolError:
                            continue  # a link out of the granted folders
                        found.setdefault(_key(real), real)
        return [Workspace(p) for p in sorted(found.values())]

    def unset(self) -> list[Path]:
        """Folders one level deep in the granted folders that hold a manuscript but were
        never set up (no working folder): novels the writer can start on, sorted by path."""
        found: dict[str, Path] = {}
        for root in self.roots():
            try:
                children = [c for c in root.iterdir() if not c.name.startswith(".")]
            except OSError:
                children = []
            for d in [root, *(c for c in children if c.is_dir())]:
                if d.name == WORKSPACE_DIR or (d / MANIFEST).is_file():
                    continue
                if (d / WORKSPACE_DIR / MANIFEST).is_file() or not _has_manuscript(d):
                    continue
                found.setdefault(_key(d), d)
        return sorted(found.values())

    def lookup(self, name: str) -> list[Workspace]:
        """Works whose title, slug, id or folder name matches ``name`` (any case or accents)."""
        want = _fold(name)
        hits = []
        for ws in self.works():
            try:
                meta = ws.manifest
            except (OSError, ValueError):
                meta = {}
            novel = ws.root.parent if ws.root.name == WORKSPACE_DIR else ws.root
            names = [meta.get(k) for k in ("title", "slug", "id")] + [novel.name, ws.root.name]
            if any(isinstance(n, str) and _fold(n) == want for n in names):
                hits.append(ws)
        return hits


def _has_manuscript(folder: Path) -> bool:
    try:
        return any(
            f.is_file()
            and f.suffix.lower() in FORMATS
            and not f.name.startswith(("~$", ".~lock.", "."))
            for f in folder.iterdir()
        )
    except OSError:
        return False


def matches(folder: Path, name: str) -> bool:
    """Whether ``name`` names this not-set-up novel: its folder or one of its documents
    (any case or accents)."""
    want = _fold(name)
    if _fold(folder.name) == want:
        return True
    try:
        return any(_fold(f.stem) == want for f in folder.iterdir() if f.is_file())
    except OSError:
        return False


def pick_folder(run: Runner = subprocess.run) -> str:
    """The folder the writer chose in the Windows picker, or "" when cancelled."""
    if os.name != "nt" and run is subprocess.run:
        raise ToolError("picker_unavailable", detail="the folder picker needs Windows")
    try:
        done = run(
            ["powershell", "-NoProfile", "-NonInteractive", "-STA", "-Command", PICKER],
            capture_output=True,
            timeout=PICK_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return ""
    except OSError as exc:
        raise ToolError("picker_unavailable", detail=str(exc)) from exc
    return bytes(done.stdout).decode("utf-8", errors="replace").lstrip("\ufeff").strip()


def add_folder(grant: Grant, run: Runner = subprocess.run) -> dict[str, object]:
    """Ask the writer for a folder with the picker and grant it."""
    chosen = pick_folder(run)
    if not chosen:
        return {"cancelled": True}
    folder = grant.add(chosen)
    titles = []
    for ws in grant.works():
        try:
            titles.append(str(ws.manifest.get("title") or ws.root.name))
        except (OSError, ValueError):
            titles.append(ws.root.name)
    out: dict[str, object] = {"added": str(folder), "works": titles}
    if fresh := grant.unset():
        out["not_set_up"] = [{"name": d.name, "folder": str(d)} for d in fresh]
    return out
