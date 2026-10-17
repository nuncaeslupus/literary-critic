import importlib.util
import json
import re
import shutil
import sys
import tomllib
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pack_mcpb = _script("pack_mcpb")


def test_pack_mcpb_contents_and_manifest(tmp_path: Path) -> None:
    out = pack_mcpb.pack(tmp_path)
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    assert out.name == f"literary-critic-{version}.mcpb"
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        manifest = json.loads(z.read("manifest.json"))
        bundled = tomllib.loads(z.read("pyproject.toml").decode("utf-8"))
    assert {"manifest.json", "launch.py", "pyproject.toml", "uv.lock", "icon.png"} <= names
    assert {"src/litcritic/mcp.py", "prompts/01-chat-guide.md", "LICENSE"} <= names
    assert not any(n.split("/")[0] in {".venv", "venv", "server"} for n in names)
    assert not any("__pycache__" in n or n.startswith(("tests/", "corpus/")) for n in names)

    assert manifest["manifest_version"] == "0.4"
    assert manifest["server"]["type"] == "uv"
    assert manifest["server"]["entry_point"] == "launch.py"
    assert manifest["version"] == version
    settings = manifest["user_config"]
    assert set(settings) == {"novels_folder", "auto_update"}
    folder, auto = settings["novels_folder"], settings["auto_update"]
    assert folder["type"] == "directory" and folder["multiple"]
    assert auto["type"] == "boolean" and auto["default"] is True
    env = manifest["server"]["mcp_config"]["env"]
    assert env == {"LC_AUTO_UPDATE": "${user_config.auto_update}", "DOC_CONTROL_STORE": "appdata"}

    # The app's uv installs the lock's runtime packages only: no dev tools, pywin32 included.
    assert bundled["tool"]["uv"]["default-groups"] == []
    assert any(d.startswith("doc-control[live]") for d in bundled["project"]["dependencies"])


def test_pack_mcpb_refuses_a_stamped_version_that_differs(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(ROOT / "extension", root / "extension")
    shutil.copy(ROOT / "pyproject.toml", root / "pyproject.toml")
    path = root / "extension" / "manifest.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "version": "9.9.9"}))
    with pytest.raises(pack_mcpb.PackError, match=r"9\.9\.9"):
        pack_mcpb.manifest(root)


def test_launch_drops_unset_folder_placeholder() -> None:
    spec = importlib.util.spec_from_file_location("launch", ROOT / "extension" / "launch.py")
    assert spec and spec.loader
    launch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    assert launch.folders(["${user_config.novels_folder}"]) == []
    assert launch.folders([r"C:\Novels", "", r"D:\More"]) == [r"C:\Novels", r"D:\More"]


smoke_mcpb = _script("smoke_mcpb")


def test_smoke_versions_differ_from_lock_fails() -> None:
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    locked = smoke_mcpb.lock_versions(lock)
    installed = {"doc_control": locked["doc-control"], "literary-critic": pack_mcpb.version(ROOT)}
    assert smoke_mcpb.version_problems(installed, lock) == []
    drifted = smoke_mcpb.version_problems({**installed, "doc_control": "0.0.1"}, lock)
    assert drifted == [f"doc-control 0.0.1 installed, lock has {locked['doc-control']}"]
    assert smoke_mcpb.version_problems({"left-pad": "1.0"}, lock) == [
        "left-pad 1.0 installed, lock has nothing",
        "doc-control not installed",
    ]


doccontrol_bump = _script("doccontrol_bump")


def test_bump_in_range_pr_out_of_range_issue() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pinned = doccontrol_bump.pinned_range(pyproject)
    current = doccontrol_bump.locked((ROOT / "uv.lock").read_text(encoding="utf-8"))
    assert doccontrol_bump.decide(current, current, *pinned) == "none"
    low, high = "0.8.3", "0.9"
    assert doccontrol_bump.decide("0.8.3", "0.8.4", low, high) == "pr"
    assert doccontrol_bump.decide("0.8.3", "0.9.0", low, high) == "issue"
    assert doccontrol_bump.decide("0.8.3", "1.0", low, high) == "issue"
    assert doccontrol_bump.decide("0.8.3", "0.8.3", low, high) == "none"
    assert doccontrol_bump.decide("0.8.4", "0.8.3", low, high) == "none"
    bumped, new = doccontrol_bump.bump_patch('[project]\nname = "x"\nversion = "0.1.9"\n')
    assert new == "0.1.10" and 'version = "0.1.10"' in bumped
    init = '"""Doc."""\n\n__version__ = "0.1.9"\n'
    assert doccontrol_bump.set_dunder_version(init, new).endswith('__version__ = "0.1.10"\n')


def test_package_version_matches_pyproject() -> None:
    from litcritic import __version__

    assert __version__ == pack_mcpb.version(ROOT)  # else a release calls itself outdated


def test_release_assets_requirements_hashed(tmp_path: Path) -> None:
    ra = _script("release_assets")
    wheel = tmp_path / "literary_critic-1.2.3-py3-none-any.whl"
    wheel.write_bytes(b"wheel bytes")
    exported = (
        "colorama==0.4.6 ; sys_platform == 'win32' \\\n"
        "    --hash=sha256:aaaa \\\n    --hash=sha256:bbbb\n"
        "doc-control==1.0 \\\n    --hash=sha256:cccc\n"
    )
    text = ra.requirements_text(exported, wheel)
    entries = [e for e in re.split(r"\n(?=\S)", text.strip()) if e]
    assert len(entries) == 3
    assert all("--hash=sha256:" in e for e in entries)
    own = entries[-1]
    assert own.startswith("literary-critic @ ./" + wheel.name)
    assert f"--hash=sha256:{ra.sha256(wheel)}" in own
    # pip joins a line ending in a backslash with the next; a literal "\n" breaks the path
    logical = text.replace("\\\n", " ").splitlines()
    assert "\\n" not in text and len(logical) == 3
    assert logical[-1].split()[:3] == ["literary-critic", "@", "./" + wheel.name]

    with pytest.raises(SystemExit):
        ra.requirements_text("doc-control==1.0\n", wheel)

    meta = json.loads(ra.release_json("1.2.3", True))
    assert meta == {"version": "1.2.3", "reinstall": True}
    assert ra.changed_since(None) is False
