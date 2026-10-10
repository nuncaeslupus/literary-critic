---
id: t-0415ffda
title: "T10: Procedures: orientation, scene-card extraction, check execution, conversational guide; skills wrapping them"
label: "procedures and prompts"
priority: 5
deps: [t-ca8ccb83]
---

# T10: Procedures: orientation, scene-card extraction, check execution, conversational guide; skills wrapping them

From `status/plan.md` (service: prompts).

## Acceptance gate
Metric: `prompts_reference_valid_commands == 1.0`. Record the measurement in `status/evidence/T10.json` and the plan's evidence log.

```bash
uv run pytest tests/test_prompts.py::test_prompts_only_reference_existing_commands
```

## Tests
`test_prompts_only_reference_existing_commands` in `tests/test_prompts.py` — every `lc` call in prompts exists
