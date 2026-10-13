import ast
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from conftest import bare_env

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


# Spec §5: doc-control is the document layer. Only convert.py builds a .docx (for
# drafts held in memory); no module reads Word parts itself.
DOCX_PART = re.compile(r"(?:^|[\"'/])word/|wordprocessingml|\[Content_Types\]\.xml")
WRITER = "convert.py"


def _docx_part_literals(tree: ast.AST) -> tuple[list[str], list[str]]:
    """Word-part string literals in ``tree``: (all of them, those passed to a read call)."""
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    found, read = [], []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and DOCX_PART.search(node.value)
        ):
            found.append(node.value)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("read", "open", "getinfo")
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and DOCX_PART.search(node.args[0].value)
        ):
            read.append(node.args[0].value)
    return found, read


def docx_xml_modules() -> list[str]:
    offenders = []
    for path in sorted((repo_root() / "src" / "litcritic").rglob("*.py")):
        found, read = _docx_part_literals(ast.parse(path.read_text(encoding="utf-8")))
        if read or (found and path.name != WRITER):
            offenders.append(f"{path.name}: {sorted(set(read or found))}")
    return offenders


def test_no_module_reads_docx_parts() -> None:
    assert docx_xml_modules() == []


def test_docx_part_guard_catches_reads_and_writes() -> None:
    reader = ast.parse('zf.read("word/document.xml")')
    writer = ast.parse('zf.writestr("word/styles.xml", x)')
    assert _docx_part_literals(reader) == (["word/document.xml"], ["word/document.xml"])
    assert _docx_part_literals(writer) == (["word/styles.xml"], [])
    assert _docx_part_literals(ast.parse('"""Writes ``word/`` parts."""')) == ([], [])


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
    env = bare_env(tmp_path)
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
