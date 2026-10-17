import importlib.util
import json
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
