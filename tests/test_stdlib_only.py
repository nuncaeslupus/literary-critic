import ast
import subprocess
import sys
import zipfile
from pathlib import Path

from litcritic import kit
from litcritic.workspace import repo_root


def third_party_imports() -> list[str]:
    found = []
    for path in sorted((repo_root() / "src" / "litcritic").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                if top != "litcritic" and top not in sys.stdlib_module_names:
                    found.append(f"{path.name}: {name}")
    return found


def test_runtime_is_stdlib_only() -> None:
    assert third_party_imports() == []


def test_kit_runs_on_its_own(tmp_path: Path) -> None:
    out, count = kit.build(tmp_path / "kit.zip")
    names = zipfile.ZipFile(out).namelist()
    for required in (
        "START_HERE.md",
        "lc.py",
        "LICENSE",
        "src/litcritic/cli.py",
        "prompts/00-guide.md",
    ):
        assert required in names
    assert any(n.startswith("schemas/") for n in names) and any(
        n.startswith("checklist/areas/") for n in names
    )
    assert "src/litcritic/data/lexicon_es.toml" in names and count == len(names)
    assert not any("__pycache__" in n or n.startswith(("tests/", "corpus/")) for n in names)
    folder = tmp_path / "unpacked"
    zipfile.ZipFile(out).extractall(folder)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-I", "lc.py", "doctor"],
        cwd=folder,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
    checked = subprocess.run(
        [sys.executable, "-I", "lc.py", "checklist", "validate"],
        cwd=folder,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
