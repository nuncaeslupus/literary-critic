import os
from pathlib import Path

import pytest


def bare_env(home: Path) -> dict[str, str]:
    """A near-empty environment for running the tool as a fresh process, on any platform."""
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home)}
    if os.name == "nt":  # Windows finds the home folder and its own DLLs through these
        env |= {"USERPROFILE": str(home), "SYSTEMROOT": os.environ["SYSTEMROOT"]}
    return env


def symlink_or_skip(link: Path, target: Path) -> None:
    """Windows only lets privileged accounts (or Developer Mode) create symlinks."""
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError:
        pytest.skip("this account cannot create symlinks")


@pytest.fixture(autouse=True)
def _isolate_user_state(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never read or write the real workspace home or registry during tests."""
    state = tmp_path_factory.mktemp("user-state")
    monkeypatch.setenv("LITCRITIC_HOME", str(Path(state) / "home"))
    monkeypatch.setenv("LITCRITIC_REGISTRY", str(Path(state) / "registry.txt"))
