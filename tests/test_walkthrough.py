"""Gate writer_setup_actions (W9): the scripted walkthrough in status/evidence."""

import re
import statistics

from litcritic.workspace import repo_root

DOC = repo_root() / "status" / "evidence" / "W9-walkthrough.md"


def _replies(text: str) -> list[str]:
    return [
        " ".join(m.split()) for m in re.findall(r"\*\*Claude:\*\* (.*?)(?:\n\n|\Z)", text, re.S)
    ]


def test_walkthrough_meets_the_writer_targets() -> None:
    text = DOC.read_text(encoding="utf-8")
    actions = text.split("## Writer actions", 1)[1].split("\n## ", 1)[0]
    writer_setup_actions = len(re.findall(r"^\|[^\n]*\| yes \|$", actions, re.M))
    assert 0 < writer_setup_actions <= 5
    replies = _replies(text)
    assert len(replies) >= 6
    words = [len(r.split()) for r in replies]
    assert statistics.median(words) <= 120 and max(words) <= 120
    for reply in replies:
        own = re.sub(r"«[^»]*»", "", reply)  # quoted manuscript text is not the reply's
        assert own.count("?") <= 1, reply  # one question, one step at a time
        if re.search(r"\bcap[ií]tulo \d", reply, re.I):  # a place: fully located
            assert "«" in reply and re.search(r"p[aá]gina|pág\.", reply), reply
