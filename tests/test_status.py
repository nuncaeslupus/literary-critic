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


def test_release_probe_evidence_answers_open_questions() -> None:
    text = (EVIDENCE / "release-probe.md").read_text(encoding="utf-8")
    for q in ("Desktop Q-8", "Desktop Q-3", "Q-5", "Q-6", "Q-7", "Q-8"):
        section = text.split(f"\n## {q}:", 1)[1].split("\n## ", 1)[0]
        assert re.search(r"\*\*Answer: (yes|no)\b", section), q
    virustotal = text.split("\n## VirusTotal", 1)[1].split("\n## ", 1)[0]
    assert re.search(r"\b\d+ / \d+\b", virustotal)


def test_release_owner_switch_evidence() -> None:
    text = (EVIDENCE / "release-owner-switch.md").read_text(encoding="utf-8")
    assert "**Installed: yes**" in text
    assert re.search(r"^dev_config_entries: 0$", text, re.M)
    assert int(re.search(r"^works_found: (\d+)$", text, re.M).group(1)) >= 1  # type: ignore[union-attr]


def test_release_test_run_evidence_meets_gates() -> None:
    text = (EVIDENCE / "release-test-run.md").read_text(encoding="utf-8")
    table = text.split("## §1 criteria", 1)[1].split("\n## ", 1)[0]
    rows = [r.split("|")[1:-1] for r in table.splitlines() if r.startswith("| `")]
    verdicts = {r[0].strip(): r[3].strip() for r in rows}
    assert "`install_actions_clean_pc`" in verdicts and len(verdicts) >= 8
    for name, verdict in verdicts.items():
        assert verdict.startswith(("met", "unmeasured")), name
    measured = re.search(r"^install_actions_clean_pc: (\d+)$", text, re.M)
    assert measured and int(measured.group(1)) <= 4
    assert int(re.search(r"^auto_update_applied_restarts: (\d+)$", text, re.M).group(1)) <= 1  # type: ignore[union-attr]
    assert int(re.search(r"^writer_update_actions: (\d+)$", text, re.M).group(1)) <= 3  # type: ignore[union-attr]
