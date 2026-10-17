---
id: t-2bf1ba73
title: "T8: Q-1 probe of ui/message"
label: "probe ui/message delivery"
priority: 10
deps: [t-94f4925f]
requires: [human:gate]
workspace: workplan
status: merged
---

## Acceptance gate

`probes_answered == 1` (plan: `arsenal/project/workplan/plan.md` T8; details there under Task details).

```bash
uv run pytest -q tests/test_status.py -k "test_workplan_q1_evidence_answers_ui_message"
```

## Tests

- `test_workplan_q1_evidence_answers_ui_message` in `tests/test_status.py` — the evidence file says whether the desktop app delivers the page's `ui/message` to the model, yes or no

## Location

owner, `status/evidence/`
