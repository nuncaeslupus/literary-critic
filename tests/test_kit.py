import os
import re
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from conftest import bare_env

from litcritic import kit
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
        "print(doc_control.__file__); print(dc.run('capabilities', {})['api'])"
    )
    ran = subprocess.run(
        [sys.executable, "-I", "-S", "-c", probe],
        cwd=folder, capture_output=True, text=True, env=env, check=False,
    )  # fmt: skip
    assert ran.returncode == 0, ran.stderr
    where, api = ran.stdout.split()
    assert Path(where).resolve().is_relative_to(folder.resolve())
    assert api.startswith("1.")
