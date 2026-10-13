import ast
import subprocess
import sys
import zipfile
from pathlib import Path

from litcritic import kit
from litcritic.workspace import repo_root

# AGENTS.md rule 9: stdlib plus doc-control, imported only by the adapter.
ALLOWED = ("doc_control",)


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
                if top not in ("litcritic", *ALLOWED) and top not in sys.stdlib_module_names:
                    found.append(f"{path.name}: {name}")
                if top in ALLOWED and path.name != "dc.py":
                    found.append(f"{path.name}: {name} (only dc.py may import it)")
    return found


def test_runtime_deps_only_doc_control() -> None:
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
        [sys.executable, "-I", "lc.py", "doctor", "--home", "./home"],
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
    for argv in (
        ["init", "nov", "--title", "T", "--language", "es", "--home", "./home"],
        ["pack", "--workspace", "nov", "--home", "./home"],
    ):
        ran = subprocess.run(
            [sys.executable, "-I", "lc.py", *argv],
            cwd=folder,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert ran.returncode == 0, ran.stderr


def test_kit_skips_its_own_output(tmp_path: Path) -> None:
    inside = repo_root() / "schemas" / "kit-test.zip"
    try:
        out, count = kit.build(inside)
        names = zipfile.ZipFile(out).namelist()
        assert "schemas/kit-test.zip" not in names and count == len(names)
    finally:
        inside.unlink(missing_ok=True)


def test_doctor_flags_workspaces_inside_the_checkout() -> None:
    problems = kit.doctor(repo_root() / "home")
    assert any("cannot live" in p for p in problems)
