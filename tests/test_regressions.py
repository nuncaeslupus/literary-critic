"""Regression tests for defects found in code review."""

import subprocess
from pathlib import Path

import pytest

from litcritic import checklist, cli, guard, workspace


def _git_repo(path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def test_staged_non_ascii_and_spaced_paths_are_scanned(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "r")
    (repo / "notas ñ.md").write_text("Ramón here\n++Ramón again\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    files = guard.staged_changes(repo)
    assert list(files) == ["notas ñ.md"]
    assert "++Ramón again" in files["notas ñ.md"]
    assert len(guard.check(files, ["Ramon"])) == 1  # path clean; content flagged
    files_all = guard.tracked_files(repo)
    assert "Ramón" in files_all["notas ñ.md"]


def test_added_lines_skip_only_the_header() -> None:
    diff = "--- a/x\n+++ b/x\n@@ -0,0 +1,2 @@\n+++plus\n+text\n"
    assert guard._added_lines(diff) == "++plus\ntext"


def test_explicit_missing_terms_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        guard.read_terms([], [tmp_path / "missing.txt"])


def test_workspace_outside_home_is_registered_for_guard(tmp_path: Path) -> None:
    ws = workspace.create("n", "Title", "es", tmp_path / "drive")
    assert ws.guard_terms_file in guard.default_term_files(tmp_path)


def test_tilde_base_is_expanded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # where Windows looks
    monkeypatch.chdir(tmp_path)
    ws = workspace.create("n", "T", "en", Path("~/novels"))
    assert ws.root == (tmp_path / "novels" / "n").resolve()
    assert not (tmp_path / "~").exists()


def test_title_with_quotes_gives_valid_manifest(tmp_path: Path) -> None:
    ws = workspace.create("n", 'The "Big" One\\', "en", tmp_path)
    assert ws.manifest["title"] == 'The "Big" One\\'


def test_plan_rejects_bad_mode_and_disabled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prof = tmp_path / "p.toml"
    prof.write_text('mode = "reader_report"\ndisabled = ["nope.x"]\n', encoding="utf-8")
    assert cli.main(["checklist", "plan", "--profile", str(prof)]) == 2
    err = capsys.readouterr().err
    assert "unknown mode" in err and "unknown disabled" in err


def test_bad_types_reported_not_crashing(tmp_path: Path) -> None:
    (tmp_path / "areas").mkdir()
    (tmp_path / "traits.toml").write_text("[trait]\nx = 1\n", encoding="utf-8")
    (tmp_path / "metrics.toml").write_text("", encoding="utf-8")
    (tmp_path / "areas" / "a.toml").write_text(
        'id = "a"\ntitle = "t"\nstage = "Scene"\norder = "ten"\npurpose = "p"\n', encoding="utf-8"
    )
    cat = checklist.load(tmp_path)
    assert any("order an integer" in e for e in cat.errors)


def test_plan_refuses_invalid_catalogue(tmp_path: Path) -> None:
    (tmp_path / "areas").mkdir()
    assert cli.main(["checklist", "plan", "--root", str(tmp_path)]) == 2
