import re
from pathlib import Path

EVIDENCE = Path(__file__).parents[1] / "status" / "evidence"


def test_install_evidence_names_q1_and_q3() -> None:
    text = (EVIDENCE / "install-Q1-Q3.md").read_text(encoding="utf-8")
    for q in ("Q-1", "Q-3"):
        section = text.split(f"## {q}", 1)[1].split("\n## ", 1)[0]
        assert re.search(r"\*\*Answer: (yes|no)\b", section), q
