"""Reader report: the assessment an agency or a publisher's reader writes.

The LLM writes its judgments to ``analysis/report.json`` (schema ``report``);
the synopsis comes from ``analysis/synopsis.md``; strengths and weaknesses come
from the findings, with evidence locations; manuscript facts come from the
structure and metrics. ``render`` assembles ``analysis/reader-report.md`` with
every required section, in the novel's language.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from litcritic import locate, query, rounds, structure, validate

SECTIONS = ("summary", "synopsis", "strengths", "weaknesses", "market", "facts", "verdict")
HEADINGS: dict[str, dict[str, Any]] = {
    "es": {
        "title": "Informe de lectura",
        "summary": "Resumen",
        "synopsis": "Sinopsis",
        "strengths": "Puntos fuertes",
        "weaknesses": "Puntos débiles",
        "market": "Mercado y lectores",
        "facts": "Datos del manuscrito",
        "verdict": "Veredicto",
        "verdicts": {
            "recommend": "Recomendado",
            "consider": "A considerar",
            "pass": "No recomendado",
        },
        "facts_lines": ["Palabras", "Capítulos", "Escenas", "Legibilidad (Fernández-Huerta)"],
        "genre": "Género",
        "readership": "Lectores",
        "comparables": "Comparables",
        "none": "(sin datos)",
    },
    "en": {
        "title": "Reader report",
        "summary": "Summary",
        "synopsis": "Synopsis",
        "strengths": "Strengths",
        "weaknesses": "Weaknesses",
        "market": "Market and readership",
        "facts": "Manuscript facts",
        "verdict": "Verdict",
        "verdicts": {"recommend": "Recommend", "consider": "Consider", "pass": "Pass"},
        "facts_lines": ["Words", "Chapters", "Scenes", "Readability (Flesch)"],
        "genre": "Genre",
        "readership": "Readership",
        "comparables": "Comparables",
        "none": "(no data)",
    },
}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class ReportError(Exception):
    """The report cannot be assembled."""


def _json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def render(ws_root: Path, version: str | None = None) -> tuple[Path, dict[str, bool]]:
    """Write the report; returns its path and which required sections have content."""
    version = version or structure.latest_version(ws_root)
    judgment = _json(ws_root / "analysis" / "report.json", None)
    if judgment is None:
        raise ReportError("no analysis/report.json yet; write it with the reader-report procedure")
    errors = validate.validate("report", judgment)
    if errors:
        raise ReportError("report.json is invalid: " + "; ".join(errors[:5]))
    lang = rounds.language(ws_root)
    h = HEADINGS.get(lang, HEADINGS["en"])
    title = str(_manifest(ws_root).get("title", ""))
    synopsis_file = ws_root / "analysis" / "synopsis.md"
    synopsis = synopsis_file.read_text(encoding="utf-8").strip() if synopsis_file.is_file() else ""
    findings = _json(ws_root / "analysis" / "findings.json", [])
    ix = query.load(ws_root, version)
    loc = locate.LocatorBuilder(ix, locate.load_meta(ws_root, version), lang)

    def located(f: dict[str, Any]) -> str:
        try:
            where = locate.describe(
                loc.locate(ix.anchors[query.paragraph_range(ix, f["anchors"][0]).start]), lang
            )
        except KeyError:
            where = f["anchors"][0]
        return f"- {f.get('explanation', '')} ({where})"

    strengths = [
        located(f) for f in findings if f["kind"] == "strength" and f["status"] != "rejected"
    ]
    problems = sorted(
        (f for f in findings if f["kind"] == "problem" and f["status"] in ("open", "accepted")),
        key=lambda f: (SEVERITY_ORDER.get(f["severity"], 3), -float(f["confidence"])),
    )
    weaknesses = [located(f) for f in problems[:10]]
    struct = _json(ws_root / "index" / version / "structure.json", {})
    chapters = [c for c in struct.get("chapters", []) if c.get("reason") != "front"]
    metrics = _json(ws_root / "metrics" / f"{version}.json", {}).get("metrics", {})
    readability_id = "readability_fernandez_huerta" if lang == "es" else "readability_flesch"
    readability = metrics.get(readability_id, {}).get("book", h["none"])
    facts = [
        f"- {h['facts_lines'][0]}: {sum(len(p.split()) for p in ix.paragraphs)}",
        f"- {h['facts_lines'][1]}: {len(chapters)}",
        f"- {h['facts_lines'][2]}: {sum(len(c.get('scenes', [])) for c in chapters)}",
        f"- {h['facts_lines'][3]}: {readability}",
    ]
    body = {
        "summary": [f"**{h['genre']}:** {judgment['genre']}", "", judgment["logline"]],
        "synopsis": [synopsis] if synopsis else [],
        "strengths": strengths,
        "weaknesses": weaknesses,
        "market": [
            f"**{h['readership']}:** {judgment['readership']}",
            "",
            f"**{h['comparables']}:** " + "; ".join(judgment["comparables"]),
            "",
            judgment["market_fit"],
        ],
        "facts": facts,
        "verdict": [f"**{h['verdicts'][judgment['verdict']]}.** {judgment['verdict_reason']}"],
    }
    complete = {name: bool(lines) for name, lines in body.items()}
    out_lines = [f"# {h['title']}" + (f": {title}" if title else ""), ""]
    for name in SECTIONS:
        out_lines += [f"## {h[name]}", "", *(body[name] or [h["none"]]), ""]
    out = ws_root / "analysis" / "reader-report.md"
    out.write_text("\n".join(out_lines), encoding="utf-8")
    return out, complete


def _manifest(ws_root: Path) -> dict[str, Any]:
    f = ws_root / "workspace.toml"
    return tomllib.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
