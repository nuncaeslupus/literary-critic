import json
import random
from pathlib import Path
from typing import Any

from docgen import odt

from litcritic import convert, corpus, dc, ingest
from litcritic.ingest import Draft, Para

EVIDENCE = Path(__file__).resolve().parent.parent / "status" / "evidence" / "doccontrol-T4.json"


def _read_back(path: Path) -> list[dict[str, Any]]:
    """Every non-empty paragraph as doc-control reads it: text plus its layout facts."""
    entries: list[dict[str, Any]] = []
    cursor = None
    while True:
        req: dict[str, Any] = {"doc": str(path), "limit": 1000}
        if cursor:
            req["cursor"] = cursor
        result = dc.run("text.normalized", req)
        for part in result["paragraphs"]:  # a long paragraph comes as several parts
            if entries and entries[-1]["at"] == part["at"]:
                entries[-1]["text"] += part["text"]
            else:
                entries.append({"at": part["at"], "text": part["text"]})
        cursor = result.get("_next")
        if not cursor:
            return [e for e in entries if e["text"]]


def _mismatches(draft: Draft, docx: bytes, tmp_path: Path, name: str) -> int:
    """Differences between the reader's paragraphs and what doc-control reads back."""
    path = tmp_path / f"{name}.docx"
    path.write_bytes(docx)
    entries = _read_back(path)
    if len(entries) != len(draft.paragraphs):
        return abs(len(entries) - len(draft.paragraphs)) + 1
    bad = 0
    for para, entry in zip(draft.paragraphs, entries, strict=True):
        facts = dc.run("para.get", {"doc": str(path), "at": entry["at"], "limit": 1})
        want = (para.text, para.heading, para.centered, para.page_break_before, para.blank_before)
        have = (
            entry["text"],
            facts["heading_level"] or 0,
            facts["centred"],
            facts["page_break_before"],
            facts["blank_before"],
        )
        bad += want != have
    return bad


def _sample(name: str) -> list[str]:
    text = corpus.get(name).path.read_text(encoding="utf-8")
    paras = [ingest.clean(p) for p in text.split("\n\n")]
    return [p for p in paras if p][:150]


def _inputs(name: str) -> dict[str, bytes]:
    paras = _sample(name)
    rng = random.Random(7)
    md: list[str] = []
    txt: list[str] = []
    for i, p in enumerate(paras):
        if i % 25 == 0:
            md.append(f"{'#' * (1 + i // 25 % 3)} {p[:40]}")
        md.append(p)
        txt.append(p)
        txt.append("\n" * rng.randrange(0, 3))
    return {
        ".md": "\n\n".join(md).encode(),
        ".txt": "\n".join(txt).encode(),
        ".odt": odt([(p, i % 30 == 0) for i, p in enumerate(paras)], seed=3),
    }


def test_convert_roundtrip_keeps_layout_facts(tmp_path: Path) -> None:
    total = checked = 0
    for name in ("marianela", "jekyll-hyde"):
        for suffix, data in _inputs(name).items():
            draft = ingest.read(Path(f"x{suffix}"), data)
            assert draft.paragraphs
            docx = convert.to_docx(Path(f"x{suffix}"), data)
            checked += len(draft.paragraphs)
            total += _mismatches(draft, docx, tmp_path, f"{name}{suffix[1:]}")
    # Page breaks have no source in .txt/.md/.odt readers: check them on a synthetic draft.
    synth = Draft(
        [
            Para("Title", heading=1, centered=True),
            Para("Body text", blank_before=2),
            Para("Next part", heading=2, page_break_before=True, blank_before=1),
            Para('A <b> & "c"', centered=True),
        ],
        "txt",
    )
    total += _mismatches(synth, convert._docx(synth), tmp_path, "synth")
    checked += len(synth.paragraphs)
    EVIDENCE.write_text(
        json.dumps(
            {
                "metric": "converted_layout_fact_mismatches",
                "value": total,
                "detail": f"{checked} paragraphs from both corpus texts as .txt, .md and .odt "
                "plus a synthetic draft; text, heading level, centring, page break before and "
                "blank lines read back through doc-control equal the reader's",
                "command": "uv run pytest tests/test_convert.py::"
                "test_convert_roundtrip_keeps_layout_facts",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    assert total == 0
