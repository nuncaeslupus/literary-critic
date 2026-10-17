---
id: t-b50ea0c6
title: "T3: Clean-PC probe"
label: "release Clean-PC probe"
priority: 10
deps: [t-c778734c]
requires: [human:gate]
workspace: release
---

## Acceptance gate

`probes_answered == 6` (plan: `arsenal/project/release/plan.md` T3; details there under Task details).

```bash
uv run pytest -q tests/test_status.py -k "test_release_probe_evidence_answers_open_questions"
```

## Tests

- `test_release_probe_evidence_answers_open_questions` in `tests/test_status.py` — the evidence file answers desktop Q-3 and Q-8 and spec Q-5 to Q-8, each yes or no, and records VirusTotal for the first release

## Location

owner, `status/evidence/`
