---
id: t-a5caf3a0
title: "T5: Owner hand tests Q-1 and Q-3"
label: "T5: Owner hand tests Q-1"
priority: 10
workspace: install
---

## Acceptance gate

`hand_tests_recorded == 2` (plan: `arsenal/project/install/plan.md` T5; details there under Task details).

```bash
uv run pytest -q tests/test_status.py -k install_evidence
```

## Tests

- `test_install_evidence_names_q1_and_q3` in `tests/test_status.py` — `status/evidence/install-Q1-Q3.md` exists and answers Q-1 and Q-3 yes or no.
