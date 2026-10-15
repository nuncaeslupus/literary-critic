import re
from pathlib import Path

EVIDENCE = Path(__file__).parents[1] / "status" / "evidence"


def test_install_evidence_names_q1_and_q3() -> None:
    text = (EVIDENCE / "install-Q1-Q3.md").read_text(encoding="utf-8")
    for q in ("Q-1", "Q-3"):
        section = text.split(f"## {q}", 1)[1].split("\n## ", 1)[0]
        assert re.search(r"\*\*Answer: (yes|no)\b", section), q


def test_workplan_q1_evidence_answers_ui_message() -> None:
    text = (EVIDENCE / "workplan-Q1-ui-message.md").read_text(encoding="utf-8")
    section = text.split("## Q-1", 1)[1].split("\n## ", 1)[0]
    assert re.search(r"\*\*Answer: (yes|no)\b", section)
    assert "ui/message" in section
