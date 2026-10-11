from pathlib import Path

import pytest

from litcritic import checklist, validate
from litcritic.cli import main
from litcritic.workspace import repo_root

FIXTURES = Path(__file__).parent / "fixtures" / "schemas"
CATALOGUE = checklist.load(repo_root() / "checklist")


def _kind(path: Path) -> str:
    return path.name.split(".")[0]


def _errors(path: Path) -> list[str]:
    kind = _kind(path)
    return validate.validate(kind, validate.load_file(kind, path), CATALOGUE)


@pytest.mark.parametrize("path", sorted((FIXTURES / "valid").iterdir()), ids=lambda p: p.name)
def test_valid_fixtures_pass(path: Path) -> None:
    assert _errors(path) == []


@pytest.mark.parametrize("path", sorted((FIXTURES / "invalid").iterdir()), ids=lambda p: p.name)
def test_invalid_fixtures_fail(path: Path) -> None:
    assert _errors(path) != []


def test_every_kind_has_valid_and_invalid_fixtures() -> None:
    for group in ("valid", "invalid"):
        assert {_kind(p) for p in (FIXTURES / group).iterdir()} == set(validate.KINDS)


def test_schema_validity_on_fixtures_metric() -> None:
    fixtures = [(p, True) for p in (FIXTURES / "valid").iterdir()]
    fixtures += [(p, False) for p in (FIXTURES / "invalid").iterdir()]
    correct = sum((_errors(p) == []) == ok for p, ok in fixtures)
    assert correct / len(fixtures) == 1.0


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "report", str(FIXTURES / "valid" / "report.basic.json")]) == 0
    bad = FIXTURES / "invalid" / "report.bad-verdict.json"
    assert main(["validate", "report", str(bad)]) == 1
    assert capsys.readouterr().err
    broken = tmp_path / "x.json"
    broken.write_text("{", encoding="utf-8")
    assert main(["validate", "report", str(broken)]) == 2
    unknown = FIXTURES / "invalid" / "profile.unknown-trait.toml"
    assert main(["validate", "profile", "--no-catalogue", str(unknown)]) == 0


def test_boolean_is_not_one() -> None:
    schema = validate.load_schema("report")
    assert any("must be 1" in e for e in validate.check({"schema_version": True}, schema, schema))
