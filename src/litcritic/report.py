"""Reader report: the assessment an agency or a publisher's reader writes.

The LLM writes its judgments to ``analysis/report.json`` (schema ``report``);
the synopsis comes from ``analysis/synopsis.md``; strengths and weaknesses come
from the findings, each with a findable place; manuscript facts come from the
structure and metrics. ``render`` assembles ``analysis/reader-report.md`` with
every required section, in the novel's language.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from litcritic import locate, query, rounds, structure, validate, workspace
from litcritic.codex import Codex, CodexError, Item

SECTIONS = ("summary", "synopsis", "strengths", "weaknesses", "market", "facts", "verdict")
MAX_WEAKNESSES = 10
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
        "notes": "Notas",
        "verdicts": {
            "recommend": "Recomendado",
            "consider": "A considerar",
            "pass": "No recomendado",
        },
        "facts_lines": [
            "Palabras (sin preliminares)",
            "Capítulos",
            "Escenas",
            "Legibilidad (Fernández-Huerta)",
        ],
        "genre": "Género",
        "readership": "Lectores",
        "comparables": "Comparables",
        "more": "y {n} más en el análisis completo",
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
        "notes": "Notes",
        "verdicts": {"recommend": "Recommend", "consider": "Consider", "pass": "Pass"},
        "facts_lines": [
            "Words (without front matter)",
            "Chapters",
            "Scenes",
            "Readability (Flesch)",
        ],
        "genre": "Genre",
        "readership": "Readership",
        "comparables": "Comparables",
        "more": "and {n} more in the full analysis",
        "none": "(no data)",
    },
}


class ReportError(Exception):
    """The report cannot be assembled."""


def render(ws_root: Path, version: str | None = None) -> tuple[Path, dict[str, bool]]:
    """Write the report; returns its path and which required sections have real content."""
    version = version or structure.latest_version(ws_root)
    judgment = rounds.load_json(ws_root / "analysis" / "report.json", None)
    if judgment is None:
        raise ReportError("no analysis/report.json yet; write it with the reader-report procedure")
    errors = validate.validate("report", judgment)
    if errors:
        raise ReportError("report.json is invalid: " + "; ".join(errors[:5]))
    try:
        cx = Codex(ws_root)
    except CodexError as exc:
        raise ReportError(f"{exc}; strengths and weaknesses come from its issues") from exc
    lang = rounds.language(ws_root)
    h = HEADINGS.get(lang, HEADINGS["en"])
    title = (
        str(workspace.Workspace(ws_root).manifest.get("title", ""))
        if (ws_root / workspace.MANIFEST).is_file()
        else ""
    )
    synopsis_file = ws_root / "analysis" / "synopsis.md"
    synopsis = synopsis_file.read_text(encoding="utf-8").strip() if synopsis_file.is_file() else ""
    ix = query.load(ws_root, version)
    loc = locate.LocatorBuilder(ix, locate.load_meta(ws_root, cx.draft), lang)

    def lines_for(items: list[Item]) -> list[str]:
        return [line for i in items if (line := rounds.located_line(cx, i, loc, lang))]

    strengths = lines_for(rounds.live(cx, "strength"))
    problems = sorted(
        rounds.live(cx, "problem"),
        key=lambda i: (
            -rounds.SEVERITY.get(str(i.fields.get("severity")), 0),
            -float(i.fields.get("confidence", 1.0)),
        ),
    )
    weaknesses = lines_for(problems)
    if len(weaknesses) > MAX_WEAKNESSES:
        extra = len(weaknesses) - MAX_WEAKNESSES
        weaknesses = [*weaknesses[:MAX_WEAKNESSES], f"- … {h['more'].format(n=extra)}"]
    chapters = [c for c in ix.chapters if c.get("reason") != "front"]
    words = sum(c["words"] for c in chapters)
    metrics = rounds.load_json(ws_root / "metrics" / f"{version}.json", {}).get("metrics", {})
    readability_id = "readability_fernandez_huerta" if lang == "es" else "readability_flesch"
    readability = metrics.get(readability_id, {}).get("book")
    facts = [
        f"- {h['facts_lines'][0]}: {words}",
        f"- {h['facts_lines'][1]}: {len(chapters)}",
        f"- {h['facts_lines'][2]}: {sum(len(c.get('scenes', [])) for c in chapters)}",
        f"- {h['facts_lines'][3]}: {readability if readability is not None else h['none']}",
    ]
    verdict = [f"**{h['verdicts'][judgment['verdict']]}.** {judgment['verdict_reason']}"]
    if judgment.get("notes"):
        verdict += ["", f"**{h['notes']}:** {judgment['notes']}"]
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
        "verdict": verdict,
    }
    complete = {name: bool(lines) for name, lines in body.items()}
    complete["facts"] = readability is not None  # run `lc metrics` first
    out_lines = [f"# {h['title']}" + (f": {title}" if title else ""), ""]
    for name in SECTIONS:
        out_lines += [f"## {h[name]}", "", *(body[name] or [h["none"]]), ""]
    out = ws_root / "analysis" / "reader-report.md"
    out.write_text("\n".join(out_lines), encoding="utf-8")
    return out, complete
