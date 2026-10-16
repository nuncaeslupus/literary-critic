---
id: t-e7ff65dc
title: "T10: End-to-end run"
label: "T10: End-to-end run"
priority: 5
deps: [t-c3d847c1, t-98eb6b03, t-00f6271d]
requires: [human:gate]
workspace: desktop
status: cancelled
---

## Acceptance gate

`writer_setup_actions <= 3` (plan: `arsenal/project/desktop/plan.md` T10; details there under Task details).

```bash
uv run pytest -q tests/test_status.py -k desktop_walkthrough
```

## Tests

- `test_desktop_walkthrough_evidence_meets_gates` in `tests/test_status.py` — the record shows setup actions ≤ 3, generic requests and novel switches resolved 10 of 10, jumps p50 ≤ 8 s

## Location

owner + Claude, `status/evidence/`
