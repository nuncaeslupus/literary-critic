from pathlib import Path

import pytest

from litcritic import codex, corpus, query, report
from litcritic import spans as spanlib
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
    _issue(root, "c01.s1.p2", "Apertura sólida.", "strength", "high")
    _issue(root, "c04.s1", "Centro lento.", "problem", "medium")


def _issue(root: Path, unit: str, why: str, kind: str, severity: str) -> str:
    cx = codex.Codex(root) if (root / "codex").is_dir() else codex.Codex.init(root, "v001")
    ix = query.load(root)
    i = query.paragraph_range(ix, unit).start
    text = spanlib.Text(ix.paragraphs, ix.anchors, "v001")
    span = spanlib.make(text, "v001", ix.anchors[i], 0, ix.anchors[i], len(ix.paragraphs[i]))
    fields = {"level": "scene", "severity": severity, "kind": kind, "why": why, "confidence": 0.8}
    return cx.add("issue", why, fields, [span]).id


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
    cx = codex.Codex(ws)
    strength = next(i for i in cx.of_type("issue") if i.fields["kind"] == "strength")
    cx.update(strength.id, status="needs_reread")  # its passage changed: left out
    for k in range(3, 18):
        _issue(ws, f"c{k:02d}.s1", f"Punto {k}.", "problem", "medium")
    text = report.render(ws)[0].read_text(encoding="utf-8")
    assert "Apertura sólida." not in text
    assert "y 6 más en el análisis completo" in text  # 16 weaknesses, 10 shown
    assert "(c0" not in text  # never a raw anchor
    (ws / "analysis" / "report.json").write_text('{"not": "a report"}', encoding="utf-8")
    with pytest.raises(report.ReportError, match="invalid"):
        report.render(ws)
