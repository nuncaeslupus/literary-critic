"""Windows Controlled folder access: is it on, and which folders does it protect?

Controlled folder access (Windows Security's ransomware protection) refuses writes by
programs it does not know in Documents, Desktop, Pictures, Videos, Music and Favorites,
plus any folder the user added. ``Get-MpPreference`` lists only the user-added folders;
the default ones are implicit, so ``Status.protects`` always counts them. A normal
(non-admin) user can read the settings (release probe, Q-8). Only the mode "on" blocks:
"audit" (2) and "off" (0) let writes through.

``read`` asks PowerShell, then the registry; it returns None when neither answers (not
Windows, Defender absent, policy hides it), and the caller then tries the folder and
falls back if Windows refuses. Tests pass their own ``Status`` or a fake ``run``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from litcritic.winblock import PROTECTED

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]

QUERY = (
    "Get-MpPreference | Select-Object EnableControlledFolderAccess,"
    "ControlledFolderAccessProtectedFolders | ConvertTo-Json -Compress"
)
REGISTRY = (
    r"SOFTWARE\Microsoft\Windows Defender\Windows Defender Exploit Guard\Controlled Folder Access"
)
ON = 1
TIMEOUT = 20  # seconds


def _parts(path: str | Path) -> list[str]:
    return [p for p in os.path.normcase(str(path)).replace("\\", "/").split("/") if p]


def _inside(path: str | Path, root: str | Path) -> bool:
    p, r = _parts(path), _parts(root)
    return bool(r) and p[: len(r)] == r


@dataclass(frozen=True)
class Status:
    """Whether protection is on, and the folders the user added to it."""

    enabled: bool
    folders: tuple[str, ...] = field(default_factory=tuple)

    def protects(
        self, path: str | Path, home: Path | None = None, onedrive: Path | None = None
    ) -> bool:
        """The path is inside a protected folder: one the user added, or a default one
        (Documents, Desktop, ... directly under the profile or OneDrive's root)."""
        if not self.enabled:
            return False
        if any(_inside(path, f) for f in self.folders):
            return True
        home = home if home is not None else _profile()
        onedrive = onedrive if onedrive is not None else onedrive_root()
        for base in (home, onedrive):
            if base is None or not _inside(path, base):
                continue
            rest = _parts(path)[len(_parts(base)) :]
            if rest and rest[0] in {n.casefold() for n in PROTECTED}:
                return True
        return False


def _profile() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home())


def onedrive_root() -> Path | None:
    """OneDrive's root when it is set up (the personal one first), else None."""
    for name in ("OneDriveConsumer", "OneDrive", "OneDriveCommercial"):
        value = os.environ.get(name)
        if value and Path(value).is_dir():
            return Path(value)
    return None


def fallback_base(home: Path | None = None, onedrive: Path | None = None) -> Path:
    """``<OneDrive>/literary-critic`` when OneDrive is set up, else the profile's."""
    onedrive = onedrive if onedrive is not None else onedrive_root()
    return (onedrive or home or _profile()) / "literary-critic"


def _list(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [value]
    return tuple(str(v) for v in value) if isinstance(value, list) else ()


def _from_powershell(run: Runner) -> Status | None:
    try:
        done = run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", QUERY],
            capture_output=True,
            timeout=TIMEOUT,
        )
        if done.returncode != 0:
            return None
        data = json.loads(bytes(done.stdout).decode("utf-8", errors="replace").lstrip("﻿"))
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("EnableControlledFolderAccess"), int):
        return None
    return Status(
        data["EnableControlledFolderAccess"] == ON,
        _list(data.get("ControlledFolderAccessProtectedFolders")),
    )


def _from_registry() -> Status | None:
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REGISTRY) as key:
            mode, _ = winreg.QueryValueEx(key, "EnableControlledFolderAccess")
        added: list[str] = []
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REGISTRY + r"\ProtectedFolders") as sub:
                i = 0
                while True:
                    added.append(winreg.EnumValue(sub, i)[0])
                    i += 1
        except OSError:
            pass  # no list, or its end
    except OSError:
        return None
    return Status(mode == ON, tuple(added))


def read(run: Runner = subprocess.run) -> Status | None:
    """The machine's setting, or None when it cannot be read. Off Windows there is no
    such protection, so it answers "off"."""
    if os.name != "nt" and run is subprocess.run:
        return Status(False)
    return _from_powershell(run) or _from_registry()
