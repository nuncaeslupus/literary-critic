import json
from pathlib import Path

import pytest

from litcritic import corpus, report
from litcritic.cli import main


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "work.toml").write_text(
        'slug = "ws"\ntitle = "Marianela"\nlanguage = "es"\n', encoding="utf-8"
    )
    assert main(["ingest", str(corpus.get("marianela").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    assert main(["metrics", "--workspace", str(root)]) == 0
    return root


def _write(root: Path) -> None:
    analysis = root / "analysis"
    analysis.mkdir(exist_ok=True)
    fixture = Path(__file__).parent / "fixtures" / "schemas" / "valid" / "report.basic.json"
    (analysis / "report.json").write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    (analysis / "synopsis.md").write_text("Un viajero se pierde al anochecer.", encoding="utf-8")
    base = {
        "schema_version": 1,
        "evidence": [{"anchor": "c01.s1.p2", "quote": "x"}],
        "confidence": 0.8,
        "effort": "M",
        "status": "open",
    }
    findings = [
        base
        | {
            "id": "F1",
            "check_id": "scene-craft.purpose",
            "anchors": ["c01.s1.p2"],
            "severity": "high",
            "kind": "strength",
            "explanation": "Apertura sólida.",
        },
        base
        | {
            "id": "F2",
            "check_id": "scene-craft.purpose",
            "anchors": ["c04.s1"],
            "severity": "medium",
            "kind": "problem",
            "explanation": "Centro lento.",
        },
    ]
    (analysis / "findings.json").write_text(json.dumps(findings), encoding="utf-8")


def test_reader_report_template_sections(ws: Path) -> None:
    _write(ws)
    out, complete = report.render(ws)
    assert all(complete.values()) and set(complete) == set(report.SECTIONS)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Informe de lectura: Marianela")
    for name in report.SECTIONS:
        assert f"## {report.HEADINGS['es'][name]}" in text
    assert "**A considerar.**" in text and "Apertura sólida." in text and "Capítulo 4" in text
    assert "Palabras (sin preliminares): " in text and "Legibilidad (Fernández-Huerta): " in text


def test_missing_or_invalid_report(ws: Path) -> None:
    with pytest.raises(report.ReportError, match=r"no analysis/report\.json"):
        report.render(ws)
    _write(ws)
    (ws / "analysis" / "report.json").write_text('{"schema_version": 1}', encoding="utf-8")
    with pytest.raises(report.ReportError, match="invalid"):
        report.render(ws)
    assert main(["report", "--workspace", str(ws)]) == 1


def test_review_regressions(ws: Path) -> None:
    _write(ws)
    findings = json.loads((ws / "analysis" / "findings.json").read_text(encoding="utf-8"))
    findings[0]["status"] = "stale"
    extra = [dict(findings[1]) | {"id": f"F{k}", "anchors": [f"c{k:02d}.s1"]} for k in range(3, 18)]
    (ws / "analysis" / "findings.json").write_text(
        json.dumps([*findings, *extra]), encoding="utf-8"
    )
    text = report.render(ws)[0].read_text(encoding="utf-8")
    assert "Apertura sólida." not in text  # stale strength left out
    assert "y 6 más en el análisis completo" in text  # 16 weaknesses, 10 shown
    assert "(c0" not in text  # never a raw anchor
    (ws / "analysis" / "findings.json").write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(report.ReportError, match="invalid"):
        report.render(ws)
