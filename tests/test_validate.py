import json
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


def test_invalid_finding_without_anchor_rejected() -> None:
    errors = _errors(FIXTURES / "invalid" / "finding.no-anchor.json")
    assert errors == ["$.anchors: needs at least 1 item(s)"]
    assert any(
        "missing anchors" in e
        for e in _errors(FIXTURES / "invalid" / "finding.missing-anchors.json")
    )


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


def test_list_errors_name_the_item() -> None:
    data = json.loads((FIXTURES / "valid" / "finding.list.json").read_text(encoding="utf-8"))
    data[1]["severity"] = "huge"
    assert validate.validate("finding", data) == [
        "$[1].severity: 'huge' not one of ['high', 'medium', 'low']"
    ]


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "action", str(FIXTURES / "valid" / "action.basic.json")]) == 0
    assert main(["validate", "action", str(FIXTURES / "invalid" / "action.no-locator.json")]) == 1
    assert "missing first_words" in capsys.readouterr().err
    broken = tmp_path / "x.json"
    broken.write_text("{", encoding="utf-8")
    assert main(["validate", "finding", str(broken)]) == 2
    unknown = FIXTURES / "invalid" / "finding.unknown-check.json"
    assert main(["validate", "finding", "--no-catalogue", str(unknown)]) == 0


def test_boolean_is_not_one() -> None:
    schema = validate.load_schema("register")
    data = {"schema_version": True, "kind": "motifs", "entries": []}
    assert validate.check(data, schema, schema) == ["$.schema_version: must be 1"]
