"""Gate writer_setup_actions (W9): the scripted walkthrough in status/evidence."""

import re
import statistics
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "status" / "evidence" / "W9-walkthrough.md"


def _replies(text: str) -> list[str]:
    return [
        " ".join(m.split()) for m in re.findall(r"\*\*Claude:\*\* (.*?)(?:\n\n|\Z)", text, re.S)
    ]


def test_walkthrough_meets_the_writer_targets() -> None:
    text = DOC.read_text(encoding="utf-8")
    actions = text.split("## Writer actions", 1)[1].split("\n## ", 1)[0]
    rows = [r for r in actions.splitlines() if r.startswith("|") and not r.startswith("|-")][1:]
    counts = [r.rstrip().rstrip("|").rsplit("|", 1)[-1].strip().lower() for r in rows]
    assert counts and set(counts) <= {"yes", "no"}, counts  # every row says whether it counts
    writer_setup_actions = counts.count("yes")
    assert 0 < writer_setup_actions <= 5
    replies = _replies(text)
    assert len(replies) >= 6
    words = [len(r.split()) for r in replies]
    assert statistics.median(words) <= 120 and max(words) <= 120
    for reply in replies:
        own = re.sub(r"«[^»]*»", "", reply)  # quoted manuscript text is not the reply's
        assert own.count("?") <= 1, reply  # one question, one step at a time
        if re.search(r"cap[ií]tulo|p[aá]gina|escena|p[aá]rrafo|chapter|page", own, re.I):
            # A place: chapter number, page, and the quoted first and last words.
            assert re.search(r"cap[ií]tulo \d|chapter \d", own, re.I), reply
            assert re.search(r"p[aá]gina \d|pág\. ≈?\d|page \d", own, re.I), reply
            assert reply.count("«") >= 2 or reply.count("“") >= 2, reply
