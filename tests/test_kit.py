import base64
import json
import os
import re
import ssl
import stat
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest
from conftest import bare_env

from litcritic import __version__, kit
from litcritic.cli import main
from litcritic.workspace import repo_root

ALLOWED = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}


def _frontmatter_problems(skill_md: str, folder: str) -> list[str]:
    """The checks Claude's Skill upload and skill-workshop's validator make."""
    m = re.match(r"---\n(.*?)\n---\n", skill_md, re.S)
    if not m:
        return ["no frontmatter"]
    keys = dict(re.findall(r"^([\w-]+):\s*(.*)$", m.group(1), re.M))
    problems = [f"unexpected key {k}" for k in keys if k not in ALLOWED]
    name, desc = keys.get("name", ""), keys.get("description", "")
    if name != folder or not re.fullmatch(r"[a-z0-9-]{1,64}", name):
        problems.append(f"bad name {name!r}")
    if not desc or len(desc) > 1024 or "<" in desc or ">" in desc:
        problems.append("bad description")
    return problems


def test_skill_zip_builds_and_validates(tmp_path: Path) -> None:
    errors: list[str] = []
    out, count = kit.build_skill(tmp_path / "skill.zip")
    names = zipfile.ZipFile(out).namelist()
    if count != len(names) or not all(n.startswith("litcritic/") for n in names):
        errors.append("everything must sit in the litcritic/ Skill folder")
    if [n for n in names if n.endswith("SKILL.md")] != ["litcritic/SKILL.md"]:
        errors.append("exactly one SKILL.md, at the top of the Skill folder")
    for required in (
        "lc.py",
        "prompts/05-setup.md",
        "prompts/80-live-word.md",
        "src/litcritic/cli.py",
    ):
        if f"litcritic/{required}" not in names:
            errors.append(f"missing {required}")
    if out.stat().st_size > kit.SKILL_MAX_BYTES:
        errors.append("over 30 MB")
    skill_md = zipfile.ZipFile(out).read("litcritic/SKILL.md").decode("utf-8")
    errors += _frontmatter_problems(skill_md, "litcritic")
    if "05-setup.md" not in skill_md or "lc.py" not in skill_md:
        errors.append("SKILL.md must route a new writer to setup and say how to run the tool")
    # The installed Skill folder is read-only: the tool still runs from it.
    folder = tmp_path / "skills"
    zipfile.ZipFile(out).extractall(folder)
    before = sorted(str(p) for p in folder.rglob("*"))
    for p in sorted(folder.rglob("*"), reverse=True):  # files first, then their folders
        p.chmod(stat.S_IRUSR | stat.S_IXUSR)
    folder.chmod(stat.S_IRUSR | stat.S_IXUSR)
    work = tmp_path / "work"
    work.mkdir()
    env = bare_env(tmp_path)
    result = subprocess.run(
        [sys.executable, "-I", str(folder / "litcritic" / "lc.py"), "doctor", "--home", "./home"],
        cwd=work,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if result.returncode != 0 or "ok" not in result.stdout:
        errors.append(f"doctor failed: {result.stdout} {result.stderr}")
    folder.chmod(stat.S_IRWXU)
    for p in folder.rglob("*"):
        p.chmod(stat.S_IRWXU)
    if sorted(str(p) for p in folder.rglob("*")) != before:
        errors.append("running the tool wrote into the Skill folder")
    skill_workshop_errors = len(errors)
    assert skill_workshop_errors == 0, errors


def test_repo_skill_passes_the_same_checks(tmp_path: Path) -> None:
    skill = repo_root() / kit.SKILL
    assert _frontmatter_problems(skill.read_text(encoding="utf-8"), "litcritic") == []
    assert main(["kit", "--skill", "--out", str(tmp_path / "s.zip")]) == 0
    assert os.path.getsize(tmp_path / "s.zip") > 0


def test_failed_skill_build_keeps_the_previous_zip(tmp_path: Path) -> None:
    out, _ = kit.build_skill(tmp_path / "skill.zip")
    good = out.read_bytes()
    saved = kit.SKILL_MAX_BYTES
    try:
        kit.SKILL_MAX_BYTES = 10
        with pytest.raises(kit.KitError, match="over"):
            kit.build_skill(out)
    finally:
        kit.SKILL_MAX_BYTES = saved
    assert out.read_bytes() == good and not list(tmp_path.glob("*.partial"))


def test_kit_zip_contains_doc_control(tmp_path: Path) -> None:
    for build in (kit.build, kit.build_skill):
        out, count = build(tmp_path / f"{build.__name__}.zip")
        names = zipfile.ZipFile(out).namelist()
        assert count == len(names)
        root = "litcritic/" if build is kit.build_skill else ""
        for needed in (
            "__init__.py",
            "cli.py",
            "py.typed",
            "LICENSE",
            "recipes/bundled/dashes-em.json",
        ):
            assert f"{root}src/doc_control/{needed}" in names
        assert not any("__pycache__" in n for n in names)


def test_kit_selftest_offline(tmp_path: Path) -> None:
    out, _ = kit.build(tmp_path / "kit.zip")
    folder = tmp_path / "unpacked"
    zipfile.ZipFile(out).extractall(folder)
    env = bare_env(tmp_path)
    # -I -S: no site-packages, so doc_control can only come from the unpacked kit
    doctor = subprocess.run(
        [sys.executable, "-I", "-S", "lc.py", "doctor", "--home", "./home"],
        cwd=folder, capture_output=True, text=True, env=env, check=False,
    )  # fmt: skip
    assert doctor.returncode == 0, doctor.stderr
    assert doctor.stdout.strip() == "ok"
    probe = (
        "import sys; sys.path.insert(0, 'src')\n"
        "import doc_control; from litcritic import dc\n"
        "print(doc_control.__file__); print(dc.run('server.capabilities', {})['api'])"
    )
    ran = subprocess.run(
        [sys.executable, "-I", "-S", "-c", probe],
        cwd=folder, capture_output=True, text=True, env=env, check=False,
    )  # fmt: skip
    assert ran.returncode == 0, ran.stderr
    where, api = ran.stdout.split()
    assert Path(where).resolve().is_relative_to(folder.resolve())
    assert api.startswith("1.")


def test_doctor_json_in_kit_reports_source_kit(tmp_path: Path) -> None:
    out, _ = kit.build(tmp_path / "kit.zip")
    folder = tmp_path / "unpacked"
    zipfile.ZipFile(out).extractall(folder)
    doctor = subprocess.run(
        [sys.executable, "-I", "-S", "lc.py", "doctor", "--json", "--no-network",
         "--home", "./home"],
        cwd=folder, capture_output=True, text=True, env=bare_env(tmp_path), check=False,
    )  # fmt: skip
    assert doctor.returncode == 0, doctor.stderr
    got = json.loads(doctor.stdout)
    assert got["problems"] == [] and got["source"] == "kit"
    assert got["version"] == __version__ and re.fullmatch(r"\d{4}-\d\d-\d\d", got["built"])


def test_doctor_json_version_sources(tmp_path: Path) -> None:
    out, _ = kit.build_skill(tmp_path / "skill.zip")
    zipfile.ZipFile(out).extractall(tmp_path / "s")
    assert kit.version_info(tmp_path / "s" / "litcritic")["source"] == "skill"
    assert kit.version_info(repo_root())["source"] == "checkout"
    bare = kit.version_info(tmp_path / "nothing")
    assert bare == {"version": __version__, "built": None, "source": "package"}


def test_doctor_json_cli_in_checkout(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["source"] == "checkout" and got["version"] == __version__


def test_version_matches_pyproject() -> None:
    meta = tomllib.loads((repo_root() / "pyproject.toml").read_text(encoding="utf-8"))
    assert meta["project"]["version"] == __version__


def _release(tag: str, bundle: bool = True) -> dict[str, object]:
    assets = [{"name": f"literary-critic-{tag[1:]}.mcpb"}] if bundle else []
    page = f"https://github.com/nuncaeslupus/literary-critic/releases/tag/{tag}"
    return {"tag_name": tag, "html_url": page, "assets": [*assets, {"name": "SHA256SUMS"}]}


@pytest.mark.parametrize(
    ("version", "source", "release", "want"),
    [
        ("0.1.0", "package", _release("v0.2.0"), "yes"),  # older, online
        ("0.2.0", "package", _release("v0.2.0"), "no"),  # current
        ("0.3.0", "package", _release("v0.2.0"), "no"),  # a development build is never out of date
        ("0.1.0", "package", None, "unknown"),  # offline or timed out
        ("0.1.0", "checkout", _release("v0.2.0"), "unknown"),  # a source checkout
        ("0.1.0", "package", _release("v0.2.0", bundle=False), "unknown"),  # tag, no .mcpb
    ],
    ids=["older", "equal", "newer", "offline", "checkout", "no-mcpb"],
)
def test_update_check_cases_no_false_alarm(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    version: str,
    source: str,
    release: dict[str, object] | None,
    want: str,
) -> None:
    monkeypatch.setattr(kit, "CACHE", tmp_path / "update.json")
    monkeypatch.setattr(kit, "_fetch_release", lambda timeout: release)
    got = kit.update_check({"version": version, "built": None, "source": source})
    assert got["update_available"] == want  # update_false_alarms == 0
    if want == "yes":
        assert got["latest"] == "0.2.0" and got["url"].endswith("/tag/v0.2.0")


def test_update_check_older_online_says_yes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(kit, "CACHE", tmp_path / "update.json")
    monkeypatch.setattr(kit, "_fetch_release", lambda timeout: _release("v9.9.9"))
    monkeypatch.setattr(
        kit, "version_info", lambda root=None: {"version": "0.1.0", "built": None, "source": "kit"}
    )
    assert main(["doctor", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["latest"] == "9.9.9" and got["update_available"] == "yes"
    # cached for the day: no second network read, unless forced
    monkeypatch.setattr(kit, "_fetch_release", lambda timeout: pytest.fail("fetched twice"))
    assert kit.update_check({"version": "0.1.0", "source": "kit"})["latest"] == "9.9.9"
    monkeypatch.setattr(kit, "_fetch_release", lambda timeout: _release("v9.9.10"))
    forced = kit.update_check({"version": "0.1.0", "source": "kit"}, force=True)
    assert forced["latest"] == "9.9.10"


def test_update_check_refetches_a_cache_older_than_this_copy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # the day's cache was read by an older copy; this one was updated since: read again
    monkeypatch.setattr(kit, "CACHE", tmp_path / "update.json")
    monkeypatch.setattr(kit, "_fetch_release", lambda timeout: _release("v0.1.2"))
    assert kit.update_check({"version": "0.1.2", "source": "kit"})["update_available"] == "no"
    monkeypatch.setattr(kit, "_fetch_release", lambda timeout: _release("v0.1.9"))
    got = kit.update_check({"version": "0.1.7", "source": "kit"})
    assert got["latest"] == "0.1.9" and got["update_available"] == "yes"


def test_update_check_no_network_and_failures_stay_silent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fetch = kit._fetch_release
    monkeypatch.setattr(kit, "CACHE", tmp_path / "update.json")
    monkeypatch.setattr(kit, "_fetch_release", lambda timeout: pytest.fail("network used"))
    assert main(["doctor", "--json", "--no-network"]) == 0
    assert json.loads(capsys.readouterr().out)["update_available"] == "unknown"

    def boom(url: str, timeout: float) -> None:
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert fetch(0.1) is None


def _cert_failure(url: object, timeout: float) -> None:
    raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "unable to get local issuer"))


def test_fetch_release_retries_a_certificate_failure_through_windows_tls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a fresh Windows: Python cannot verify GitHub until Windows' own TLS installs the root
    asked: list[tuple[str, float]] = []

    def windows(url: str, timeout: float) -> bytes:
        asked.append((url, timeout))
        return json.dumps(_release("v0.2.0")).encode("utf-8")

    monkeypatch.setattr(urllib.request, "urlopen", _cert_failure)
    monkeypatch.setattr(kit, "_windows_fetch", windows)
    assert kit._fetch_release(5.0) == _release("v0.2.0")
    assert asked[0][0] == kit.RELEASE_URL and 0 < asked[0][1] <= 5.0  # within the budget


def test_fetch_release_fallback_failures_stay_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _cert_failure)
    monkeypatch.setattr(kit, "_windows_fetch", lambda url, timeout: None)
    assert kit._fetch_release(5.0) is None
    monkeypatch.setattr(kit, "_windows_fetch", lambda url, timeout: b"not json")
    assert kit._fetch_release(5.0) is None

    def offline(url: object, timeout: float) -> None:
        raise urllib.error.URLError(OSError("offline"))

    monkeypatch.setattr(urllib.request, "urlopen", offline)  # not a certificate: no retry
    monkeypatch.setattr(kit, "_windows_fetch", lambda url, timeout: pytest.fail("retried"))
    assert kit._fetch_release(5.0) is None


def test_windows_fetch_runs_hidden_powershell_and_decodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[bytes]:
        seen.update(cmd=cmd, **kw)
        return subprocess.CompletedProcess(cmd, 0, base64.b64encode('{"ñ": 1}'.encode()) + b"\r\n")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", run)
    assert kit._windows_fetch(kit.RELEASE_URL, 4.5) == '{"ñ": 1}'.encode()
    cmd = seen["cmd"]
    assert isinstance(cmd, list) and cmd[0].lower().endswith("powershell.exe")
    assert "-NoProfile" in cmd and kit.RELEASE_URL in cmd[-1] and "-TimeoutSec 3" in cmd[-1]
    assert seen["timeout"] == 4.5

    def failed(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(cmd, 1, b"", b"error")

    monkeypatch.setattr(subprocess, "run", failed)
    assert kit._windows_fetch(kit.RELEASE_URL, 4.5) is None

    def slow(cmd: list[str], **kw: object) -> None:
        raise subprocess.TimeoutExpired(cmd, 4.5)

    monkeypatch.setattr(subprocess, "run", slow)
    assert kit._windows_fetch(kit.RELEASE_URL, 4.5) is None
    assert kit._windows_fetch(kit.RELEASE_URL, 0.5) is None  # no time left: no retry
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("not Windows"))
    assert kit._windows_fetch(kit.RELEASE_URL, 4.5) is None
