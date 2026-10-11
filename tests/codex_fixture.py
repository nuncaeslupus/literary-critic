"""A hand-built Codex for the public-domain corpus text (Marianela).

Curated rules, not a real analysis: dialogue lines are attributed where the
text names the speaker right after a speech verb; storylines and setups are
chosen by keyword. Tests use it to check named questions end to end.
"""

from __future__ import annotations

import re
from pathlib import Path

from litcritic import codex, corpus, query
from litcritic import spans as spanlib
from litcritic.cli import main

SPEECH = re.compile(
    r"--\s*(?:dijo|preguntó|exclamó|respondió|contestó|añadió|gritó|repuso|murmuró)\s+"
    r"(?:la |el )?(Nela|Mariquilla|Pablo|Teodoro|Florentina|Sofía|Carlos|Celipín)\b"
)
CHARACTERS = {
    "nela": ("Nela", ["Marianela", "Mariquilla"]),
    "pablo": ("Pablo", []),
    "teodoro": ("Teodoro Golfín", ["Teodoro"]),
    "carlos": ("Carlos Golfín", ["Carlos"]),
    "sofia": ("Sofía", []),
    "florentina": ("Florentina", []),
    "celipin": ("Celipín", []),
}
SPEAKER = {
    "Nela": "nela",
    "Mariquilla": "nela",
    "Pablo": "pablo",
    "Teodoro": "teodoro",
    "Florentina": "florentina",
    "Sofía": "sofia",
    "Carlos": "carlos",
    "Celipín": "celipin",
}


def whole(text: spanlib.Text, i: int) -> spanlib.Span:
    a = text.anchors[i]
    return spanlib.make(text, text.draft, a, 0, a, len(text.paragraphs[i]))


def build(root: Path) -> dict[str, str]:
    """Ingest, anchor and fill a Codex in ``root``; returns names -> item ids."""
    (root / "work.toml").write_text('slug = "marianela"\nlanguage = "es"\n', "utf-8")
    assert main(["ingest", str(corpus.get("marianela").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    cx = codex.Codex.init(root, "v001")
    ix = query.load(root, "v001")
    text = spanlib.Text(ix.paragraphs, ix.anchors, "v001")
    ids: dict[str, str] = {}
    for key, (name, aliases) in CHARACTERS.items():
        fields = {"kind": "character", "name": name, **({"aliases": aliases} if aliases else {})}
        ids[key] = cx.add("entity", name, fields).id
    ids["socartes"] = cx.add("entity", "The mines.", {"kind": "place", "name": "Socartes"}).id
    lines = []
    for i, p in enumerate(text.paragraphs):
        m = SPEECH.search(p) if p.startswith("--") else None
        if not m:
            continue
        speaker = SPEAKER[m.group(1)]
        fields = {"speaker": ids[speaker]}
        other = {"nela": "Pablo", "pablo": "Nela"}.get(speaker)
        if other and other in p:
            fields["addressee"] = ids["pablo" if other == "Pablo" else "nela"]
        lines.append(
            codex.Item(
                id=f"dl-{i:08x}",
                type="dialogue",
                text=f"{m.group(1)} speaks.",
                spans=[whole(text, i)],
                fields=fields,
                created="v001",
                updated="v001",
            )
        )
    cx.replace_all(lines, op="add", by="writer")
    cure = [whole(text, i) for i, p in enumerate(text.paragraphs) if "operación" in p]
    ids["cure"] = cx.add("thread", "Pablo's sight.", {"name": "cure", "role": "main"}, cure).id
    flor = [whole(text, i) for i, p in enumerate(text.paragraphs) if "Florentina" in p]
    ids["florentina-thread"] = cx.add("thread", "Florentina.", {"name": "florentina"}, flor).id
    vista = [i for i, p in enumerate(text.paragraphs) if "vista" in p]
    setup = cx.add(
        "setup", "Sight promised.", {"label": "sight", "side": "setup"}, [whole(text, vista[0])]
    )
    cx.add(
        "setup",
        "Sight given.",
        {"label": "sight", "side": "payoff"},
        [whole(text, vista[-1])],
        [{"rel": "pays_off", "to": setup.id}],
    )
    star = next(i for i, p in enumerate(text.paragraphs) if "estrella" in p)
    ids["open-setup"] = cx.add(
        "setup", "A star.", {"label": "star", "side": "setup"}, [whole(text, star)]
    ).id
    i1 = cx.add(
        "issue", "Slow opening.", {"level": "chapter", "severity": "high"}, [whole(text, 10)]
    )
    i2 = cx.add("issue", "Repeated word.", {"level": "line", "severity": "low"}, [whole(text, 20)])
    cx.add("issue", "Unclear time jump.", {"level": "scene", "severity": "low"}, [whole(text, 30)])
    cx.add(
        "decision",
        "Keep it.",
        {"verdict": "rejected", "reason": "intended pace"},
        links=[{"rel": "about", "to": i1.id}],
        by="writer",
    )
    cx.add(
        "decision",
        "Fixed.",
        {"verdict": "accepted"},
        links=[{"rel": "about", "to": i2.id}],
        by="writer",
    )
    ids["rejected-issue"] = i1.id
    return ids
