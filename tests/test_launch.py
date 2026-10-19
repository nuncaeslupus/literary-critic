"""The extension's launcher: newest healthy runtime, rollback after failed starts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _launch() -> ModuleType:
    spec = importlib.util.spec_from_file_location("launch", ROOT / "extension" / "launch.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launch = _launch()


def runtime(root: Path, version: str) -> Path:
    exe = root / version / "Scripts" / "python.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    return exe


class Server:
    """Fakes for one start: the staged child's exit code and how long it ran."""

    def __init__(self, code: int = 0, seconds: float = 60.0) -> None:
        self.code, self.seconds = code, seconds
        self.calls: list[list[str]] = []
        self.bundled: list[list[str]] = []
        self.now = 0.0

    def call(self, cmd: list[str]) -> int:
        self.calls.append(cmd)
        self.now += self.seconds
        return self.code

    def serve(self, args: list[str]) -> int:
        self.bundled.append(args)
        return 0

    def start(self, argv: list[str] | None = None) -> int:
        code: int = launch.main(
            argv or [],
            call=self.call,
            serve=self.serve,
            clock=lambda: self.now,
            bundled="0.1.1",
        )
        return code


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "runtime"
    monkeypatch.setenv("LC_RUNTIME_DIR", str(path))
    return path


def write_state(root: Path, **state: object) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "state.json").write_text(json.dumps(state))


def read_state(root: Path) -> dict[str, object]:
    state: dict[str, object] = json.loads((root / "state.json").read_text())
    return state


def test_launch_two_failures_roll_back(root: Path) -> None:
    # With no staged runtime, the bundled one runs.
    fresh = Server()
    fresh.start(["C:\\Novels", "${user_config.novels_folder}"])
    assert fresh.bundled == [["C:\\Novels"]] and not fresh.calls

    old, previous = runtime(root, "0.1.2"), runtime(root, "0.1.5")
    current = runtime(root, "0.2.0")
    write_state(root, current="0.2.0", previous="0.1.5")

    # Two quick error exits mark the current runtime bad.
    broken = Server(code=1, seconds=2.0)
    assert broken.start(["C:\\Novels"]) == 1
    assert broken.calls[0] == [str(current), "-m", "litcritic", "mcp", "C:\\Novels"]
    assert read_state(root)["failures"] == {"0.2.0": 1}
    broken.start()
    assert read_state(root)["bad"] == ["0.2.0"]

    # The next start runs the previous runtime, and two runtimes are kept.
    healthy = Server()
    healthy.start()
    assert healthy.calls[0][0] == str(previous)
    assert not old.exists() and not current.exists() and previous.exists()


def test_launch_healthy_run_clears_failures(root: Path) -> None:
    runtime(root, "0.2.0")
    write_state(root, current="0.2.0", failures={"0.2.0": 1})
    Server(code=1, seconds=60.0).start()  # an error after a long run is not a failed start
    assert read_state(root)["failures"] == {}
    assert "bad" not in read_state(root)


def test_launch_bundled_runs_when_newer_or_staged_missing(root: Path) -> None:
    runtime(root, "0.1.0")
    write_state(root, current="0.1.0", previous="0.0.9")  # older than the bundle; 0.0.9 gone
    server = Server()
    server.start()
    assert server.bundled == [[]] and not server.calls


def test_launch_keeps_a_newer_runtime_staging_is_building(root: Path) -> None:
    runtime(root, "0.2.0")
    building = root / "0.3.0"
    building.mkdir()
    write_state(root, current="0.2.0")
    Server().start()
    assert building.exists()


def test_launch_survives_a_corrupt_state(root: Path) -> None:
    root.mkdir()
    (root / "state.json").write_text("{not json")
    server = Server()
    server.start()
    assert server.bundled == [[]]


def test_launch_save_waits_for_a_held_state_and_never_fails_the_exit(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows, or an antivirus scan, holds state.json for a moment (WinError 32)."""
    real = Path.replace
    held = {"times": 2}

    def replace(self: Path, target: Path) -> Path:
        if held["times"]:
            held["times"] -= 1
            raise PermissionError(32, "being used by another process")
        return real(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(launch, "SAVE_WAIT", 0)
    assert launch.save(root, {"current": "0.1.2"}) is True
    assert read_state(root) == {"current": "0.1.2"}

    held["times"] = 99  # held for good: the exit still reports the server's own code
    runtime(root, "0.1.2")
    write_state(root, current="0.1.2")
    assert Server(code=3, seconds=60).start() == 3
    assert not list(root.glob("state.json.*.tmp"))
