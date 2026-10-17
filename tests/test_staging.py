"""Self-update: a newer release is built, self-tested and named for the launcher."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from litcritic import folders, kit, mcp, staging

ROOT = Path(__file__).resolve().parents[1]
NEW = "9.0.0"  # newer than any version this checkout runs


def _launch() -> ModuleType:
    spec = importlib.util.spec_from_file_location("launch", ROOT / "extension" / "launch.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Release:
    """Fake downloads and uv: ``uv venv`` makes the python, the python answers the
    self-test (or not)."""

    def __init__(self, reinstall: bool = False, healthy: bool = True) -> None:
        self.reinstall, self.healthy = reinstall, healthy
        self.fetched: list[str] = []
        self.cmds: list[list[str]] = []

    def fetch(self, url: str) -> bytes:
        self.fetched.append(url.rsplit("/", 1)[1])
        if url.endswith("release.json"):
            return json.dumps({"version": NEW, "reinstall": self.reinstall}).encode()
        return b"payload"

    def run(self, cmd: list[str], **kwargs: Any) -> SimpleNamespace:
        self.cmds.append(cmd)
        if cmd[1] == "venv":
            python = staging.python_of(Path(cmd[-1]))
            python.parent.mkdir(parents=True)
            python.write_text("")
            return SimpleNamespace(stdout="")
        if cmd[1:] == ["-m", "litcritic", "mcp"]:
            assert kwargs["env"]["LC_AUTO_UPDATE"] == "false"
            tools = [{"name": "works"}] if self.healthy else []
            replies = [
                {"id": 1, "result": {"serverInfo": {}}},
                {"id": 2, "result": {"tools": tools}},
            ]
            return SimpleNamespace(stdout="".join(json.dumps(r) + "\n" for r in replies))
        return SimpleNamespace(stdout="")


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "runtime"
    monkeypatch.setenv("LC_RUNTIME_DIR", str(path))
    monkeypatch.setenv("LC_AUTO_UPDATE", "true")
    monkeypatch.setenv("UV", "uv")
    return path


def test_staging_ready_after_selftest_applied_next_start(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The setting off or a release that needs the .mcpb leaves the notice.
    off_or_reinstall_leaves_the_notice(root, monkeypatch)
    shutil.rmtree(root)  # forget that release, so it is not retried only tomorrow

    # A newer release is built, self-tested and named current.
    release = Release()
    assert staging.stage(NEW, fetch=release.fetch, run=release.run) == "staged"
    assert release.fetched == ["release.json", f"requirements-{NEW}.txt",
                               f"literary_critic-{NEW}-py3-none-any.whl"]  # fmt: skip
    assert "--require-hashes" in release.cmds[1]
    state = json.loads((root / "state.json").read_text())
    assert state["current"] == NEW and not (root / "downloads" / NEW).exists()
    assert staging.status() == {"applied": False, "restart_needed": True}
    assert staging.stage(NEW, fetch=release.fetch, run=release.run) == "ready"

    # The launcher runs it at the next start.
    calls: list[list[str]] = []

    def call(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    _launch().main([], call=call, serve=lambda a: 1, bundled="0.1.1")
    assert calls == [[str(staging.python_of(root / NEW)), "-m", "litcritic", "mcp"]]

    # That start says once that it updated.
    monkeypatch.setattr(staging, "running_staged", lambda: NEW)
    assert staging.status()["applied"] is True
    assert staging.status()["applied"] is False

    # "Update now" through the tool stages at once and asks for a restart.
    shutil.rmtree(root)
    update_now_stages_at_once(root, tmp_path, monkeypatch)


def off_or_reinstall_leaves_the_notice(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    release = Release()
    assert staging.stage("0.0.1", fetch=release.fetch, run=release.run) == "none"
    monkeypatch.setenv("LC_AUTO_UPDATE", "false")
    assert staging.stage(NEW, fetch=release.fetch, run=release.run) == "off"
    monkeypatch.setenv("LC_AUTO_UPDATE", "true")
    reinstall = Release(reinstall=True)
    assert staging.stage(NEW, fetch=reinstall.fetch, run=reinstall.run) == "reinstall"
    assert "current" not in staging.load(root) and not release.cmds


def test_staging_failed_selftest_names_nothing_and_waits_a_day(root: Path) -> None:
    broken = Release(healthy=False)
    assert staging.stage(NEW, fetch=broken.fetch, run=broken.run) == "failed"
    assert "current" not in staging.load(root) and not (root / NEW).exists()
    assert staging.load(root)["errors"][NEW] == "the self-test failed"  # why, for support
    assert staging.stage(NEW, fetch=broken.fetch, run=broken.run) == "failed"
    assert len(broken.fetched) == 3  # retried the next day, not now

    def offline(url: str) -> bytes:
        raise OSError("no route to host")

    assert staging.stage(NEW, force=True, fetch=offline, run=broken.run) == "failed"
    assert staging.load(root)["errors"][NEW] == "OSError: no route to host"
    healthy = Release()
    assert staging.stage(NEW, force=True, fetch=healthy.fetch, run=healthy.run) == "staged"
    assert NEW not in staging.load(root)["errors"]


def test_staging_one_at_a_time(root: Path) -> None:
    root.mkdir()
    lock = root / "staging.lock"
    lock.write_text("")
    release = Release()
    assert staging.stage(NEW, fetch=release.fetch, run=release.run) == "busy"
    os.utime(lock, (0, 0))  # left by a server that died mid-staging
    assert staging.stage(NEW, fetch=release.fetch, run=release.run) == "staged"
    assert not lock.exists()


def update_now_stages_at_once(root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(folders.FOLDERS_ENV, str(tmp_path / "folders.json"))
    monkeypatch.setattr(kit, "CACHE", tmp_path / "update.json")
    monkeypatch.setattr(kit, "version_info", lambda: {"version": "0.1.0", "source": "package"})
    monkeypatch.setattr(mcp, "UPDATE", {"available": "unknown", "url": kit.RELEASES_PAGE})
    name = f"literary-critic-{NEW}.mcpb"
    found = {"tag_name": f"v{NEW}", "html_url": "page", "assets": [{"name": name}]}
    monkeypatch.setattr(kit, "_fetch_release", lambda timeout: found)
    release = Release()
    real = staging.stage
    monkeypatch.setattr(
        staging,
        "stage",
        lambda v, force=False: real(v, force=force, fetch=release.fetch, run=release.run),
    )
    update = mcp.works(folders.Grant([]), check=True)["update"]
    assert update["available"] == "yes" and update["restart_needed"] is True
    assert staging.load(root)["current"] == NEW


def test_download_installs_a_missing_root_through_windows_tls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A fresh Windows: the assets' host has a root Python cannot verify until Windows'
    # own TLS asks for it once; the retry then reads the (binary) body through urllib.
    import ssl
    import urllib.error
    import urllib.request

    primed: list[str] = []

    class Body:
        def __enter__(self) -> Body:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self) -> bytes:
            return b"\x00wheel"

    def urlopen(req: Any, timeout: float) -> Body:
        if not primed:
            raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "local issuer"))
        return Body()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(kit, "_windows_fetch", lambda url, timeout: primed.append(url))
    url = staging.DOWNLOAD.format(v=NEW, name="release.json")
    assert staging.download(url) == b"\x00wheel" and primed == [url]

    def offline(req: Any, timeout: float) -> Body:
        raise urllib.error.URLError(OSError("offline"))

    monkeypatch.setattr(urllib.request, "urlopen", offline)  # not a certificate: no retry
    monkeypatch.setattr(kit, "_windows_fetch", lambda url, timeout: pytest.fail("primed"))
    with pytest.raises(urllib.error.URLError):
        staging.download(url)
