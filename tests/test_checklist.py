from pathlib import Path

from litcritic import checklist
from litcritic.workspace import repo_root

TRAITS = '[trait.nested_narration]\ndescription = "x"\n'
METRICS = '[metric.words_per_chapter]\ndescription = "x"\nunit = "words"\nstatus = "planned"\n'
SEV = 'severity = { high = "h", medium = "m", low = "l" }\n'


def _cat(tmp_path: Path, area: str) -> checklist.Catalogue:
    (tmp_path / "areas").mkdir()
    (tmp_path / "traits.toml").write_text(TRAITS, encoding="utf-8")
    (tmp_path / "metrics.toml").write_text(METRICS, encoding="utf-8")
    (tmp_path / "areas" / "10-a.toml").write_text(area, encoding="utf-8")
    return checklist.load(tmp_path)


AREA_HEAD = 'id = "arch"\ntitle = "A"\nstage = "developmental"\norder = 10\npurpose = "p"\n'


def _check(cid: str, extra: str = "") -> str:
    return (
        f'[[check]]\nid = "{cid}"\ntitle = "t"\nquestion = "q"\nlook_for = ["s"]\n'
        f'method = "llm"\ninputs = ["L1"]\nevidence = "e"\n{SEV}{extra}'
    )


def test_valid_area_loads(tmp_path: Path) -> None:
    cat = _cat(tmp_path, AREA_HEAD + _check("arch.one"))
    assert cat.errors == []
    assert [c.id for c in cat.checks] == ["arch.one"]


def test_bad_id_unknown_input_and_missing_severity(tmp_path: Path) -> None:
    bad = (
        '[[check]]\nid = "other.x"\ntitle = "t"\nquestion = "q"\nlook_for = ["s"]\n'
        'method = "llm"\ninputs = ["L9"]\nevidence = "e"\n'
    )
    errs = " ".join(_cat(tmp_path, AREA_HEAD + bad).errors)
    assert "id must be" in errs and "unknown value 'L9'" in errs and "severity" in errs


def test_script_check_requires_metrics(tmp_path: Path) -> None:
    area = AREA_HEAD + _check("arch.one").replace('method = "llm"', 'method = "script"')
    assert any("must name metrics" in e for e in _cat(tmp_path, area).errors)


def test_duplicate_ids_reported(tmp_path: Path) -> None:
    cat = _cat(tmp_path, AREA_HEAD + _check("arch.one") + _check("arch.one"))
    assert any("duplicate id" in e for e in cat.errors)


def ids(cs: list[checklist.Check]) -> list[str]:
    return [c.id for c in cs]


def test_select_gates_by_trait_mode_and_disabled(tmp_path: Path) -> None:
    area = (
        AREA_HEAD
        + _check("arch.always")
        + _check("arch.gated", 'applies_when = ["nested_narration"]\n')
        + _check("arch.report", 'modes = ["reader-report"]\n')
    )
    cat = _cat(tmp_path, area)
    assert cat.errors == []
    assert ids(checklist.select(cat, set())) == ["arch.always"]
    assert ids(checklist.select(cat, {"nested_narration"})) == ["arch.always", "arch.gated"]
    assert ids(checklist.select(cat, set(), "reader-report")) == ["arch.always", "arch.report"]
    assert ids(checklist.select(cat, set(), disabled={"arch.always"})) == []


def test_repo_catalogue_is_valid() -> None:
    cat = checklist.load(repo_root() / "checklist")
    assert cat.errors == []
    assert len(cat.areas) >= 20
    stages = {c.stage for c in cat.checks}
    assert stages == set(checklist.STAGES)
